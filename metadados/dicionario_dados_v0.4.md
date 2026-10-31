# Dicionário de Dados v0.4 — Árvore Final, Teste Único e Model Card (Tarefa 5)

**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Equipe:** Grupo 42  
**Versão:** v0.4 (Versão Final Congelada — Alinhada às Colunas Consumidas pela Árvore Final na Tarefa 5)  
**Data de atualização:** 25/10/2026  

---

## 1. Registro de Evolução v0.3 → v0.4

Na Tarefa 5 (encerramento do ciclo), a Árvore Ajustada na Tarefa 4 (`DecisionTreeClassifier` CART com `criterion='entropy'`, `max_depth=6`, `min_samples_leaf=20`, `random_state=42`, `7` folhas) foi submetida à **abertura única do conjunto de teste temporal** (`data/processed/teste_periodo_b.csv`, `48.270` medições) e à **checagem em fluxos não vistos no treino** (Protocolo B, `16` fluxos completos das probes `*03`, `40.201` medições).

- **Congelamento estrito:** Nenhuma coluna nova foi adicionada ou removida entre a v0.3 e a v0.4. O vetor de entrada `X` permanece exatamente igual a `COLUNAS_MODELO` (8 variáveis relativas ao baseline do fluxo).
- **Imputação Causal Aprendida no Treino:** Nas medições com `timeout_atual = 1` (RTT ausente, nunca substituído por `0 ms`), os campos `z_robusto`, `aumento_pct` e `jitter_relativo` recebem exclusivamente as medianas aprendidas em `treino_periodo_b.csv` (`z_robusto = 0,2562`, `aumento_pct = 0,7357%`, `jitter_relativo = 1,0000`), sem qualquer vazamento do teste ou da validação.

---

## 2. Colunas Oficiais Consumidas pela Árvore Final (`COLUNAS_MODELO`)

| Ordem em `X` | Nome da Coluna | Tipo | Unidade / Escala | Fórmula Relativa ao Baseline doPeríodo A | Papel na Árvore Final (`entropy`, `max_depth=6`, `min_samples_leaf=20`, `7` folhas) |
|---:|---|---|---|---|---|
| 0 | `z_robusto` | `float64` | desvios robustos ($\sigma_{\text{rob}}$) | $\frac{\text{RTT}_{\text{atual}} - \text{mediana}_A}{1,4826 \times \text{MAD}_A}$ | **Nó Raiz (Nível 0: `<= 3,5010`)** para isolar desvios extremos imediatos (`FALHA`, Folha 7) e **Nível 4 (`<= 2,0003`)** para separar operação normal (`OK`, Folha 1) de desvios moderados (`> 2,0003`). |
| 1 | `aumento_pct` | `float64` | `%` | $\frac{\text{RTT}_{\text{atual}} - \text{mediana}_A}{\text{mediana}_A} \times 100$ | Compõe o vetor `X` e alimenta a janela causal `n5_aumento80` (saltos $> 80\%$ sobre a mediana do fluxo). |
| 2 | `jitter_relativo` | `float64` | razão adimensional | $\frac{\text{jitter}_{\text{atual}}}{\text{jitter\_tipico}_A}$ | Compõe o vetor `X` e alimenta a janela causal `n5_risco` (instabilidade $\ge 3\times$ o jitter típico do fluxo). |
| 3 | `perda_pct` | `float64` | `%` (`0` a `100`) | $\frac{\text{sent} - \text{rcvd}}{\text{sent}} \times 100$ | **Nível 1 (`<= 16,6650%`)** para classificar imediatamente como `FALHA` (Folha 6) qualquer perda de pacotes na rajada atual (`33,33%`, `66,67%` ou `100%`). |
| 4 | `timeout_atual` | `int64` | binário (`0` ou `1`) | `1` se RTT ausente ou `perda_pct == 100%`; senão `0` | Compõe o vetor `X`; capturado instantaneamente por `perda_pct > 16,6650%` e historicamente por `n5_timeout`. |
| 5 | `n5_timeout` | `int64` | contagem `[0, 5]` | $\sum_{k=0}^{4} \text{timeout\_atual}(t-k)$ no mesmo `fluxo_id` | **Nível 3 (`<= 2,5000`)** para classificar como `FALHA` (Folha 4) fluxos com $\ge 3$ timeouts nas últimas 5 medições (~20 min), mesmo quando o pacote atual responde sem perda. |
| 6 | `n5_aumento80` | `int64` | contagem `[0, 5]` | $\sum_{k=0}^{4} \mathbb{I}(\text{aumento\_pct}(t-k) > 80\%)$ | **Nível 2 (`<= 1,5000`)** para classificar como `FALHA` (Folha 5) degradações severas sustentadas ($\ge 2$ janelas com aumento $> 80\%$). |
| 7 | `n5_risco` | `int64` | contagem `[0, 5]` | $\sum_{k=0}^{4} \mathbb{I}(\text{cond\_risco}(t-k))$ | **Nível 5 (`<= 1,5000`)** para separar pico moderado isolado (`n5_risco <= 1` $\rightarrow$ `OK`, Folha 2) de degradação moderada persistente (`n5_risco >= 2` $\rightarrow$ `RISCO`, Folha 3). |

---

## 3. Alvo Supervisionado (`COLUNAS_ALVO`)

| Coluna | Tipo | Domínio | Proporção no Teste Único (`48.270` linhas) | Significado Operacional |
|---|---|---|---|---|
| `classe` | `string` | `OK`, `RISCO`, `FALHA` | `OK`: `28.303` (`58,63%`) \| `RISCO`: `189` (`0,39%`) \| `FALHA`: `19.778` (`40,97%`) | Estado operacional atual do fluxo relativo à sua própria ficha de baseline do Período A. Como verificado na Seção 4 da Tarefa 5, o entregável opera formalmente como **Detector do estado atual** (e não preditor de 12 minutos à frente). |

---

## 4. Colunas Bloqueadas na Árvore (`COLUNAS_PROIBIDAS`)

Auditadas programaticamente em `src/arvore_final.py` para garantir **interseção vazia** com `COLUNAS_MODELO`:
- **Identificadores topológicos e geográficos:** `pais`, `rota_id`, `escopo`, `fluxo_id`, `prb_id`, `dst_addr`.
- **Métricas de latência/jitter em milissegundos absolutos:** `avg_rtt_ms`, `min`, `max`, `jitter_ms`, `mediana_baseline_ms`, `mad_baseline_ms`, `jitter_tipico_ms`.
- **Metadados de controle e auditoria:** `timestamp`, `datetime_utc`, `sent`, `rcvd`, `ordem_regra`, `split`.
