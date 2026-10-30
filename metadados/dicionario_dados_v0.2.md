# Dicionário de Dados v0.2 — Baseline por Fluxo, Métricas Relativas e Rótulo (Tarefa 2)

**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Equipe:** Grupo 42  
**Versão:** v0.2 (Congelamento do Baseline no Período A, Métricas Relativas e Rotulagem no Período B)  
**Data de atualização:** 30/09/2026  

---

## 1. Visão Geral das Tabelas na Versão v0.2

| Tabela / Artefato | Caminho | Linhas | Descrição |
|---|---|---|---|
| **Dado Bruto Auditado** | `data/interim/df_bruto_auditado.csv` | 336.326 | Série bruta dos 67 fluxos ordenada por `(fluxo_id, timestamp)` com marcação de período (`A` ou `B`), sem rótulo. |
| **Ficha de Baseline por Fluxo** | `data/processed/baseline_por_fluxo.csv` | 67 (64 elegíveis, 3 insuficientes) | Estatísticas robustas congeladas por `fluxo_id` calculadas **exclusivamente no Período A** (`2026-09-06T04:32:00Z` a `2026-09-13T04:32:00Z`). |
| **Dataset Rotulado do Período B** | `data/processed/dataset_rotulado_periodo_b.csv` | 160.804 | Medições do Período B (`2026-09-13T04:32:00Z` a `2026-09-20T04:32:00Z`) dos 64 fluxos elegíveis, enriquecidas com métricas relativas, rótulo (`OK`, `RISCO`, `FALHA`) e partição temporal (`treino`, `validacao`, `teste`). |

---

## 2. Ficha de Baseline (`data/processed/baseline_por_fluxo.csv`)

Calculada **somente** com medições do Período A e congelada. O Período B nunca atualiza esta tabela.

| Coluna | Tipo | Unidade | Fórmula / Definição (somente Período A) | Papel |
|---|---|---|---|---|
| `fluxo_id` | `string` | `prb_id\|dst_addr` | Chave identificadora única do fluxo | Chave primária da ficha (auditoria) |
| `prb_id` | `int64` | ID | Identificador da sonda de origem | Auditoria |
| `dst_addr` | `string` | IPv4 | Endereço IPv4 do destino | Auditoria |
| `total_amostras_a` | `int64` | contagem | Total de medições do fluxo no Período A | Auditoria de volume |
| `amostras_validas_a` | `int64` | contagem | Medições com RTT (`avg`) presente e `timeout_atual = 0` no Período A | Filtro de elegibilidade (piso ≥ 1.500) |
| `prop_resposta` | `float64` | proporção `[0, 1]` | `amostras_validas_a / total_amostras_a` | Cobertura de resposta no Período A |
| `mediana` | `float64` | ms | $\operatorname{mediana}(\text{RTT}_{\text{válidos em A}})$ | Referência central robusta de latência do fluxo (vazio se `< 1.500`) |
| `MAD` | `float64` | ms | $\operatorname{mediana}(\|\text{RTT}_{\text{válidos em A}} - \text{mediana}\|)$ | Dispersão robusta do RTT no Período A |
| `IQR` | `float64` | ms | $Q_{75}(\text{RTT}_{\text{válidos em A}}) - Q_{25}(\text{RTT}_{\text{válidos em A}})$ | Dispersão interquartil de reserva (usada se `MAD = 0`) |
| `jitter_tipico` | `float64` | ms | $\operatorname{mediana}(\text{jitter}_{\text{presente em A}})$ | Jitter normal de referência do fluxo |
| `perda_tipica` | `float64` | % | $\operatorname{mediana}(\text{perda\_pct}_{\text{todas em A, incl. timeout}})$ | Perda típica do fluxo no Período A |
| `status_baseline` | `string` | categoria | `"elegivel"` se `amostras_validas_a >= 1500`; `"baseline_insuficiente"` caso contrário | Governança (3 fluxos `170.81.100.114` excluídos sem inventar mediana) |

---

## 3. Métricas Relativas e Janela Causal no Período B (`COLUNAS_MODELO`)

Estas **8 colunas relativas** são as **únicas variáveis explicativas (features) permitidas** para treinar a árvore de decisão oficial a partir da Tarefa 3:

| Coluna (`COLUNAS_MODELO`) | Tipo | Unidade | Fórmula / Regra de Contagem | Tratamento de Casos Especiais |
|---|---|---|---|---|
| `z_robusto` | `float64` | adimensional ($\sigma_{\text{rob}}$) | $\dfrac{\text{RTT}_{\text{atual}} - \text{mediana}}{1{,}4826 \times \text{MAD}}$ | Se RTT ausente: `NaN` (não usar 0 ms). Se `MAD = 0` e `RTT = mediana`: `0`. Se `MAD = 0` e `RTT != mediana`: denominador = $\max(\text{IQR}/1{,}349,\; 1\text{ ms})$. |
| `aumento_pct` | `float64` | % | $\dfrac{\text{RTT}_{\text{atual}} - \text{mediana}}{\text{mediana}} \times 100$ | Se RTT ausente: `NaN`. |
| `jitter_relativo` | `float64` | razão adimensional | $\dfrac{\text{jitter}_{\text{atual}}}{\text{jitter\_tipico}}$ | Se jitter atual vazio: `NaN` (não dispara). Se `jitter_tipico = 0` e `jitter_atual = 0`: `1.0`. Se `jitter_tipico = 0` e `jitter_atual > 0`: `3.0` ($\ge 3$). |
| `perda_pct` | `float64` | % | $\dfrac{\text{sent} - \text{rcvd}}{\text{sent}} \times 100$ | Em rajada de 3 pacotes assume `0.0`, `33.33`, `66.67` ou `100.0`. |
| `timeout_atual` | `int64` | binário (`0`/`1`) | `1` se RTT ausente ou `perda_pct = 100`; senão `0` | Marca indisponibilidade na medição corrente. |
| `n5_timeout` | `int64` | contagem `[0, 5]` | Soma de `timeout_atual == 1` nas últimas 5 medições do fluxo (incluindo a atual) | Janela móvel causal restrita ao mesmo `fluxo_id` dentro de B. |
| `n5_aumento80` | `int64` | contagem `[0, 5]` | Quantas das últimas 5 medições do fluxo têm `aumento_pct > 80` | Janela móvel causal restrita ao mesmo `fluxo_id` dentro de B. |
| `n5_risco` | `int64` | contagem `[0, 5]` | Quantas das últimas 5 medições do fluxo cumprem `2 <= z_robusto < 3.5` OU `30 <= aumento_pct <= 80` OU `jitter_relativo >= 3` | Exige persistência (`n5_risco >= 2`) para consolidar a classe `RISCO`. |

---

## 4. Variável Alvo (Classe Supervisionada) e Metadados de Corte

| Coluna | Tipo | Valores Possíveis | Descrição |
|---|---|---|---|
| `classe` | `string` | `OK`, `RISCO`, `FALHA` | Variável alvo (target) definida pela aplicação sequencial estrita das Ordens 1 a 6 da Tabela de Rotulagem (`FALHA > RISCO > OK`). **Nunca entra como feature (`X`).** |
| `ordem_regra` | `string` | `1_perda_pct>=10`, `2_n5_timeout>=3`, `3_z_robusto>=3.5`, `4_n5_aumento80>=2`, `5_risco_persistente`, `6_ok` | Coluna de auditoria indicando qual linha exata da tabela disparou o rótulo. **Proibida como feature (`X`).** |
| `split` | `string` | `treino` (50%), `validacao` (20%), `teste` (30%) | Particionamento temporal causal dentro do Período B por fluxo (passado treina, meio valida, futuro recente testa). |

---

## 5. Colunas Estritamente Proibidas na Árvore Oficial (`COLUNAS_PROIBIDAS`)

Para garantir **independência geográfica e de rota** (evitando que o classificador decore endereços IP, países ou confunda distância física de cabos submarinos com falha de rede), as colunas abaixo permanecem **apenas para auditoria** e são **proibidas na matriz de entrada `X` da árvore oficial**:

| Coluna / Atributo Proibido | Motivo Técnico da Proibição |
|---|---|
| `pais` / `origem` / `destino` / `escopo` | Ensinaria geografia à árvore (ex.: classificar rotas transoceânicas `BR->JP`, `BR->IN` ou `BR->ZA` pelo continente). |
| `dst_addr` (Endereço IP de destino) | Atalho de memorização de rota/servidor; impede generalização para novos enlaces ou para o monitor local. |
| `prb_id` (ID da sonda) | Atalho de memorização do equipamento de origem. |
| `rota_id` | Identificador topológico direto da rota geográfica. |
| `fluxo_id` (`prb_id\|dst_addr`) | Identificador único do par origem–destino; causaria *overfitting* por memorização de fluxo. |
| `avg_rtt_ms`, `min`, `max` (RTT absoluto em ms) | **Proibido como substituto das métricas relativas:** mistura atraso físico de propagação na fibra com degradação operacional (ex.: 344 ms em `BR->ZA` é `OK`, enquanto 31 ms em `DE->DE` é `FALHA`). |
| `mediana_baseline_ms`, `mad_baseline_ms`, `jitter_tipico_ms` | Constantes fixas por fluxo que funcionariam como *proxy* direto do comprimento da rota (`fluxo_id`). |
| `timestamp`, `datetime_utc`, `msm_id`, `af`, `step`, `proto`, `ordem_regra`, `split` | Metadados de controle temporal, protocolo e auditoria do rótulo (vazamento de alvo se `ordem_regra` entrasse). |
