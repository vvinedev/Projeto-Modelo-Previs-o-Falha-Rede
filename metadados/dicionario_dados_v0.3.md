# Dicionário de Dados v0.3 — Auditoria de Atributos Relativos e Árvore Ajustada (Tarefa 4)

**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Equipe:** Grupo 42  
**Versão:** v0.3 (Ajuste da Árvore a partir do Erro da Tarefa 3 — Consolidação das Features Relativas)  
**Data de atualização:** 11/10/2026  

---

## 1. Registro de Evolução v0.2 → v0.3

Na Tarefa 4, investigou-se se a correção dos `634` erros da Árvore Inicial da Tarefa 3 (`500 FALHA -> OK`, `131 RISCO -> OK` e `3 OK -> FALHA`) exigia a criação de uma 9ª coluna relativa de tendência (`delta_z_robusto`) ou se as **8 colunas relativas originais (`COLUNAS_MODELO`)** já continham toda a informação causal necessária quando combinadas com o ajuste estrutural da árvore (`criterion = 'entropy'`, `max_depth = 6`, `min_samples_leaf = 20`).

| Atributo Avaliado na Tarefa 4 | Fórmula Causal (Restrita ao Mesmo `fluxo_id`) | Status Final em `COLUNAS_MODELO` | Justificativa Técnica |
|---|---|---|---|
| `delta_z_robusto` *(candidata testada)* | $z_{\text{robusto}}(t) - z_{\text{robusto}}(t-1)$ | **Descartada por parcimônia** | Ao ajustar a árvore para `criterion='entropy'`, `max_depth=6` e `min_samples_leaf=20`, a árvore usando exclusivamente as 8 colunas originais já atingiu `F1 macro = 1,0000` (`0` erros na validação) com `7` folhas 100% puras, sem selecionar `delta_z_robusto` em nenhum nó. |
| `COLUNAS_MODELO` *(8 colunas da v0.2)* | `z_robusto`, `aumento_pct`, `jitter_relativo`, `perda_pct`, `timeout_atual`, `n5_timeout`, `n5_aumento80`, `n5_risco` | **Mantidas e congeladas para a Tarefa 5** | Suficientes para representar desvio instantâneo, perda, indisponibilidade e persistência temporal de 5 janelas (~20 min) sem depender da rota. |

---

## 2. Colunas Oficiais Consumidas pela Árvore Ajustada (`COLUNAS_MODELO`)

| Ordem em `X` | Coluna | Tipo | Unidade | Papel Real nos Nós da Árvore Ajustada (`entropy`, `max_depth=6`, `min_samples_leaf=20`) |
|---:|---|---|---|---|
| 0 | `z_robusto` | `float64` | $\sigma_{\text{rob}}$ | **Usada no Nível 0 (Raiz: `<= 3,5010`)** para isolar desvios extremos imediatos (`FALHA`) e **no Nível 4 (`<= 2,0003`)** para filtrar desvios moderados candidatos a `RISCO`. |
| 1 | `aumento_pct` | `float64` | % | Mantida no vetor `X`; correlacionada com `z_robusto` e sintetizada temporalmente em `n5_aumento80`. |
| 2 | `jitter_relativo` | `float64` | razão | Mantida no vetor `X`; participa da janela de instabilidade capturada por `n5_risco`. |
| 3 | `perda_pct` | `float64` | % | **Usada no Nível 1 (`<= 16,6650%`)** para isolar perda de pacotes na rajada atual (`33,33%`, `66,67%` e `100%` $\rightarrow$ `FALHA`). |
| 4 | `timeout_atual` | `int64` | `0`/`1` | Mantida no vetor `X`; coberta instantaneamente por `perda_pct = 100%` e historicamente por `n5_timeout`. |
| 5 | `n5_timeout` | `int64` | `[0, 5]` | **Usada no Nível 3 (`<= 2,5000`)** — introduzida pelo ajuste da Tarefa 4 para eliminar os `500` falsos negativos de `FALHA` por timeouts persistentes. |
| 6 | `n5_aumento80` | `int64` | `[0, 5]` | **Usada no Nível 2 (`<= 1,5000`)** para capturar degradação severa sustentada (`aumento_pct > 80%` em $\ge 2$ das últimas 5 janelas $\rightarrow$ `FALHA`). |
| 7 | `n5_risco` | `int64` | `[0, 5]` | **Usada no Nível 5 (`<= 1,5000`)** — introduzida pelo ajuste da Tarefa 4 para separar pico moderado isolado (`OK`) de risco persistente (`RISCO`), elevando o Recall de `RISCO` de `0%` para `100%`. |

---

## 3. Governança de Colunas Proibidas (`COLUNAS_PROIBIDAS`)

Permanecem **estritamente bloqueadas** na Tarefa 4 e na futura Tarefa 5 todas as variáveis de identificação topológica, geográfica ou de latência bruta em milissegundos:
- `pais`, `rota_id`, `escopo`, `fluxo_id`, `prb_id`, `dst_addr`
- `avg_rtt_ms`, `min`, `max`, `jitter_ms`, `mediana_baseline_ms`, `mad_baseline_ms`, `jitter_tipico_ms`
- `timestamp`, `datetime_utc`, `sent`, `rcvd`, `ordem_regra`, `split`
