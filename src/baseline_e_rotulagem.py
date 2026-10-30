"""
Pipeline oficial da Tarefa 2 — Baseline do Fluxo e Rotulagem (OK, RISCO, FALHA)
Executa:
1. Auditoria da camada bruta (data/raw/ripe_atlas_14dias_20260920T043200Z.csv) e exportação para data/interim/df_bruto_auditado.csv
2. Cálculo da ficha de baseline congelada por fluxo exclusivamente no Período A (piso de 1.500 RTTs válidos) -> data/processed/baseline_por_fluxo.csv
3. Cálculo das 8 métricas relativas e janela causal de 5 medições no Período B
4. Rotulagem hierárquica sequencial (Ordens 1 a 6: FALHA > RISCO > OK)
5. Recorte temporal causal dentro do Período B por fluxo (50% Treino / 20% Validação / 30% Teste) -> data/processed/dataset_rotulado_periodo_b.csv e splits
"""

import csv
import json
import math
import statistics
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path


START_A = 1788669120  # 2026-09-06T04:32:00Z
STOP_A = 1789273920   # 2026-09-13T04:32:00Z
START_B = 1789273920  # 2026-09-13T04:32:00Z
STOP_B = 1789878720   # 2026-09-20T04:32:00Z
PISO_VALIDOS_A = 1500

# Mapa de metadados de rota apenas para auditoria (NUNCA entra nas colunas do modelo)
ROUTE_MAP = {
    "194.109.133.10": ("DE->DE", "curto"),
    "213.154.229.1": ("DE->DE", "curto"),
    "200.0.206.1": ("AR->AR", "curto"),
    "170.210.0.1": ("AR->AR", "curto"),
    "200.160.2.3": ("BR->BR", "curto"),
    "200.136.34.1": ("BR->BR", "curto"),
    "170.81.100.114": ("BR->BR_FAIL", "curto"),
    "200.40.0.1": ("BR->UY", "regional"),
    "179.31.0.1": ("BR->UY", "regional"),
    "193.136.0.1": ("DE->PT", "regional"),
    "194.65.0.1": ("DE->PT", "regional"),
    "212.191.0.1": ("ES->PL", "regional"),
    "148.81.0.1": ("ES->PL", "regional"),
    "196.200.0.1": ("ZA->KE", "regional"),
    "197.136.0.1": ("ZA->KE", "regional"),
    "202.157.0.1": ("IN->SG", "regional"),
    "165.21.0.1": ("IN->SG", "regional"),
    "200.87.0.1": ("BR->BO", "regional"),
    "190.181.0.1": ("BR->BO", "regional"),
    "203.178.136.1": ("BR->JP", "longo"),
    "133.242.0.1": ("BR->JP", "longo"),
    "14.139.0.1": ("BR->IN", "longo"),
    "218.248.0.1": ("BR->IN", "longo"),
    "196.24.0.1": ("BR->ZA", "longo"),
    "155.232.0.1": ("BR->ZA", "longo"),
}


def ts_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def calc_iqr(vals):
    if len(vals) < 4:
        return 0.0
    qs = statistics.quantiles(vals, n=4)
    return qs[2] - qs[0]


def executar_pipeline_tarefa2():
    dir_proj = Path("/home/roma/Projects/Projeto-Modelo-Previs-o-Falha-Rede")
    dir_raw = dir_proj / "data" / "raw"
    dir_interim = dir_proj / "data" / "interim"
    dir_processed = dir_proj / "data" / "processed"
    dir_metadados = dir_proj / "metadados"

    for d in [dir_interim, dir_processed, dir_metadados]:
        d.mkdir(parents=True, exist_ok=True)

    raw_csv = dir_raw / "ripe_atlas_14dias_20260920T043200Z.csv"
    interim_csv = dir_interim / "df_bruto_auditado.csv"

    # 1. Leitura e auditoria do bruto
    rows_by_flow = defaultdict(list)
    total_rows = 0
    null_avg_count = 0
    zero_avg_count = 0
    probes = set()
    dsts = set()
    seen_keys = set()
    dup_count = 0

    with open(raw_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames_raw = reader.fieldnames
        for row in reader:
            total_rows += 1
            ts = int(row["timestamp"])
            fid = row["fluxo_id"]
            probes.add(row["prb_id"])
            dsts.add(row["dst_addr"])
            key = (fid, ts)
            if key in seen_keys:
                dup_count += 1
            seen_keys.add(key)

            avg_str = row["avg"].strip()
            if avg_str == "":
                null_avg_count += 1
                avg_val = None
            else:
                avg_val = float(avg_str)
                if avg_val == 0.0:
                    zero_avg_count += 1

            jit_str = row["jitter_ms"].strip()
            jit_val = None if jit_str == "" else float(jit_str)

            row["_ts"] = ts
            row["_avg"] = avg_val
            row["_jit"] = jit_val
            row["_sent"] = int(row["sent"])
            row["_rcvd"] = int(row["rcvd"])
            row["_loss"] = float(row["perda_pct"])
            row["_timeout"] = int(row["timeout_atual"])
            rows_by_flow[fid].append(row)

    # Ordenar cada fluxo por timestamp e gravar data/interim/df_bruto_auditado.csv
    count_a = 0
    count_b = 0
    shared_ts_ab = 0

    with open(interim_csv, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(list(fieldnames_raw) + ["periodo"])
        for fid in sorted(rows_by_flow.keys()):
            rows_by_flow[fid].sort(key=lambda r: r["_ts"])
            ts_a = set()
            ts_b = set()
            for r in rows_by_flow[fid]:
                if r["_ts"] < STOP_A:
                    periodo = "A"
                    count_a += 1
                    ts_a.add(r["_ts"])
                else:
                    periodo = "B"
                    count_b += 1
                    ts_b.add(r["_ts"])
                writer.writerow([r[col] for col in fieldnames_raw] + [periodo])
            shared_ts_ab += len(ts_a.intersection(ts_b))

    # 2. Ficha de Baseline por Fluxo (somente Período A)
    baseline_records = []
    baseline_map = {}
    excluded_flows = []

    for fid in sorted(rows_by_flow.keys()):
        flow_rows = rows_by_flow[fid]
        rows_a = [r for r in flow_rows if r["_ts"] < STOP_A]
        total_a = len(rows_a)
        valid_rtts = [r["_avg"] for r in rows_a if r["_avg"] is not None and r["_timeout"] == 0]
        valid_jits = [r["_jit"] for r in rows_a if r["_jit"] is not None]
        all_losses = [r["_loss"] for r in rows_a]

        n_valid = len(valid_rtts)
        prop_resp = round(n_valid / total_a, 4) if total_a > 0 else 0.0
        prb_id, dst_addr = fid.split("|")
        rota_nome, escopo = ROUTE_MAP.get(dst_addr, ("DESCONHECIDA", "desconhecido"))

        if n_valid < PISO_VALIDOS_A:
            status_b = "baseline_insuficiente"
            rec = {
                "fluxo_id": fid,
                "prb_id": prb_id,
                "dst_addr": dst_addr,
                "total_amostras_a": total_a,
                "amostras_validas_a": n_valid,
                "prop_resposta": f"{prop_resp:.4f}",
                "mediana": "",
                "MAD": "",
                "IQR": "",
                "jitter_tipico": "",
                "perda_tipica": "",
                "status_baseline": status_b,
            }
            baseline_records.append(rec)
            excluded_flows.append((fid, total_a, n_valid, prop_resp, rota_nome))
        else:
            status_b = "elegivel"
            med = statistics.median(valid_rtts)
            abs_devs = [abs(x - med) for x in valid_rtts]
            mad = statistics.median(abs_devs)
            iqr = calc_iqr(valid_rtts)
            jit_tip = statistics.median(valid_jits) if valid_jits else 0.0
            perda_tip = statistics.median(all_losses) if all_losses else 0.0

            rec = {
                "fluxo_id": fid,
                "prb_id": prb_id,
                "dst_addr": dst_addr,
                "total_amostras_a": total_a,
                "amostras_validas_a": n_valid,
                "prop_resposta": f"{prop_resp:.4f}",
                "mediana": f"{med:.4f}",
                "MAD": f"{mad:.4f}",
                "IQR": f"{iqr:.4f}",
                "jitter_tipico": f"{jit_tip:.4f}",
                "perda_tipica": f"{perda_tip:.4f}",
                "status_baseline": status_b,
            }
            baseline_records.append(rec)
            baseline_map[fid] = {
                "mediana": med,
                "MAD": mad,
                "IQR": iqr,
                "jitter_tipico": jit_tip,
                "perda_tipica": perda_tip,
                "prop_resposta": prop_resp,
                "total_amostras_a": total_a,
                "amostras_validas_a": n_valid,
                "rota_auditoria": rota_nome,
                "escopo_auditoria": escopo,
            }

    baseline_cols = [
        "fluxo_id", "prb_id", "dst_addr", "total_amostras_a",
        "amostras_validas_a", "prop_resposta", "mediana", "MAD",
        "IQR", "jitter_tipico", "perda_tipica", "status_baseline"
    ]
    baseline_csv_path = dir_processed / "baseline_por_fluxo.csv"
    with open(baseline_csv_path, "w", newline="", encoding="utf-8") as f_b:
        w = csv.DictWriter(f_b, fieldnames=baseline_cols)
        w.writeheader()
        for r in baseline_records:
            w.writerow(r)

    # 3 e 4. Métricas Relativas no Período B + Rotulagem Hierárquica + 5. Recorte Temporal Causal
    labeled_rows_all = []
    class_counts = Counter()
    rule_counts = Counter()
    split_counts = defaultdict(Counter)
    split_totals = Counter()
    split_ts_bounds = {
        "treino": [None, None],
        "validacao": [None, None],
        "teste": [None, None],
    }

    # Comparação contra regra ingênua absoluta (RTT > 100 ms = FALHA, 50 < RTT <= 100 = RISCO, <= 50 = OK)
    abs_vs_rel = Counter()

    exemplos_auditaveis = {
        "ok_longo": None,
        "risco": None,
        "falha_curto": None,
        "falha_timeout": None,
        "pico_isolado_ok": None,
    }

    for fid in sorted(baseline_map.keys()):
        b_info = baseline_map[fid]
        med = b_info["mediana"]
        mad = b_info["MAD"]
        iqr = b_info["IQR"]
        jit_tip = b_info["jitter_tipico"]
        escopo = b_info["escopo_auditoria"]
        rota_nome = b_info["rota_auditoria"]

        rows_b = [r for r in rows_by_flow[fid] if r["_ts"] >= START_B]
        n_b = len(rows_b)
        idx_train_end = int(0.50 * n_b)
        idx_val_end = int(0.70 * n_b)

        win_timeout = deque(maxlen=5)
        win_aum80 = deque(maxlen=5)
        win_risco = deque(maxlen=5)

        for idx, r in enumerate(rows_b):
            ts = r["_ts"]
            sent = r["_sent"]
            rcvd = r["_rcvd"]
            perda_pct = round(((sent - rcvd) / sent) * 100.0, 2) if sent > 0 else 100.0
            avg_rtt = r["_avg"]
            jit_atual = r["_jit"]

            timeout_atual = 1 if (avg_rtt is None or perda_pct >= 100.0) else 0

            # z_robusto e aumento_pct
            if timeout_atual == 1 or avg_rtt is None:
                z_robusto = None
                aumento_pct = None
            else:
                aumento_pct = ((avg_rtt - med) / med) * 100.0
                if mad == 0.0:
                    if avg_rtt == med:
                        z_robusto = 0.0
                    else:
                        denom = max(iqr / 1.349, 1.0)
                        z_robusto = (avg_rtt - med) / denom
                else:
                    z_robusto = (avg_rtt - med) / (1.4826 * mad)

            # jitter_relativo
            if jit_atual is None:
                jitter_relativo = None
            else:
                if jit_tip == 0.0:
                    jitter_relativo = 1.0 if jit_atual == 0.0 else 3.0
                else:
                    jitter_relativo = jit_atual / jit_tip

            # Condição individual da linha 5 (critério de risco na medição atual)
            cond_risco_atual = False
            if z_robusto is not None and (2.0 <= z_robusto < 3.5):
                cond_risco_atual = True
            if aumento_pct is not None and (30.0 <= aumento_pct <= 80.0):
                cond_risco_atual = True
            if jitter_relativo is not None and (jitter_relativo >= 3.0):
                cond_risco_atual = True

            # Atualizar janelas causais das últimas 5 medições deste fluxo
            win_timeout.append(1 if timeout_atual == 1 else 0)
            win_aum80.append(1 if (aumento_pct is not None and aumento_pct > 80.0) else 0)
            win_risco.append(1 if cond_risco_atual else 0)

            n5_timeout = sum(win_timeout)
            n5_aumento80 = sum(win_aum80)
            n5_risco = sum(win_risco)

            # Tabela de rotulagem — parar na primeira linha verdadeira
            if perda_pct >= 10.0:
                classe = "FALHA"
                ordem_regra = "1_perda_pct>=10"
            elif n5_timeout >= 3:
                classe = "FALHA"
                ordem_regra = "2_n5_timeout>=3"
            elif z_robusto is not None and z_robusto >= 3.5:
                classe = "FALHA"
                ordem_regra = "3_z_robusto>=3.5"
            elif n5_aumento80 >= 2:
                classe = "FALHA"
                ordem_regra = "4_n5_aumento80>=2"
            elif cond_risco_atual and n5_risco >= 2:
                classe = "RISCO"
                ordem_regra = "5_risco_persistente"
            else:
                classe = "OK"
                ordem_regra = "6_ok"

            # Recorte temporal dentro de B por fluxo (50% / 20% / 30%)
            if idx < idx_train_end:
                split = "treino"
            elif idx < idx_val_end:
                split = "validacao"
            else:
                split = "teste"

            class_counts[classe] += 1
            rule_counts[ordem_regra] += 1
            split_counts[split][classe] += 1
            split_totals[split] += 1

            bounds = split_ts_bounds[split]
            if bounds[0] is None or ts < bounds[0]:
                bounds[0] = ts
            if bounds[1] is None or ts > bounds[1]:
                bounds[1] = ts

            # Comparação com regra absoluta ingênua (>100ms = FALHA)
            if timeout_atual == 1 or avg_rtt is None or avg_rtt > 100.0:
                abs_class = "FALHA_ABS"
            elif avg_rtt > 50.0:
                abs_class = "RISCO_ABS"
            else:
                abs_class = "OK_ABS"
            abs_vs_rel[(abs_class, classe)] += 1

            out_row = {
                "timestamp": ts,
                "datetime_utc": ts_to_iso(ts),
                "fluxo_id": fid,
                "prb_id": r["prb_id"],
                "dst_addr": r["dst_addr"],
                "sent": sent,
                "rcvd": rcvd,
                "avg_rtt_ms": "" if avg_rtt is None else f"{avg_rtt:.2f}",
                "jitter_ms": "" if jit_atual is None else f"{jit_atual:.2f}",
                "mediana_baseline_ms": f"{med:.4f}",
                "mad_baseline_ms": f"{mad:.4f}",
                "jitter_tipico_ms": f"{jit_tip:.4f}",
                "z_robusto": "" if z_robusto is None else f"{z_robusto:.4f}",
                "aumento_pct": "" if aumento_pct is None else f"{aumento_pct:.4f}",
                "jitter_relativo": "" if jitter_relativo is None else f"{jitter_relativo:.4f}",
                "perda_pct": f"{perda_pct:.2f}",
                "timeout_atual": timeout_atual,
                "n5_timeout": n5_timeout,
                "n5_aumento80": n5_aumento80,
                "n5_risco": n5_risco,
                "classe": classe,
                "ordem_regra": ordem_regra,
                "split": split,
            }
            labeled_rows_all.append(out_row)

            # Capturar exemplos auditáveis reais
            if (
                exemplos_auditaveis["ok_longo"] is None
                and classe == "OK"
                and escopo == "longo"
                and avg_rtt is not None
                and avg_rtt > 330.0
                and z_robusto is not None
                and abs(z_robusto) < 0.5
            ):
                exemplos_auditaveis["ok_longo"] = {**out_row, "rota": rota_nome, "escopo": escopo}

            if (
                exemplos_auditaveis["risco"] is None
                and classe == "RISCO"
                and z_robusto is not None
                and 2.0 <= z_robusto < 3.5
                and n5_risco >= 2
            ):
                exemplos_auditaveis["risco"] = {**out_row, "rota": rota_nome, "escopo": escopo}

            if (
                exemplos_auditaveis["falha_curto"] is None
                and classe == "FALHA"
                and escopo == "curto"
                and ordem_regra == "3_z_robusto>=3.5"
                and avg_rtt is not None
                and avg_rtt < 60.0
            ):
                exemplos_auditaveis["falha_curto"] = {**out_row, "rota": rota_nome, "escopo": escopo}

            if (
                exemplos_auditaveis["falha_timeout"] is None
                and classe == "FALHA"
                and ordem_regra == "1_perda_pct>=10"
                and timeout_atual == 1
                and n5_timeout >= 3
            ):
                exemplos_auditaveis["falha_timeout"] = {**out_row, "rota": rota_nome, "escopo": escopo}

            if (
                exemplos_auditaveis["pico_isolado_ok"] is None
                and classe == "OK"
                and z_robusto is not None
                and 2.1 <= z_robusto < 3.4
                and n5_risco == 1
            ):
                exemplos_auditaveis["pico_isolado_ok"] = {**out_row, "rota": rota_nome, "escopo": escopo}

    # Salvar dataset rotulado completo e splits
    cols_labeled = [
        "timestamp", "datetime_utc", "fluxo_id", "prb_id", "dst_addr",
        "sent", "rcvd", "avg_rtt_ms", "jitter_ms",
        "mediana_baseline_ms", "mad_baseline_ms", "jitter_tipico_ms",
        "z_robusto", "aumento_pct", "jitter_relativo", "perda_pct",
        "timeout_atual", "n5_timeout", "n5_aumento80", "n5_risco",
        "classe", "ordem_regra", "split"
    ]

    dataset_b_path = dir_processed / "dataset_rotulado_periodo_b.csv"
    train_path = dir_processed / "treino_periodo_b.csv"
    val_path = dir_processed / "validacao_periodo_b.csv"
    test_path = dir_processed / "teste_periodo_b.csv"

    with (
        open(dataset_b_path, "w", newline="", encoding="utf-8") as f_all,
        open(train_path, "w", newline="", encoding="utf-8") as f_tr,
        open(val_path, "w", newline="", encoding="utf-8") as f_val,
        open(test_path, "w", newline="", encoding="utf-8") as f_te,
    ):
        w_all = csv.DictWriter(f_all, fieldnames=cols_labeled)
        w_tr = csv.DictWriter(f_tr, fieldnames=cols_labeled)
        w_val = csv.DictWriter(f_val, fieldnames=cols_labeled)
        w_te = csv.DictWriter(f_te, fieldnames=cols_labeled)
        for w in (w_all, w_tr, w_val, w_te):
            w.writeheader()
        for row in labeled_rows_all:
            w_all.writerow(row)
            if row["split"] == "treino":
                w_tr.writerow(row)
            elif row["split"] == "validacao":
                w_val.writerow(row)
            else:
                w_te.writerow(row)

    # Resumo consolidado para exibição
    summary = {
        "bruto": {
            "total_linhas": total_rows,
            "total_fluxos": len(rows_by_flow),
            "total_probes": len(probes),
            "total_destinos": len(dsts),
            "duplicatas": dup_count,
            "avg_nulos": null_avg_count,
            "avg_zeros": zero_avg_count,
            "linhas_periodo_a": count_a,
            "linhas_periodo_b": count_b,
            "timestamps_compartilhados_ab": shared_ts_ab,
        },
        "baseline": {
            "fluxos_com_ficha": len(baseline_map),
            "fluxos_excluidos": len(excluded_flows),
            "detalhes_excluidos": excluded_flows,
            "exemplo_curto_ar": {
                "fluxo_id": "201|200.0.206.1",
                **baseline_map["201|200.0.206.1"],
            },
            "exemplo_curto_de": {
                "fluxo_id": "101|194.109.133.10",
                **baseline_map["101|194.109.133.10"],
            },
            "exemplo_longo_jp": {
                "fluxo_id": "301|203.178.136.1",
                **baseline_map["301|203.178.136.1"],
            },
            "exemplo_longo_za": {
                "fluxo_id": "301|196.24.0.1",
                **baseline_map["301|196.24.0.1"],
            },
        },
        "rotulagem_b": {
            "total_rotulado_b": len(labeled_rows_all),
            "linhas_excluidas_b": count_b - len(labeled_rows_all),
            "contagem_classes": dict(class_counts),
            "proporcao_classes_pct": {
                k: round((v / len(labeled_rows_all)) * 100.0, 2)
                for k, v in class_counts.items()
            },
            "contagem_regras": dict(rule_counts),
            "abs_vs_rel": {f"{k[0]}__{k[1]}": v for k, v in abs_vs_rel.items()},
            "exemplos_auditaveis": exemplos_auditaveis,
        },
        "splits": {
            s: {
                "total": split_totals[s],
                "proporcao_pct": round((split_totals[s] / len(labeled_rows_all)) * 100.0, 2),
                "inicio_utc": ts_to_iso(split_ts_bounds[s][0]),
                "fim_utc": ts_to_iso(split_ts_bounds[s][1]),
                "classes": dict(split_counts[s]),
                "classes_pct": {
                    c: round((cnt / split_totals[s]) * 100.0, 2)
                    for c, cnt in split_counts[s].items()
                },
            }
            for s in ["treino", "validacao", "teste"]
        },
    }

    summary_path = dir_metadados / "resumo_tarefa2.json"
    with open(summary_path, "w", encoding="utf-8") as f_sum:
        json.dump(summary, f_sum, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    executar_pipeline_tarefa2()
