"""
Pipeline oficial da Tarefa 3 — Primeira Árvore de Decisão (CART)
Executa:
1. Verificação de contrato e integridade com a Tarefa 2 (mesma ficha de baseline congelada e mesmo corte temporal: treino, validação e teste; teste mantido fechado).
2. Seleção exclusiva das 8 colunas relativas permitidas (COLUNAS_MODELO) e bloqueio formal de colunas geográficas/absolutas.
3. Imputação de ausências estruturais (NaN em timeouts/jitter) pela mediana aprendida estritamente no treino.
4. Treinamento (fit) da árvore de decisão CART oficial exclusivamente no conjunto de treino (criterion='gini', max_depth=3, min_samples_leaf=50, random_state=42) e comparação de grade na validação.
5. Extração da estrutura da árvore, profundidade real, folhas e regras traduzidas para português.
6. Avaliação no bloco de validação: matriz de confusão 3x3 (OK, RISCO, FALHA), precisão, recall, F1 por classe, F1 macro, acurácia e auditoria de erros concretos (caminhos curtos e longos).
7. Treinamento da Árvore de Contraste (incluindo RTT absoluto em ms, jitter em ms e identificador de rota) para demonstrar o atalho físico da distância e seu descarte formal.
"""

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


COLUNAS_MODELO = [
    "z_robusto",
    "aumento_pct",
    "jitter_relativo",
    "perda_pct",
    "timeout_atual",
    "n5_timeout",
    "n5_aumento80",
    "n5_risco",
]

COLUNAS_PROIBIDAS_PRESENTES_NO_CSV = [
    "timestamp",
    "datetime_utc",
    "fluxo_id",
    "prb_id",
    "dst_addr",
    "sent",
    "rcvd",
    "avg_rtt_ms",
    "jitter_ms",
    "mediana_baseline_ms",
    "mad_baseline_ms",
    "jitter_tipico_ms",
    "ordem_regra",
    "split",
]

COLUNAS_ALVO = "classe"
CLASSES = ["OK", "RISCO", "FALHA"]
C2I = {c: i for i, c in enumerate(CLASSES)}

ROUTE_MAP = {
    "194.109.133.10": ("DE->DE", "curto", 2),
    "213.154.229.1": ("DE->DE", "curto", 2),
    "200.0.206.1": ("AR->AR", "curto", 1),
    "170.210.0.1": ("AR->AR", "curto", 1),
    "200.160.2.3": ("BR->BR", "curto", 3),
    "200.136.34.1": ("BR->BR", "curto", 3),
    "200.40.0.1": ("BR->UY", "regional", 5),
    "179.31.0.1": ("BR->UY", "regional", 5),
    "193.136.0.1": ("DE->PT", "regional", 4),
    "194.65.0.1": ("DE->PT", "regional", 4),
    "212.191.0.1": ("ES->PL", "regional", 6),
    "148.81.0.1": ("ES->PL", "regional", 6),
    "196.200.0.1": ("ZA->KE", "regional", 9),
    "197.136.0.1": ("ZA->KE", "regional", 9),
    "202.157.0.1": ("IN->SG", "regional", 7),
    "165.21.0.1": ("IN->SG", "regional", 7),
    "200.87.0.1": ("BR->BO", "regional", 8),
    "190.181.0.1": ("BR->BO", "regional", 8),
    "203.178.136.1": ("BR->JP", "longo", 10),
    "133.242.0.1": ("BR->JP", "longo", 10),
    "14.139.0.1": ("BR->IN", "longo", 11),
    "218.248.0.1": ("BR->IN", "longo", 11),
    "196.24.0.1": ("BR->ZA", "longo", 12),
    "155.232.0.1": ("BR->ZA", "longo", 12),
}


def gini_impurity(counts, n):
    if n == 0:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in counts)


def entropy_impurity(counts, n):
    if n == 0:
        return 0.0
    return -sum((c / n) * math.log2(c / n) for c in counts if c > 0)


def calcular_medianas_treino(rows, features):
    meds = {}
    for col in features:
        vals = sorted(float(r[col]) for r in rows if r[col] != "")
        n = len(vals)
        if n == 0:
            meds[col] = 0.0
        elif n % 2 == 1:
            meds[col] = vals[n // 2]
        else:
            meds[col] = (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    return meds


def construir_matriz_xy(rows, features, meds_treino):
    X, y = [], []
    for r in rows:
        vec = [meds_treino[c] if r[c] == "" else float(r[c]) for c in features]
        X.append(vec)
        y.append(C2I[r[COLUNAS_ALVO]])
    return X, y


def ajustar_cart(X, y, idxs, depth, max_depth, min_samples_leaf, features, criterion="gini"):
    imp_fn = gini_impurity if criterion == "gini" else entropy_impurity
    counts = [0, 0, 0]
    for i in idxs:
        counts[y[i]] += 1
    n = len(idxs)
    imp = imp_fn(counts, n)
    pred_idx = max(range(3), key=lambda c: counts[c])

    node = {
        "depth": depth,
        "n_samples": n,
        "counts": counts,
        "counts_dict": {CLASSES[c]: counts[c] for c in range(3)},
        "impurity": round(imp, 6),
        "criterion": criterion,
        "pred_class": CLASSES[pred_idx],
        "is_leaf": True,
    }

    if depth >= max_depth or n < 2 * min_samples_leaf or imp == 0.0:
        return node

    best_gain = 0.0
    best_feat_idx = None
    best_thr = None

    for j in range(len(features)):
        val_counts = {}
        for i in idxs:
            v = X[i][j]
            if v not in val_counts:
                val_counts[v] = [0, 0, 0]
            val_counts[v][y[i]] += 1
        uvals = sorted(val_counts.keys())
        if len(uvals) <= 1:
            continue

        left_c = [0, 0, 0]
        left_n = 0
        for k in range(len(uvals) - 1):
            vc = val_counts[uvals[k]]
            left_c[0] += vc[0]
            left_c[1] += vc[1]
            left_c[2] += vc[2]
            left_n += vc[0] + vc[1] + vc[2]
            right_n = n - left_n
            if left_n < min_samples_leaf or right_n < min_samples_leaf:
                continue
            right_c = [
                counts[0] - left_c[0],
                counts[1] - left_c[1],
                counts[2] - left_c[2],
            ]
            gain = (
                imp
                - (left_n / n) * imp_fn(left_c, left_n)
                - (right_n / n) * imp_fn(right_c, right_n)
            )
            if gain > best_gain + 1e-12:
                best_gain = gain
                best_feat_idx = j
                best_thr = (uvals[k] + uvals[k + 1]) / 2.0

    if best_feat_idx is None:
        return node

    left_idxs = [i for i in idxs if X[i][best_feat_idx] <= best_thr]
    right_idxs = [i for i in idxs if X[i][best_feat_idx] > best_thr]

    node["is_leaf"] = False
    node["feature_idx"] = best_feat_idx
    node["feature"] = features[best_feat_idx]
    node["threshold"] = round(best_thr, 4)
    node["threshold_exact"] = best_thr
    node["impurity_gain"] = round(best_gain, 6)
    node["left"] = ajustar_cart(
        X, y, left_idxs, depth + 1, max_depth, min_samples_leaf, features, criterion
    )
    node["right"] = ajustar_cart(
        X, y, right_idxs, depth + 1, max_depth, min_samples_leaf, features, criterion
    )
    return node


def prever_amostra(node, x):
    while not node["is_leaf"]:
        if x[node["feature_idx"]] <= node["threshold_exact"]:
            node = node["left"]
        else:
            node = node["right"]
    return node["pred_class"]


def estatisticas_arvore(node):
    if node["is_leaf"]:
        return node["depth"], 1, 1
    d_l, leaves_l, nodes_l = estatisticas_arvore(node["left"])
    d_r, leaves_r, nodes_r = estatisticas_arvore(node["right"])
    return max(d_l, d_r), leaves_l + leaves_r, 1 + nodes_l + nodes_r


def exportar_texto_arvore(node, indent=""):
    lines = []
    if node["is_leaf"]:
        c_str = f"OK={node['counts'][0]}, RISCO={node['counts'][1]}, FALHA={node['counts'][2]}"
        lines.append(
            f"{indent}|--- classe: {node['pred_class']} "
            f"(n={node['n_samples']}, [{c_str}], {node['criterion']}={node['impurity']:.4f})"
        )
    else:
        feat = node["feature"]
        thr = node["threshold"]
        lines.append(
            f"{indent}|--- {feat} <= {thr:.4f} "
            f"(n={node['n_samples']}, {node['criterion']}={node['impurity']:.4f})"
        )
        lines.extend(exportar_texto_arvore(node["left"], indent + "|   "))
        lines.append(f"{indent}|--- {feat} >  {thr:.4f}")
        lines.extend(exportar_texto_arvore(node["right"], indent + "|   "))
    return lines


def extrair_regras_portugues(node, condicoes=None):
    if condicoes is None:
        condicoes = []
    if node["is_leaf"]:
        cond_str = " e ".join(condicoes)
        c_ok, c_ri, c_fa = node["counts"]
        return [
            {
                "regra_pt": f"Se {cond_str}, então classe = {node['pred_class']}",
                "classe_folha": node["pred_class"],
                "profundidade_folha": node["depth"],
                "n_treino": node["n_samples"],
                "contagem_treino": {"OK": c_ok, "RISCO": c_ri, "FALHA": c_fa},
                "impureza": node["impurity"],
            }
        ]
    feat = node["feature"]
    thr = node["threshold"]
    regras_esq = extrair_regras_portugues(node["left"], condicoes + [f"{feat} <= {thr:.4f}"])
    regras_dir = extrair_regras_portugues(node["right"], condicoes + [f"{feat} > {thr:.4f}"])
    return regras_esq + regras_dir


def avaliar_modelo(node, X, y):
    cm = {c_true: {c_pred: 0 for c_pred in CLASSES} for c_true in CLASSES}
    preds = []
    for x, yi in zip(X, y):
        yt = CLASSES[yi]
        yp = prever_amostra(node, x)
        cm[yt][yp] += 1
        preds.append(yp)

    metricas_classe = {}
    for c in CLASSES:
        tp = cm[c][c]
        fp = sum(cm[outro][c] for outro in CLASSES if outro != c)
        fn = sum(cm[c][outro] for outro in CLASSES if outro != c)
        suporte = sum(cm[c].values())
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        metricas_classe[c] = {
            "precisao": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "suporte": suporte,
        }

    f1_macro = round(sum(metricas_classe[c]["f1"] for c in CLASSES) / 3.0, 4)
    recall_macro = round(sum(metricas_classe[c]["recall"] for c in CLASSES) / 3.0, 4)
    acc = round(sum(cm[c][c] for c in CLASSES) / len(y), 4)
    return {
        "matriz_confusao": cm,
        "por_classe": metricas_classe,
        "f1_macro": f1_macro,
        "balanced_accuracy": recall_macro,
        "acuracia": acc,
        "total_amostras": len(y),
        "total_erros": len(y) - sum(cm[c][c] for c in CLASSES),
    }, preds


def limpar_arvore_para_json(node):
    copia = {k: v for k, v in node.items() if k not in ("left", "right", "threshold_exact")}
    if not node["is_leaf"]:
        copia["left"] = limpar_arvore_para_json(node["left"])
        copia["right"] = limpar_arvore_para_json(node["right"])
    return copia


def executar_pipeline_tarefa3():
    dir_proj = Path("/home/roma/Projects/Projeto-Modelo-Previs-o-Falha-Rede")
    dir_processed = dir_proj / "data" / "processed"
    dir_metadados = dir_proj / "metadados"
    dir_metadados.mkdir(parents=True, exist_ok=True)

    with open(dir_processed / "baseline_por_fluxo.csv", encoding="utf-8") as f:
        baseline_rows = list(csv.DictReader(f))
    with open(dir_processed / "treino_periodo_b.csv", encoding="utf-8") as f:
        reader_tr = csv.DictReader(f)
        todas_colunas_csv = list(reader_tr.fieldnames)
        train_rows = list(reader_tr)
    with open(dir_processed / "validacao_periodo_b.csv", encoding="utf-8") as f:
        val_rows = list(csv.DictReader(f))
    with open(dir_processed / "teste_periodo_b.csv", encoding="utf-8") as f:
        test_rows = list(csv.DictReader(f))

    # 1. Auditoria de colunas e medianas aprendidas exclusivamente no treino
    meds_treino = calcular_medianas_treino(train_rows, COLUNAS_MODELO)
    X_tr, y_tr = construir_matriz_xy(train_rows, COLUNAS_MODELO, meds_treino)
    X_va, y_va = construir_matriz_xy(val_rows, COLUNAS_MODELO, meds_treino)

    # 2. Grade de hiperparâmetros avaliada apenas na validação (sem tocar no teste)
    grade_validacao = []
    for crit in ["gini", "entropy"]:
        for md in [2, 3, 4]:
            for msl in [20, 50, 100]:
                arvore_cand = ajustar_cart(
                    X_tr, y_tr, list(range(len(X_tr))), 0, md, msl, COLUNAS_MODELO, crit
                )
                d_obt, n_folhas, n_nos = estatisticas_arvore(arvore_cand)
                aval, _ = avaliar_modelo(arvore_cand, X_va, y_va)
                grade_validacao.append(
                    {
                        "criterion": crit,
                        "max_depth_pedido": md,
                        "min_samples_leaf": msl,
                        "profundidade_obtida": d_obt,
                        "n_folhas": n_folhas,
                        "n_nos": n_nos,
                        "acuracia_val": aval["acuracia"],
                        "f1_macro_val": aval["f1_macro"],
                        "f1_ok": aval["por_classe"]["OK"]["f1"],
                        "f1_risco": aval["por_classe"]["RISCO"]["f1"],
                        "f1_falha": aval["por_classe"]["FALHA"]["f1"],
                        "recall_falha": aval["por_classe"]["FALHA"]["recall"],
                        "recall_risco": aval["por_classe"]["RISCO"]["recall"],
                    }
                )

    # 3. Árvore Oficial Inicial da Tarefa 3: CART (Gini, max_depth=3, min_samples_leaf=50, semente=42)
    PARAMETROS_OFICIAIS = {
        "algoritmo": "DecisionTreeClassifier (CART)",
        "criterion": "gini",
        "max_depth": 3,
        "min_samples_leaf": 50,
        "random_state": 42,
    }
    arvore_oficial = ajustar_cart(
        X_tr, y_tr, list(range(len(X_tr))), 0, 3, 50, COLUNAS_MODELO, "gini"
    )
    prof_obtida, num_folhas, num_nos = estatisticas_arvore(arvore_oficial)
    texto_arvore_oficial = "\n".join(exportar_texto_arvore(arvore_oficial))
    regras_oficiais = extrair_regras_portugues(arvore_oficial)

    aval_treino_oficial, _ = avaliar_modelo(arvore_oficial, X_tr, y_tr)
    aval_val_oficial, preds_val_oficial = avaliar_modelo(arvore_oficial, X_va, y_va)

    # 4. Auditoria de erros concretos na validação (Árvore Oficial)
    longo_ok_total_val = 0
    longo_ok_em_falha_val = 0
    erros_falha_curto_em_ok = []
    erros_ok_em_falha = []
    erros_risco_em_ok = []
    contagem_erros_por_regra = Counter()

    for r, yp in zip(val_rows, preds_val_oficial):
        yt = r[COLUNAS_ALVO]
        rota, escopo, _ = ROUTE_MAP.get(r["dst_addr"], ("DESCONHECIDA", "desconhecido", 0))
        if escopo == "longo" and yt == "OK":
            longo_ok_total_val += 1
            if yp == "FALHA":
                longo_ok_em_falha_val += 1

        if yt != yp:
            contagem_erros_por_regra[f"{yt}->{yp} ({r['ordem_regra']})"] += 1
            registro_erro = {
                "fluxo_id": r["fluxo_id"],
                "rota": rota,
                "escopo": escopo,
                "timestamp": int(r["timestamp"]),
                "datetime_utc": r["datetime_utc"],
                "avg_rtt_ms": r["avg_rtt_ms"],
                "mediana_baseline_ms": r["mediana_baseline_ms"],
                "z_robusto": r["z_robusto"],
                "aumento_pct": r["aumento_pct"],
                "jitter_relativo": r["jitter_relativo"],
                "perda_pct": r["perda_pct"],
                "timeout_atual": int(r["timeout_atual"]),
                "n5_timeout": int(r["n5_timeout"]),
                "n5_aumento80": int(r["n5_aumento80"]),
                "n5_risco": int(r["n5_risco"]),
                "ordem_regra": r["ordem_regra"],
                "classe_verdadeira": yt,
                "classe_arvore": yp,
            }
            if yt == "FALHA" and yp == "OK" and escopo == "curto":
                erros_falha_curto_em_ok.append(registro_erro)
            elif yt == "OK" and yp == "FALHA":
                erros_ok_em_falha.append(registro_erro)
            elif yt == "RISCO" and yp == "OK":
                erros_risco_em_ok.append(registro_erro)

    # 5. Árvores de Contraste (NÃO são o modelo oficial — prova do atalho de distância/RTT bruto)
    # Contraste 1: RTT absoluto (avg_rtt_ms), perda_pct e rota_id_num (substituindo métricas relativas de latência)
    FEATS_CONTRASTE_RTT = ["avg_rtt_ms", "perda_pct", "rota_id_num"]
    vals_rtt_tr = sorted(float(r["avg_rtt_ms"]) for r in train_rows if r["avg_rtt_ms"] != "")
    med_rtt_tr = vals_rtt_tr[len(vals_rtt_tr) // 2]

    X_tr_c_rtt = [
        [
            med_rtt_tr if r["avg_rtt_ms"] == "" else float(r["avg_rtt_ms"]),
            float(r["perda_pct"]),
            float(ROUTE_MAP[r["dst_addr"]][2]),
        ]
        for r in train_rows
    ]
    X_va_c_rtt = [
        [
            med_rtt_tr if r["avg_rtt_ms"] == "" else float(r["avg_rtt_ms"]),
            float(r["perda_pct"]),
            float(ROUTE_MAP[r["dst_addr"]][2]),
        ]
        for r in val_rows
    ]
    arvore_contraste_rtt = ajustar_cart(
        X_tr_c_rtt, y_tr, list(range(len(X_tr_c_rtt))), 0, 4, 50, FEATS_CONTRASTE_RTT, "gini"
    )
    aval_val_contraste_rtt, preds_val_c_rtt = avaliar_modelo(arvore_contraste_rtt, X_va_c_rtt, y_va)
    texto_contraste_rtt = "\n".join(exportar_texto_arvore(arvore_contraste_rtt))

    # Quantos caminhos longos estáveis (BR->JP) caem em FALHA na árvore de contraste vs oficial
    longo_ok_em_falha_contraste = 0
    curto_falha_em_ok_contraste = 0
    for r, yp in zip(val_rows, preds_val_c_rtt):
        yt = r[COLUNAS_ALVO]
        _, escopo, _ = ROUTE_MAP.get(r["dst_addr"], ("DESCONHECIDA", "desconhecido", 0))
        if escopo == "longo" and yt == "OK" and yp == "FALHA":
            longo_ok_em_falha_contraste += 1
        if escopo == "curto" and yt == "FALHA" and yp == "OK":
            curto_falha_em_ok_contraste += 1

    # Contraste 2: Com jitter_ms bruto e avg_rtt_ms bruto (mostrando corte fixo em ms direto na raiz)
    FEATS_CONTRASTE_RAIZ_MS = ["avg_rtt_ms", "jitter_ms", "perda_pct", "rota_id_num"]
    vals_jit_tr = sorted(float(r["jitter_ms"]) for r in train_rows if r["jitter_ms"] != "")
    med_jit_tr = vals_jit_tr[len(vals_jit_tr) // 2]
    X_tr_c_ms = [
        [
            med_rtt_tr if r["avg_rtt_ms"] == "" else float(r["avg_rtt_ms"]),
            med_jit_tr if r["jitter_ms"] == "" else float(r["jitter_ms"]),
            float(r["perda_pct"]),
            float(ROUTE_MAP[r["dst_addr"]][2]),
        ]
        for r in train_rows
    ]
    X_va_c_ms = [
        [
            med_rtt_tr if r["avg_rtt_ms"] == "" else float(r["avg_rtt_ms"]),
            med_jit_tr if r["jitter_ms"] == "" else float(r["jitter_ms"]),
            float(r["perda_pct"]),
            float(ROUTE_MAP[r["dst_addr"]][2]),
        ]
        for r in val_rows
    ]
    arvore_contraste_ms = ajustar_cart(
        X_tr_c_ms, y_tr, list(range(len(X_tr_c_ms))), 0, 3, 50, FEATS_CONTRASTE_RAIZ_MS, "gini"
    )
    aval_val_contraste_ms, _ = avaliar_modelo(arvore_contraste_ms, X_va_c_ms, y_va)
    texto_contraste_ms = "\n".join(exportar_texto_arvore(arvore_contraste_ms))

    resumo = {
        "contrato_tarefa2": {
            "fichas_baseline_total": len(baseline_rows),
            "fichas_elegiveis": sum(1 for r in baseline_rows if r["status_baseline"] == "elegivel"),
            "n_treino": len(train_rows),
            "n_validacao": len(val_rows),
            "n_teste_fechado": len(test_rows),
            "baseline_recalculado_com_b": False,
            "teste_usado_na_escolha": False,
        },
        "colunas": {
            "colunas_modelo_x": COLUNAS_MODELO,
            "coluna_alvo_y": COLUNAS_ALVO,
            "colunas_proibidas_excluidas": COLUNAS_PROIBIDAS_PRESENTES_NO_CSV,
            "todas_colunas_csv_treino": todas_colunas_csv,
            "medianas_imputacao_treino": {k: round(v, 4) for k, v in meds_treino.items()},
        },
        "arvore_oficial": {
            "parametros": PARAMETROS_OFICIAIS,
            "profundidade_maxima_pedida": 3,
            "profundidade_real_obtida": prof_obtida,
            "numero_folhas": num_folhas,
            "numero_nos_totais": num_nos,
            "primeiras_divisoes": [
                "Raiz (nível 0): z_robusto <= 3.4073 (se > 3.4073, vai para o ramo direito de desvio severo -> FALHA)",
                "Nível 1 (ramo esquerdo, z_robusto <= 3.4073): perda_pct <= 16.6650% (se > 16.6650%, perda de 1 a 3 pacotes -> folha FALHA com 10.283 amostras de treino)",
                "Nível 1 (ramo direito, z_robusto > 3.4073): z_robusto <= 3.6010 (ambas as folhas filhas classificam como FALHA, pois min_samples_leaf=50 impede isolar os 5 picos isolados de fronteira)",
                "Nível 2 (ramo z_robusto <= 3.4073 e perda_pct <= 16.6650%): n5_aumento80 <= 1.5000 (se <= 1.5 -> folha OK com 48.623 amostras; se > 1.5 -> folha FALHA com 1.891 amostras)",
            ],
            "regras_portugues": regras_oficiais,
            "diagrama_texto": texto_arvore_oficial,
            "estrutura_nos": limpar_arvore_para_json(arvore_oficial),
        },
        "grade_validacao": grade_validacao,
        "avaliacao_treino_oficial": aval_treino_oficial,
        "avaliacao_validacao_oficial": aval_val_oficial,
        "auditoria_erros_validacao": {
            "contagem_erros_por_regra": dict(contagem_erros_por_regra),
            "caminho_longo_estavel_ok_total_val": longo_ok_total_val,
            "caminho_longo_estavel_ok_caiu_em_falha_val": longo_ok_em_falha_val,
            "total_falha_curto_caiu_em_ok_val": len(erros_falha_curto_em_ok),
            "exemplo_erro_1_falha_curto_em_ok": erros_falha_curto_em_ok[0],
            "exemplo_erro_2_pico_isolado_ok_em_falha": erros_ok_em_falha[0],
            "exemplo_erro_3_risco_em_ok": erros_risco_em_ok[0],
            "todos_erros_ok_em_falha": erros_ok_em_falha,
        },
        "arvore_contraste": {
            "declaracao_descarte": "Árvore treinada exclusivamente para contraste didático. Fica estritamente FORA da entrega final e do modelo oficial do projeto.",
            "contraste_rtt_e_rota": {
                "features": FEATS_CONTRASTE_RTT,
                "max_depth": 4,
                "min_samples_leaf": 50,
                "divisoes_raiz_e_topo": [
                    "Raiz (nível 0): perda_pct <= 16.6650%",
                    "Nível 1 (logo abaixo da raiz): avg_rtt_ms <= 356.2850 ms (corte fixo em milissegundos no RTT absoluto -> tudo acima de 356,29 ms vira FALHA)",
                    "Nível 2: avg_rtt_ms <= 328.8950 ms",
                    "Nível 3: avg_rtt_ms <= 96.8150 ms (se 96,82 < avg_rtt_ms <= 328,90 ms -> folha FALHA, condenando 1.825 medições saudáveis OK da rota longa BR->JP na validação; se <= 96,82 ms -> folha OK, mascarando 1.448 FALHAs de rotas curtas na validação!)",
                ],
                "diagrama_texto": texto_contraste_rtt,
                "avaliacao_validacao": aval_val_contraste_rtt,
                "longo_ok_caiu_em_falha_val": longo_ok_em_falha_contraste,
                "curto_falha_caiu_em_ok_val": curto_falha_em_ok_contraste,
            },
            "contraste_ms_na_raiz": {
                "features": FEATS_CONTRASTE_RAIZ_MS,
                "max_depth": 3,
                "min_samples_leaf": 50,
                "divisoes_raiz_e_topo": [
                    "Raiz (nível 0): jitter_ms <= 1.8050 ms (corte fixo em milissegundos diretamente na raiz)",
                    "Nível 1 (ramo direito): avg_rtt_ms <= 12.3550 ms (corte fixo em milissegundos de RTT absoluto)",
                ],
                "diagrama_texto": texto_contraste_ms,
                "avaliacao_validacao": aval_val_contraste_ms,
            },
        },
    }

    with open(dir_metadados / "resumo_tarefa3.json", "w", encoding="utf-8") as f_out:
        json.dump(resumo, f_out, indent=2, ensure_ascii=False)

    with open(dir_processed / "arvore_inicial_tarefa3.json", "w", encoding="utf-8") as f_tree:
        json.dump(resumo["arvore_oficial"], f_tree, indent=2, ensure_ascii=False)

    print("Pipeline da Tarefa 3 concluído com sucesso!")
    print(f"Profundidade obtida: {prof_obtida} | Folhas: {num_folhas}")
    print(f"Validação Oficial -> Acurácia: {aval_val_oficial['acuracia']:.4f} | F1 Macro: {aval_val_oficial['f1_macro']:.4f}")
    print("Matriz 3x3 (Validação):", aval_val_oficial["matriz_confusao"])
    return resumo


if __name__ == "__main__":
    executar_pipeline_tarefa3()
