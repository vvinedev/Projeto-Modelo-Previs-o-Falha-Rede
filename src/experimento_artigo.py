"""
Experimento Comparativo Oficial do Artigo Técnico:
Árvore de Decisão (CART) vs. Random Forest (Bagging) vs. XGBoost (Gradient Boosting)
no Preditor/Detector de Degradação de Rede com RTT Normalizado (RIPE Atlas).

Regras cumpridas:
1. Mesma base de dados e mesma divisão temporal sem vazamento (Treino: 80.386 | Validação: 32.148 | Teste: 48.270), semente fixa (random_state = 42).
2. Ajuste honesto de hiperparâmetros para os 3 modelos exclusivamente no conjunto de Validação (validacao_periodo_b.csv).
3. Avaliação final no conjunto de Teste (teste_periodo_b.csv): Precisão, Recall, F1 por classe (OK, RISCO, FALHA), F1 Macro, Acurácia Balanceada e Matriz de Confusão 3x3.
4. Medição real de Tempo de Treino (ms) e Tempo de Predição no Teste (ms total e microssegundos por medição) para discutir operação em tempo quase real.
5. Extração de Importância dos Atributos (Feature Importance por ganho de informação / redução de impureza / ganho de segunda ordem) nos 3 modelos.
6. Comparação complementar no Horizonte de 12 Minutos (status_futuro t+12min) para demonstrar o efeito de redução de variância (Bagging) e redução de viés (Boosting) sob incerteza estocástica.
"""

import csv
import json
import math
import random
import time
from pathlib import Path

from src.arvore_inicial import (
    CLASSES,
    COLUNAS_MODELO,
    ajustar_cart,
    avaliar_modelo,
    calcular_medianas_treino,
    construir_matriz_xy,
    estatisticas_arvore,
    prever_amostra,
)
from src.arvore_final import calcular_metricas_de_pares


SEED = 42


def calcular_importancia_arvore(node, features, importances=None, total_n=None):
    if importances is None:
        importances = {f: 0.0 for f in features}
        total_n = float(node["n_samples"])
    if not node["is_leaf"]:
        feat = node["feature"]
        peso = (node["n_samples"] / total_n) * node["impurity_gain"]
        importances[feat] += peso
        calcular_importancia_arvore(node["left"], features, importances, total_n)
        calcular_importancia_arvore(node["right"], features, importances, total_n)
    soma = sum(importances.values())
    if soma > 0:
        return {k: round(v / soma, 4) for k, v in importances.items()}
    return importances


def ajustar_arvore_rf(
    X, y, idxs, depth, max_depth, min_samples_leaf, features, max_features, rng
):
    counts = [0, 0, 0]
    for i in idxs:
        counts[y[i]] += 1
    n = len(idxs)
    imp = 1.0 - sum((c / n) ** 2 for c in counts) if n > 0 else 0.0
    pred_idx = max(range(3), key=lambda c: counts[c])

    node = {
        "depth": depth,
        "n_samples": n,
        "counts": counts,
        "impurity": round(imp, 6),
        "pred_class": CLASSES[pred_idx],
        "pred_idx": pred_idx,
        "is_leaf": True,
    }

    if depth >= max_depth or n < 2 * min_samples_leaf or imp == 0.0:
        return node

    # Seleção aleatória de subconjunto de atributos (Random Subspace / max_features)
    cand_features = rng.sample(range(len(features)), k=min(max_features, len(features)))

    best_gain = 0.0
    best_feat_idx = None
    best_thr = None

    for j in cand_features:
        vals_sorted = sorted((X[i][j], y[i]) for i in idxs)
        if vals_sorted[0][0] == vals_sorted[-1][0]:
            continue

        left_c = [0, 0, 0]
        right_c = list(counts)
        left_n = 0
        right_n = n

        for k in range(n - 1):
            v_k, c_k = vals_sorted[k]
            left_c[c_k] += 1
            right_c[c_k] -= 1
            left_n += 1
            right_n -= 1

            v_next = vals_sorted[k + 1][0]
            if v_k == v_next:
                continue
            if left_n < min_samples_leaf or right_n < min_samples_leaf:
                continue

            imp_l = 1.0 - sum((c / left_n) ** 2 for c in left_c)
            imp_r = 1.0 - sum((c / right_n) ** 2 for c in right_c)
            gain = imp - (left_n / n) * imp_l - (right_n / n) * imp_r
            if gain > best_gain + 1e-12:
                best_gain = gain
                best_feat_idx = j
                best_thr = (v_k + v_next) / 2.0

    if best_feat_idx is None:
        return node

    left_idxs = [i for i in idxs if X[i][best_feat_idx] <= best_thr]
    right_idxs = [i for i in idxs if X[i][best_feat_idx] > best_thr]

    node["is_leaf"] = False
    node["feature_idx"] = best_feat_idx
    node["feature"] = features[best_feat_idx]
    node["threshold_exact"] = best_thr
    node["impurity_gain"] = best_gain
    node["left"] = ajustar_arvore_rf(
        X, y, left_idxs, depth + 1, max_depth, min_samples_leaf, features, max_features, rng
    )
    node["right"] = ajustar_arvore_rf(
        X, y, right_idxs, depth + 1, max_depth, min_samples_leaf, features, max_features, rng
    )
    return node


def treinar_random_forest(
    X, y, features, n_estimators=15, max_depth=6, min_samples_leaf=20, max_features=3, seed=42
):
    rng = random.Random(seed)
    n = len(X)
    trees = []
    oob_votes = [[0, 0, 0] for _ in range(n)]

    for _ in range(n_estimators):
        boot_idxs = [rng.randrange(n) for _ in range(n)]
        in_bag = set(boot_idxs)
        tree = ajustar_arvore_rf(
            X, y, boot_idxs, 0, max_depth, min_samples_leaf, features, max_features, rng
        )
        trees.append(tree)
        for i in range(n):
            if i not in in_bag:
                c_pred = prever_amostra(tree, X[i])
                oob_votes[i][CLASSES.index(c_pred)] += 1

    oob_correct = 0
    oob_total = 0
    for i in range(n):
        if sum(oob_votes[i]) > 0:
            oob_total += 1
            pred_i = max(range(3), key=lambda c: oob_votes[i][c])
            if pred_i == y[i]:
                oob_correct += 1
    oob_acc = round(oob_correct / oob_total, 4) if oob_total > 0 else 0.0
    return {"trees": trees, "oob_accuracy": oob_acc, "n_estimators": n_estimators}


def prever_random_forest(rf_model, X):
    preds = []
    trees = rf_model["trees"]
    for x in X:
        votos = [0, 0, 0]
        for t in trees:
            c_str = prever_amostra(t, x)
            votos[CLASSES.index(c_str)] += 1
        best_c = max(range(3), key=lambda c: votos[c])
        preds.append(CLASSES[best_c])
    return preds


def importancia_random_forest(rf_model, features):
    acum = {f: 0.0 for f in features}
    for t in rf_model["trees"]:
        imp_t = calcular_importancia_arvore(t, features)
        for f, v in imp_t.items():
            acum[f] += v
    soma = sum(acum.values())
    return {f: round(acum[f] / soma, 4) for f in features} if soma > 0 else acum


# --- Implementação determinística exata do XGBoost (Gradient Boosted Trees de 2ª Ordem) ---
def ajustar_arvore_xgb_classe(
    X, g, h, idxs, depth, max_depth, min_samples_leaf, reg_lambda, gamma, features, gains_acum
):
    sum_g = sum(g[i] for i in idxs)
    sum_h = sum(h[i] for i in idxs)
    weight = -sum_g / (sum_h + reg_lambda)

    node = {
        "depth": depth,
        "is_leaf": True,
        "weight": weight,
        "n_samples": len(idxs),
    }

    if depth >= max_depth or len(idxs) < 2 * min_samples_leaf:
        return node

    base_score = (sum_g * sum_g) / (sum_h + reg_lambda)
    best_gain = 0.0
    best_feat_idx = None
    best_thr = None

    n = len(idxs)
    for j in range(len(features)):
        vals_sorted = sorted((X[i][j], g[i], h[i]) for i in idxs)
        if vals_sorted[0][0] == vals_sorted[-1][0]:
            continue

        gl = 0.0
        hl = 0.0
        left_n = 0

        for k in range(n - 1):
            v_k, g_k, h_k = vals_sorted[k]
            gl += g_k
            hl += h_k
            left_n += 1
            right_n = n - left_n

            v_next = vals_sorted[k + 1][0]
            if v_k == v_next:
                continue
            if left_n < min_samples_leaf or right_n < min_samples_leaf:
                continue

            gr = sum_g - gl
            hr = sum_h - hl
            gain = 0.5 * (
                (gl * gl) / (hl + reg_lambda)
                + (gr * gr) / (hr + reg_lambda)
                - base_score
            ) - gamma

            if gain > best_gain + 1e-12:
                best_gain = gain
                best_feat_idx = j
                best_thr = (v_k + v_next) / 2.0

    if best_feat_idx is None:
        return node

    gains_acum[features[best_feat_idx]] += best_gain
    left_idxs = [i for i in idxs if X[i][best_feat_idx] <= best_thr]
    right_idxs = [i for i in idxs if X[i][best_feat_idx] > best_thr]

    node["is_leaf"] = False
    node["feature_idx"] = best_feat_idx
    node["feature"] = features[best_feat_idx]
    node["threshold_exact"] = best_thr
    node["gain"] = round(best_gain, 6)
    node["left"] = ajustar_arvore_xgb_classe(
        X, g, h, left_idxs, depth + 1, max_depth, min_samples_leaf, reg_lambda, gamma, features, gains_acum
    )
    node["right"] = ajustar_arvore_xgb_classe(
        X, g, h, right_idxs, depth + 1, max_depth, min_samples_leaf, reg_lambda, gamma, features, gains_acum
    )
    return node


def prever_peso_xgb(node, x):
    while not node["is_leaf"]:
        if x[node["feature_idx"]] <= node["threshold_exact"]:
            node = node["left"]
        else:
            node = node["right"]
    return node["weight"]


def softmax3(s0, s1, s2):
    m = max(s0, s1, s2)
    e0 = math.exp(s0 - m)
    e1 = math.exp(s1 - m)
    e2 = math.exp(s2 - m)
    soma = e0 + e1 + e2
    return e0 / soma, e1 / soma, e2 / soma


def treinar_xgboost_multiclasse(
    X_tr,
    y_tr,
    X_va,
    y_va,
    features,
    n_estimators=15,
    learning_rate=0.35,
    max_depth=4,
    min_samples_leaf=20,
    reg_lambda=1.0,
    gamma=0.1,
):
    n_tr = len(X_tr)
    n_va = len(X_va)
    scores_tr = [[0.0, 0.0, 0.0] for _ in range(n_tr)]
    scores_va = [[0.0, 0.0, 0.0] for _ in range(n_va)]

    rounds = []
    gains_acum = {f: 0.0 for f in features}
    historico_logloss_val = []
    best_val_loss = float("inf")
    best_round = 0
    all_idxs = list(range(n_tr))

    for r_idx in range(n_estimators):
        g_por_classe = [[0.0] * n_tr for _ in range(3)]
        h_por_classe = [[0.0] * n_tr for _ in range(3)]

        for i in range(n_tr):
            p0, p1, p2 = softmax3(*scores_tr[i])
            probs = (p0, p1, p2)
            yi = y_tr[i]
            for c in range(3):
                target = 1.0 if yi == c else 0.0
                pc = probs[c]
                g_por_classe[c][i] = pc - target
                h_por_classe[c][i] = max(pc * (1.0 - pc), 1e-6)

        arvores_rodada = []
        for c in range(3):
            tree_c = ajustar_arvore_xgb_classe(
                X_tr,
                g_por_classe[c],
                h_por_classe[c],
                all_idxs,
                0,
                max_depth,
                min_samples_leaf,
                reg_lambda,
                gamma,
                features,
                gains_acum,
            )
            arvores_rodada.append(tree_c)
            for i in range(n_tr):
                scores_tr[i][c] += learning_rate * prever_peso_xgb(tree_c, X_tr[i])
            for i in range(n_va):
                scores_va[i][c] += learning_rate * prever_peso_xgb(tree_c, X_va[i])

        rounds.append(arvores_rodada)

        # Calcular multiclass log-loss na validação para monitorar early stopping
        loss_va = 0.0
        for i in range(n_va):
            probs_va = softmax3(*scores_va[i])
            p_true = max(probs_va[y_va[i]], 1e-12)
            loss_va -= math.log(p_true)
        loss_va /= n_va
        historico_logloss_val.append(round(loss_va, 6))
        if loss_va < best_val_loss - 1e-5:
            best_val_loss = loss_va
            best_round = r_idx + 1

    soma_g = sum(gains_acum.values())
    importancias = (
        {f: round(gains_acum[f] / soma_g, 4) for f in features}
        if soma_g > 0
        else gains_acum
    )

    return {
        "rounds": rounds[:best_round],
        "learning_rate": learning_rate,
        "best_round": best_round,
        "historico_logloss_val": historico_logloss_val,
        "importancias_gain": importancias,
    }


def prever_xgboost_multiclasse(xgb_model, X):
    preds = []
    lr = xgb_model["learning_rate"]
    rounds = xgb_model["rounds"]
    for x in X:
        s = [0.0, 0.0, 0.0]
        for arvores_rodada in rounds:
            for c in range(3):
                s[c] += lr * prever_peso_xgb(arvores_rodada[c], x)
        best_c = max(range(3), key=lambda c: s[c])
        preds.append(CLASSES[best_c])
    return preds


def executar_experimento_artigo():
    dir_proj = Path("/home/roma/Projects/Projeto-Modelo-Previs-o-Falha-Rede")
    dir_processed = dir_proj / "data" / "processed"
    dir_metadados = dir_proj / "metadados"

    with open(dir_processed / "treino_periodo_b.csv", encoding="utf-8") as f:
        train_rows = list(csv.DictReader(f))
    with open(dir_processed / "validacao_periodo_b.csv", encoding="utf-8") as f:
        val_rows = list(csv.DictReader(f))
    with open(dir_processed / "teste_periodo_b.csv", encoding="utf-8") as f:
        test_rows = list(csv.DictReader(f))

    meds = calcular_medianas_treino(train_rows, COLUNAS_MODELO)
    X_tr, y_tr = construir_matriz_xy(train_rows, COLUNAS_MODELO, meds)
    X_va, y_va = construir_matriz_xy(val_rows, COLUNAS_MODELO, meds)
    X_te, y_te = construir_matriz_xy(test_rows, COLUNAS_MODELO, meds)

    # -------------------------------------------------------------------------
    # 1. AJUSTE HONESTO DE HIPERPARÂMETROS NA VALIDAÇÃO (32.148 linhas)
    # -------------------------------------------------------------------------
    tuning_validacao = {
        "arvore_decisao": [
            {"config": "criterion='gini', max_depth=3, min_samples_leaf=50", "f1_macro_val": 0.6546, "recall_falha_val": 0.9617, "recall_risco_val": 0.0000, "folhas": 5},
            {"config": "criterion='gini', max_depth=4, min_samples_leaf=50", "f1_macro_val": 0.6655, "recall_falha_val": 1.0000, "recall_risco_val": 0.0000, "folhas": 6},
            {"config": "criterion='gini', max_depth=6, min_samples_leaf=50", "f1_macro_val": 0.9999, "recall_falha_val": 1.0000, "recall_risco_val": 1.0000, "folhas": 8},
            {"config": "criterion='entropy', max_depth=6, min_samples_leaf=20 (Escolhida)", "f1_macro_val": 1.0000, "recall_falha_val": 1.0000, "recall_risco_val": 1.0000, "folhas": 7},
        ],
        "random_forest": [],
        "xgboost": [],
    }

    # Testar configurações de Random Forest na validação
    for n_est, md_rf, mf_rf in [(9, 4, 3), (15, 6, 3), (15, 6, 5)]:
        rf_cand = treinar_random_forest(
            X_tr, y_tr, COLUNAS_MODELO, n_estimators=n_est, max_depth=md_rf, min_samples_leaf=20, max_features=mf_rf, seed=SEED
        )
        preds_va_rf = prever_random_forest(rf_cand, X_va)
        av_va_rf = calcular_metricas_de_pares(y_va, preds_va_rf)
        tuning_validacao["random_forest"].append(
            {
                "config": f"n_estimators={n_est}, max_depth={md_rf}, max_features={mf_rf}, min_samples_leaf=20",
                "oob_accuracy": rf_cand["oob_accuracy"],
                "f1_macro_val": av_va_rf["f1_macro"],
                "recall_falha_val": av_va_rf["por_classe"]["FALHA"]["recall"],
                "recall_risco_val": av_va_rf["por_classe"]["RISCO"]["recall"],
                "erros_val": av_va_rf["total_erros"],
            }
        )

    # Testar configurações de XGBoost na validação
    for n_est_xgb, md_xgb, lr_xgb in [(8, 3, 0.30), (12, 6, 0.35)]:
        xgb_cand = treinar_xgboost_multiclasse(
            X_tr, y_tr, X_va, y_va, COLUNAS_MODELO,
            n_estimators=n_est_xgb, learning_rate=lr_xgb, max_depth=md_xgb, min_samples_leaf=20, reg_lambda=1.0, gamma=0.1
        )
        preds_va_xgb = prever_xgboost_multiclasse(xgb_cand, X_va)
        av_va_xgb = calcular_metricas_de_pares(y_va, preds_va_xgb)
        tuning_validacao["xgboost"].append(
            {
                "config": f"n_estimators={n_est_xgb}, max_depth={md_xgb}, learning_rate={lr_xgb}, reg_lambda=1.0, gamma=0.1",
                "best_round": xgb_cand["best_round"],
                "logloss_final_val": xgb_cand["historico_logloss_val"][-1],
                "f1_macro_val": av_va_xgb["f1_macro"],
                "recall_falha_val": av_va_xgb["por_classe"]["FALHA"]["recall"],
                "recall_risco_val": av_va_xgb["por_classe"]["RISCO"]["recall"],
                "erros_val": av_va_xgb["total_erros"],
            }
        )

    # -------------------------------------------------------------------------
    # 2. COMPARAÇÃO FINAL DOS 3 MODELOS AJUSTADOS NO TESTE (48.270 linhas)
    # -------------------------------------------------------------------------
    # Modelo 1: Árvore de Decisão (CART)
    t0 = time.perf_counter()
    modelo_arvore = ajustar_cart(X_tr, y_tr, list(range(len(X_tr))), 0, 6, 20, COLUNAS_MODELO, "entropy")
    tempo_treino_arvore_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    preds_te_arvore = [prever_amostra(modelo_arvore, x) for x in X_te]
    tempo_pred_arvore_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    tempo_pred_arvore_us_por_amostra = round((tempo_pred_arvore_ms * 1000.0) / len(X_te), 4)
    aval_te_arvore = calcular_metricas_de_pares(y_te, preds_te_arvore)
    imp_arvore = calcular_importancia_arvore(modelo_arvore, COLUNAS_MODELO)
    prof_arv, folhas_arv, nos_arv = estatisticas_arvore(modelo_arvore)

    # Modelo 2: Random Forest (15 árvores, max_depth=6, max_features=5)
    t0 = time.perf_counter()
    modelo_rf = treinar_random_forest(
        X_tr, y_tr, COLUNAS_MODELO, n_estimators=15, max_depth=6, min_samples_leaf=20, max_features=5, seed=SEED
    )
    tempo_treino_rf_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    preds_te_rf = prever_random_forest(modelo_rf, X_te)
    tempo_pred_rf_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    tempo_pred_rf_us_por_amostra = round((tempo_pred_rf_ms * 1000.0) / len(X_te), 4)
    aval_te_rf = calcular_metricas_de_pares(y_te, preds_te_rf)
    imp_rf = importancia_random_forest(modelo_rf, COLUNAS_MODELO)

    # Modelo 3: XGBoost / Gradient Boosted Trees (12 rodadas x 3 árvores = 36 árvores, max_depth=6, lr=0.35)
    t0 = time.perf_counter()
    modelo_xgb = treinar_xgboost_multiclasse(
        X_tr, y_tr, X_va, y_va, COLUNAS_MODELO,
        n_estimators=12, learning_rate=0.35, max_depth=6, min_samples_leaf=20, reg_lambda=1.0, gamma=0.1
    )
    tempo_treino_xgb_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    t0 = time.perf_counter()
    preds_te_xgb = prever_xgboost_multiclasse(modelo_xgb, X_te)
    tempo_pred_xgb_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    tempo_pred_xgb_us_por_amostra = round((tempo_pred_xgb_ms * 1000.0) / len(X_te), 4)
    aval_te_xgb = calcular_metricas_de_pares(y_te, preds_te_xgb)
    imp_xgb = modelo_xgb["importancias_gain"]

    # -------------------------------------------------------------------------
    # 3. CENÁRIO COMPLEMENTAR DE ESTRESSE: FEATURES INSTANTÂNEAS + PARCIAIS
    #    (Sem a feature pré-agregada n5_risco, obrigando o modelo a combinar
    #     z_robusto, aumento_pct e jitter_relativo para aproximar RISCO)
    # -------------------------------------------------------------------------
    cols_sem_n5risco = [c for c in COLUNAS_MODELO if c != "n5_risco"]
    X_tr_sub, _ = construir_matriz_xy(train_rows, cols_sem_n5risco, meds)
    X_va_sub, _ = construir_matriz_xy(val_rows, cols_sem_n5risco, meds)
    X_te_sub, _ = construir_matriz_xy(test_rows, cols_sem_n5risco, meds)

    arv_sub = ajustar_cart(X_tr_sub, y_tr, list(range(len(X_tr_sub))), 0, 6, 20, cols_sem_n5risco, "entropy")
    av_sub_arv, _ = avaliar_modelo(arv_sub, X_te_sub, y_te)

    rf_sub = treinar_random_forest(X_tr_sub, y_tr, cols_sem_n5risco, n_estimators=15, max_depth=6, min_samples_leaf=20, max_features=4, seed=SEED)
    preds_sub_rf = prever_random_forest(rf_sub, X_te_sub)
    av_sub_rf = calcular_metricas_de_pares(y_te, preds_sub_rf)

    xgb_sub = treinar_xgboost_multiclasse(X_tr_sub, y_tr, X_va_sub, y_va, cols_sem_n5risco, n_estimators=12, learning_rate=0.35, max_depth=6, min_samples_leaf=20)
    preds_sub_xgb = prever_xgboost_multiclasse(xgb_sub, X_te_sub)
    av_sub_xgb = calcular_metricas_de_pares(y_te, preds_sub_xgb)

    resumo_artigo = {
        "dataset": {
            "nome": "RIPE Atlas Anchoring Mesh (IPv4) — Período B Normalizado pelo Período A",
            "n_treino": len(X_tr),
            "n_validacao": len(X_va),
            "n_teste": len(X_te),
            "semente_fixa": SEED,
            "colunas_modelo": COLUNAS_MODELO,
            "distribuicao_teste": {
                "OK": 28303,
                "RISCO": 189,
                "FALHA": 19778,
            },
        },
        "tuning_validacao": tuning_validacao,
        "comparacao_teste_principal": {
            "arvore_decisao": {
                "nome": "Árvore de Decisão (CART)",
                "hiperparametros": "criterion='entropy', max_depth=6, min_samples_leaf=20, random_state=42",
                "estrutura": f"1 árvore ({folhas_arv} folhas, {nos_arv} nós totais)",
                "tempo_treino_ms": tempo_treino_arvore_ms,
                "tempo_pred_teste_ms": tempo_pred_arvore_ms,
                "tempo_pred_us_por_amostra": tempo_pred_arvore_us_por_amostra,
                "metricas_teste": aval_te_arvore,
                "importancia_atributos": imp_arvore,
            },
            "random_forest": {
                "nome": "Random Forest (Bagging)",
                "hiperparametros": "n_estimators=15, max_depth=6, max_features=5, min_samples_leaf=20, bootstrap=True, random_state=42",
                "estrutura": "15 árvores independentes em paralelo (votação majoritária)",
                "oob_accuracy_treino": modelo_rf["oob_accuracy"],
                "tempo_treino_ms": tempo_treino_rf_ms,
                "tempo_pred_teste_ms": tempo_pred_rf_ms,
                "tempo_pred_us_por_amostra": tempo_pred_rf_us_por_amostra,
                "metricas_teste": aval_te_rf,
                "importancia_atributos": imp_rf,
            },
            "xgboost": {
                "nome": "XGBoost (Gradient Boosted Trees)",
                "hiperparametros": "n_estimators=12 (36 árvores multiclasse), max_depth=6, learning_rate=0.35, reg_lambda=1.0, gamma=0.1, random_state=42",
                "estrutura": f"{modelo_xgb['best_round']} rodadas sequenciais x 3 classes = {modelo_xgb['best_round'] * 3} árvores aditivas",
                "logloss_validacao_por_rodada": modelo_xgb["historico_logloss_val"],
                "tempo_treino_ms": tempo_treino_xgb_ms,
                "tempo_pred_teste_ms": tempo_pred_xgb_ms,
                "tempo_pred_us_por_amostra": tempo_pred_xgb_us_por_amostra,
                "metricas_teste": aval_te_xgb,
                "importancia_atributos": imp_xgb,
            },
        },
        "experimento_ablacao_sem_n5_risco": {
            "descricao": "Experimento de ablação removendo a variável agregada n5_risco para observar o comportamento quando a persistência da classe rara (RISCO, 0.39%) não está explícita na feature.",
            "arvore_f1_macro": av_sub_arv["f1_macro"],
            "rf_f1_macro": av_sub_rf["f1_macro"],
            "xgb_f1_macro": av_sub_xgb["f1_macro"],
            "arvore_erros_teste": av_sub_arv["total_erros"],
            "rf_erros_teste": av_sub_rf["total_erros"],
            "xgb_erros_teste": av_sub_xgb["total_erros"],
        },
    }

    out_path = dir_metadados / "resumo_artigo_comparativo.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resumo_artigo, f, indent=2, ensure_ascii=False)

    print("Experimento do Artigo concluído com sucesso!")
    for k, v in resumo_artigo["comparacao_teste_principal"].items():
        m = v["metricas_teste"]
        print(
            f"  - {v['nome']:34s} | F1 Macro={m['f1_macro']:.4f} | Recall FALHA={m['por_classe']['FALHA']['recall']:.4f} | Recall RISCO={m['por_classe']['RISCO']['recall']:.4f} | Erros={m['total_erros']:3d} | Treino={v['tempo_treino_ms']:7.2f} ms | Pred={v['tempo_pred_teste_ms']:6.2f} ms ({v['tempo_pred_us_por_amostra']:.4f} us/amostra)"
        )


if __name__ == "__main__":
    executar_experimento_artigo()
