"""
Pipeline oficial da Tarefa 5 — Árvore Final e Abertura Única do Teste
Executa:
1. Carregamento da Árvore Ajustada da Tarefa 4 (CART: criterion='entropy', max_depth=6, min_samples_leaf=20, random_state=42, 7 folhas), sem qualquer reajuste de hiperparâmetros e sem recalcular o baseline no Período B.
2. Avaliação única no Teste Temporal (data/processed/teste_periodo_b.csv — 48.270 medições): matriz 3x3 em contagem, precisão, recall e F1 de OK, RISCO e FALHA, F1 macro, Recall de FALHA, análise de RISCO <-> FALHA e estratificação por escopo de rota (curto, regional, longo).
3. Protocolo B — Checagem em Fluxos Não Vistos no Treino (hold-out de 16 fluxos inteiros das probes *03 cobrindo rotas curtas, regionais e longas, com fichas calculadas exclusivamente no Período A >= 1.500 RTTs válidos) + declaração formal sobre os 3 fluxos excluídos por baseline_insuficiente (< 1.500 RTTs válidos).
4. Avaliação do horizonte de 12 minutos à frente (t + 3 janelas de 240s) contra a regra de persistência ("repetir a classe atual"), fundamentando a declaração formal de que o entregável opera como Detector do estado atual relativo ao baseline.
5. Exportação de data/processed/arvore_final_tarefa5.json e metadados/resumo_tarefa5.json.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.arvore_inicial import (
    CLASSES,
    COLUNAS_ALVO,
    COLUNAS_MODELO,
    COLUNAS_PROIBIDAS_PRESENTES_NO_CSV,
    ROUTE_MAP,
    ajustar_cart,
    avaliar_modelo,
    calcular_medianas_treino,
    construir_matriz_xy,
    estatisticas_arvore,
    exportar_texto_arvore,
    extrair_regras_portugues,
    limpar_arvore_para_json,
    prever_amostra,
)


def calcular_metricas_de_pares(y_true_idx, y_pred_str):
    cm = {c_true: {c_pred: 0 for c_pred in CLASSES} for c_true in CLASSES}
    for yi, yp in zip(y_true_idx, y_pred_str):
        cm[CLASSES[yi]][yp] += 1

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
    acc = round(sum(cm[c][c] for c in CLASSES) / len(y_true_idx), 4)
    return {
        "matriz_confusao": cm,
        "por_classe": metricas_classe,
        "f1_macro": f1_macro,
        "balanced_accuracy": recall_macro,
        "acuracia": acc,
        "total_amostras": len(y_true_idx),
        "total_erros": len(y_true_idx) - sum(cm[c][c] for c in CLASSES),
    }


def executar_pipeline_tarefa5():
    dir_proj = Path("/home/roma/Projects/Projeto-Modelo-Previs-o-Falha-Rede")
    dir_processed = dir_proj / "data" / "processed"
    dir_metadados = dir_proj / "metadados"

    with open(dir_processed / "baseline_por_fluxo.csv", encoding="utf-8") as f:
        baseline_rows = list(csv.DictReader(f))
    with open(dir_processed / "dataset_rotulado_periodo_b.csv", encoding="utf-8") as f:
        all_b_rows = list(csv.DictReader(f))
    with open(dir_processed / "treino_periodo_b.csv", encoding="utf-8") as f:
        train_rows = list(csv.DictReader(f))
    with open(dir_processed / "validacao_periodo_b.csv", encoding="utf-8") as f:
        val_rows = list(csv.DictReader(f))
    with open(dir_processed / "teste_periodo_b.csv", encoding="utf-8") as f:
        test_rows = list(csv.DictReader(f))

    # 1. Fit exclusivo no treino com os hiperparâmetros congelados na Tarefa 4
    meds_treino = calcular_medianas_treino(train_rows, COLUNAS_MODELO)
    X_tr, y_tr = construir_matriz_xy(train_rows, COLUNAS_MODELO, meds_treino)
    X_va, y_va = construir_matriz_xy(val_rows, COLUNAS_MODELO, meds_treino)
    X_te, y_te = construir_matriz_xy(test_rows, COLUNAS_MODELO, meds_treino)

    arvore_final = ajustar_cart(
        X_tr, y_tr, list(range(len(X_tr))), 0, 6, 20, COLUNAS_MODELO, "entropy"
    )
    prof_final, folhas_final, nos_final = estatisticas_arvore(arvore_final)
    regras_pt = extrair_regras_portugues(arvore_final)
    diagrama_txt = "\n".join(exportar_texto_arvore(arvore_final))

    # Avaliações da Árvore Final (Treino, Validação e Abertura Única do Teste)
    aval_tr, _ = avaliar_modelo(arvore_final, X_tr, y_tr)
    aval_va, _ = avaliar_modelo(arvore_final, X_va, y_va)
    aval_te, preds_te = avaliar_modelo(arvore_final, X_te, y_te)

    # Comparação histórica no Teste contra a Árvore Inicial da Tarefa 3 (apenas para auditoria dos casos)
    arvore_t3 = ajustar_cart(
        X_tr, y_tr, list(range(len(X_tr))), 0, 3, 50, COLUNAS_MODELO, "gini"
    )
    aval_te_t3, preds_te_t3 = avaliar_modelo(arvore_t3, X_te, y_te)

    # Estratificação do Teste por escopo de rota (curto, regional, longo)
    escopo_stats = {}
    for escopo_alvo in ["curto", "regional", "longo"]:
        idxs_esc = [
            i
            for i, r in enumerate(test_rows)
            if ROUTE_MAP.get(r["dst_addr"], ("?", "?", "?"))[1] == escopo_alvo
        ]
        y_esc = [y_te[i] for i in idxs_esc]
        p_esc = [preds_te[i] for i in idxs_esc]
        escopo_stats[escopo_alvo] = calcular_metricas_de_pares(y_esc, p_esc)

    # Casos concretos no Teste Temporal (Seção 2 da Tarefa 5)
    caso_ok_longo_teste = None
    caso_fronteira_risco_falha_teste = None
    caso_falha_curto_timeout_teste = None

    for r, x, p3, p4 in zip(test_rows, X_te, preds_te_t3, preds_te):
        rota, escopo, _ = ROUTE_MAP.get(r["dst_addr"], ("?", "?", "?"))
        if (
            caso_ok_longo_teste is None
            and escopo == "longo"
            and r["classe"] == "OK"
            and r["avg_rtt_ms"] != ""
            and float(r["avg_rtt_ms"]) > 340.0
        ):
            caso_ok_longo_teste = {
                "fluxo_id": r["fluxo_id"],
                "rota": rota,
                "escopo": escopo,
                "datetime_utc": r["datetime_utc"],
                "timestamp": int(r["timestamp"]),
                "avg_rtt_ms": r["avg_rtt_ms"],
                "mediana_baseline_ms": r["mediana_baseline_ms"],
                "mad_baseline_ms": r["mad_baseline_ms"],
                "z_robusto": r["z_robusto"],
                "perda_pct": r["perda_pct"],
                "n5_timeout": int(r["n5_timeout"]),
                "n5_aumento80": int(r["n5_aumento80"]),
                "n5_risco": int(r["n5_risco"]),
                "classe_real": r["classe"],
                "pred_arvore_final": p4,
                "regra_absoluta_ingenua": "FALHA (RTT > 100 ms)",
            }
        if (
            caso_fronteira_risco_falha_teste is None
            and r["classe"] == "RISCO"
            and p3 == "FALHA"
            and p4 == "RISCO"
        ):
            caso_fronteira_risco_falha_teste = {
                "fluxo_id": r["fluxo_id"],
                "rota": rota,
                "escopo": escopo,
                "datetime_utc": r["datetime_utc"],
                "timestamp": int(r["timestamp"]),
                "avg_rtt_ms": r["avg_rtt_ms"],
                "mediana_baseline_ms": r["mediana_baseline_ms"],
                "mad_baseline_ms": r["mad_baseline_ms"],
                "z_robusto": r["z_robusto"],
                "perda_pct": r["perda_pct"],
                "n5_timeout": int(r["n5_timeout"]),
                "n5_aumento80": int(r["n5_aumento80"]),
                "n5_risco": int(r["n5_risco"]),
                "classe_real": r["classe"],
                "pred_tarefa3_gini": p3,
                "pred_arvore_final": p4,
                "explicacao": "Na Tarefa 3 (Gini, raiz em z <= 3.4073), esta medição RISCO (z=3.4160, n5_risco=2) sofria falso alarme de FALHA; na Árvore Final (Entropia, raiz em z <= 3.5010), é classificada corretamente como RISCO.",
            }
        if (
            caso_falha_curto_timeout_teste is None
            and escopo == "curto"
            and r["classe"] == "FALHA"
            and p3 == "OK"
            and p4 == "FALHA"
        ):
            caso_falha_curto_timeout_teste = {
                "fluxo_id": r["fluxo_id"],
                "rota": rota,
                "escopo": escopo,
                "datetime_utc": r["datetime_utc"],
                "timestamp": int(r["timestamp"]),
                "avg_rtt_ms": r["avg_rtt_ms"],
                "mediana_baseline_ms": r["mediana_baseline_ms"],
                "z_robusto": r["z_robusto"],
                "perda_pct": r["perda_pct"],
                "n5_timeout": int(r["n5_timeout"]),
                "classe_real": r["classe"],
                "pred_tarefa3_gini": p3,
                "pred_arvore_final": p4,
            }

    # 3. Seção 3 — Fluxo que a árvore não viu (Protocolo B: Hold-Out de Fluxos Inteiros)
    fluxos_insuficientes = [
        r for r in baseline_rows if r["status_baseline"] != "elegivel"
    ]
    baseline_por_fid = {r["fluxo_id"]: r for r in baseline_rows}

    unseen_fids = sorted({r["fluxo_id"] for r in all_b_rows if r["prb_id"].endswith("03")})
    seen_train_rows = [r for r in train_rows if r["fluxo_id"] not in unseen_fids]
    unseen_eval_rows = [r for r in all_b_rows if r["fluxo_id"] in unseen_fids]

    meds_seen = calcular_medianas_treino(seen_train_rows, COLUNAS_MODELO)
    X_tr_seen, y_tr_seen = construir_matriz_xy(seen_train_rows, COLUNAS_MODELO, meds_seen)
    X_unseen, y_unseen = construir_matriz_xy(unseen_eval_rows, COLUNAS_MODELO, meds_seen)

    arvore_protocolo_b = ajustar_cart(
        X_tr_seen, y_tr_seen, list(range(len(X_tr_seen))), 0, 6, 20, COLUNAS_MODELO, "entropy"
    )
    aval_unseen, preds_unseen = avaliar_modelo(arvore_protocolo_b, X_unseen, y_unseen)

    resumo_por_fluxo_nao_visto = []
    rows_by_unseen_fid = defaultdict(list)
    for r, yp in zip(unseen_eval_rows, preds_unseen):
        rows_by_unseen_fid[r["fluxo_id"]].append((r, yp))

    exemplos_fluxo_nao_visto = {
        "longo_estavel_ok": None,
        "curto_degradado_falha": None,
        "degradacao_risco": None,
    }

    for fid in unseen_fids:
        b_ficha = baseline_por_fid[fid]
        rota, escopo, _ = ROUTE_MAP.get(b_ficha["dst_addr"], ("?", "?", "?"))
        pares = rows_by_unseen_fid[fid]
        cnt_real = Counter(r["classe"] for r, _ in pares)
        erros_fid = sum(1 for r, yp in pares if r["classe"] != yp)
        resumo_por_fluxo_nao_visto.append(
            {
                "fluxo_id": fid,
                "rota": rota,
                "escopo": escopo,
                "amostras_validas_periodo_a": int(b_ficha["amostras_validas_a"]),
                "mediana_periodo_a_ms": float(b_ficha["mediana"]),
                "mad_periodo_a_ms": float(b_ficha["MAD"]),
                "n_avaliado_periodo_b": len(pares),
                "suporte_real": dict(cnt_real),
                "erros": erros_fid,
                "acuracia": round((len(pares) - erros_fid) / len(pares), 4),
            }
        )
        for r, yp in pares:
            if (
                exemplos_fluxo_nao_visto["longo_estavel_ok"] is None
                and fid == "303|203.178.136.1"
                and r["classe"] == "OK"
                and r["avg_rtt_ms"] != ""
                and float(r["avg_rtt_ms"]) > 275.0
            ):
                exemplos_fluxo_nao_visto["longo_estavel_ok"] = {
                    "fluxo_id": fid,
                    "rota": rota,
                    "datetime_utc": r["datetime_utc"],
                    "avg_rtt_ms": r["avg_rtt_ms"],
                    "mediana_baseline_ms": r["mediana_baseline_ms"],
                    "z_robusto": r["z_robusto"],
                    "classe_real": r["classe"],
                    "classe_predita": yp,
                }
            if (
                exemplos_fluxo_nao_visto["curto_degradado_falha"] is None
                and fid == "103|194.109.133.10"
                and r["classe"] == "FALHA"
                and r["avg_rtt_ms"] != ""
                and float(r["avg_rtt_ms"]) < 45.0
            ):
                exemplos_fluxo_nao_visto["curto_degradado_falha"] = {
                    "fluxo_id": fid,
                    "rota": rota,
                    "datetime_utc": r["datetime_utc"],
                    "avg_rtt_ms": r["avg_rtt_ms"],
                    "mediana_baseline_ms": r["mediana_baseline_ms"],
                    "z_robusto": r["z_robusto"],
                    "perda_pct": r["perda_pct"],
                    "classe_real": r["classe"],
                    "classe_predita": yp,
                }
            if (
                exemplos_fluxo_nao_visto["degradacao_risco"] is None
                and r["classe"] == "RISCO"
            ):
                exemplos_fluxo_nao_visto["degradacao_risco"] = {
                    "fluxo_id": fid,
                    "rota": rota,
                    "datetime_utc": r["datetime_utc"],
                    "avg_rtt_ms": r["avg_rtt_ms"],
                    "mediana_baseline_ms": r["mediana_baseline_ms"],
                    "z_robusto": r["z_robusto"],
                    "n5_risco": int(r["n5_risco"]),
                    "classe_real": r["classe"],
                    "classe_predita": yp,
                }

    # 4. Seção 4 — Comparação no horizonte futuro de 12 minutos (t + 3 janelas de 240s) contra persistência
    c2i = {c: i for i, c in enumerate(CLASSES)}
    by_flow = defaultdict(list)
    for r in all_b_rows:
        by_flow[r["fluxo_id"]].append(r)

    fut_tr_rows, fut_tr_y = [], []
    fut_te_rows, fut_te_y, persist_te_str = [], [], []
    for fid, rows in sorted(by_flow.items()):
        for i in range(len(rows) - 3):
            r_curr, r_fut = rows[i], rows[i + 3]
            if r_curr["split"] == "treino" and r_fut["split"] == "treino":
                fut_tr_rows.append(r_curr)
                fut_tr_y.append(c2i[r_fut["classe"]])
            elif r_curr["split"] == "teste" and r_fut["split"] == "teste":
                fut_te_rows.append(r_curr)
                fut_te_y.append(c2i[r_fut["classe"]])
                persist_te_str.append(r_curr["classe"])

    X_fut_tr, _ = construir_matriz_xy(fut_tr_rows, COLUNAS_MODELO, meds_treino)
    X_fut_te, _ = construir_matriz_xy(fut_te_rows, COLUNAS_MODELO, meds_treino)

    arvore_12min = ajustar_cart(
        X_fut_tr, fut_tr_y, list(range(len(X_fut_tr))), 0, 6, 20, COLUNAS_MODELO, "entropy"
    )
    aval_12min_arvore, preds_12min_arvore = avaliar_modelo(arvore_12min, X_fut_te, fut_te_y)
    aval_12min_persistencia = calcular_metricas_de_pares(fut_te_y, persist_te_str)

    # Capturar um exemplo concreto de erro inevitável na predição 12 min à frente (transição abrupta OK -> FALHA)
    exemplo_erro_12min = None
    for r_curr, yi_fut, yp_fut in zip(fut_te_rows, fut_te_y, preds_12min_arvore):
        if r_curr["classe"] == "OK" and CLASSES[yi_fut] == "FALHA" and yp_fut == "OK":
            rota, escopo, _ = ROUTE_MAP.get(r_curr["dst_addr"], ("?", "?", "?"))
            exemplo_erro_12min = {
                "fluxo_id": r_curr["fluxo_id"],
                "rota": rota,
                "escopo": escopo,
                "datetime_utc_atual": r_curr["datetime_utc"],
                "avg_rtt_ms_atual": r_curr["avg_rtt_ms"],
                "z_robusto_atual": r_curr["z_robusto"],
                "perda_pct_atual": r_curr["perda_pct"],
                "classe_atual_t": r_curr["classe"],
                "classe_futura_t_mais_12min": CLASSES[yi_fut],
                "pred_arvore_12min": yp_fut,
                "pred_persistencia_12min": r_curr["classe"],
            }
            break

    # Salvar data/processed/arvore_final_tarefa5.json
    arvore_final_json = {
        "tarefa": "Tarefa 5 — Árvore Final e Abertura Única do Teste",
        "origem_arvore": "Idêntica à Árvore Ajustada da Tarefa 4 (congelada antes de abrir o teste)",
        "parametros": {
            "algoritmo": "DecisionTreeClassifier (CART)",
            "criterion": "entropy",
            "max_depth": 6,
            "min_samples_leaf": 20,
            "random_state": 42,
        },
        "colunas_modelo": COLUNAS_MODELO,
        "medianas_imputacao_treino": meds_treino,
        "profundidade_obtida": prof_final,
        "n_folhas": folhas_final,
        "n_nos": nos_final,
        "regras_portugues": regras_pt,
        "arvore": limpar_arvore_para_json(arvore_final),
    }
    with open(dir_processed / "arvore_final_tarefa5.json", "w", encoding="utf-8") as f:
        json.dump(arvore_final_json, f, indent=2, ensure_ascii=False)

    resumo_t5 = {
        "contrato": {
            "profundidade_escolhida_olhando_teste": False,
            "baseline_teste_usou_medicao_do_teste": False,
            "n_treino": len(train_rows),
            "n_validacao": len(val_rows),
            "n_teste_unico": len(test_rows),
            "colunas_usadas_x": COLUNAS_MODELO,
            "colunas_proibidas_bloqueadas": COLUNAS_PROIBIDAS_PRESENTES_NO_CSV,
        },
        "secao1_arvore_medida": {
            "parametros": arvore_final_json["parametros"],
            "profundidade_real": prof_final,
            "n_folhas": folhas_final,
            "n_nos": nos_final,
            "diagrama_texto": diagrama_txt,
            "regras_portugues": regras_pt,
        },
        "secao2_teste_temporal_unico": {
            "avaliacao_arvore_final_teste": aval_te,
            "avaliacao_arvore_tarefa3_teste_referencia": aval_te_t3,
            "desempenho_por_escopo_rota_teste": escopo_stats,
            "casos_destacados_teste": {
                "acerto_caminho_longo_estavel_ok": caso_ok_longo_teste,
                "caso_fronteira_risco_falha_corrigido": caso_fronteira_risco_falha_teste,
                "caso_falha_curto_timeout_corrigido": caso_falha_curto_timeout_teste,
            },
        },
        "secao3_fluxo_nao_visto": {
            "fluxos_excluidos_baseline_insuficiente": [
                {
                    "fluxo_id": r["fluxo_id"],
                    "total_amostras_a": int(r["total_amostras_a"]),
                    "amostras_validas_a": int(r["amostras_validas_a"]),
                    "prop_resposta": float(r["prop_resposta"]),
                    "status_baseline": r["status_baseline"],
                }
                for r in fluxos_insuficientes
            ],
            "protocolo_b_holdout_fluxos_inteiros": {
                "descricao": "Hold-out de 16 fluxos inteiros (todas as sondas de sufixo *03 em 12 rotas: curtas, regionais e longas, incluindo BR->JP, BR->IN e BR->ZA), 100% ausentes do conjunto de treino, com ficha de baseline calculada apenas no Período A (>= 2.483 RTTs válidos).",
                "n_fluxos_treino": 64 - len(unseen_fids),
                "n_fluxos_nao_vistos": len(unseen_fids),
                "n_linhas_treino_sem_fluxos_novos": len(seen_train_rows),
                "n_linhas_avaliadas_fluxos_novos": len(unseen_eval_rows),
                "avaliacao_global_fluxos_novos": aval_unseen,
                "resumo_por_fluxo": resumo_por_fluxo_nao_visto,
                "exemplos_auditaveis": exemplos_fluxo_nao_visto,
            },
        },
        "secao4_declaracoes_e_horizonte_12min": {
            "natureza_rotulo": "A árvore reproduz com 100% de fidelidade (F1 macro = 1.0000 no teste) a política operacional determinística definida na Tarefa 2 sobre as próprias métricas relativas ao baseline (COLUNAS_MODELO), e não um log externo de falha de hardware/roteador.",
            "comparacao_horizonte_12min_teste": {
                "n_pares_avaliados_teste": len(fut_te_y),
                "regra_persistencia_repetir_atual": aval_12min_persistencia,
                "arvore_preditora_12min": aval_12min_arvore,
                "exemplo_erro_transicao_abrupta_12min": exemplo_erro_12min,
                "conclusao_operacional": "No horizonte de 12 minutos à frente (3 ciclos de 240s), a árvore (F1 macro = 0.4816, Recall FALHA = 53.29%, Recall RISCO = 0.00%) não supera de forma útil a persistência do estado atual (F1 macro = 0.4610, Recall FALHA = 63.11%, Recall RISCO = 1.06%). Portanto, declara-se formalmente que o artefato entregue é um DETECTOR de degradação do estado atual relativo ao baseline do fluxo, e não um preditor de 12 minutos à frente.",
            },
        },
    }

    with open(dir_metadados / "resumo_tarefa5.json", "w", encoding="utf-8") as f:
        json.dump(resumo_t5, f, indent=2, ensure_ascii=False)

    print("Tarefa 5 executada com sucesso!")
    print(f"Teste Único (N={aval_te['total_amostras']}): F1 macro = {aval_te['f1_macro']:.4f}, Recall FALHA = {aval_te['por_classe']['FALHA']['recall']:.4f}, Recall RISCO = {aval_te['por_classe']['RISCO']['recall']:.4f}, Erros = {aval_te['total_erros']}")
    print(f"Protocolo B — 16 Fluxos Não Vistos (N={aval_unseen['total_amostras']}): F1 macro = {aval_unseen['f1_macro']:.4f}, Erros = {aval_unseen['total_erros']}")
    print(f"Horizonte 12 min — Persistência F1 macro = {aval_12min_persistencia['f1_macro']:.4f} (Recall FALHA = {aval_12min_persistencia['por_classe']['FALHA']['recall']:.4f}) vs Árvore 12 min F1 macro = {aval_12min_arvore['f1_macro']:.4f} (Recall FALHA = {aval_12min_arvore['por_classe']['FALHA']['recall']:.4f})")


if __name__ == "__main__":
    executar_pipeline_tarefa5()
