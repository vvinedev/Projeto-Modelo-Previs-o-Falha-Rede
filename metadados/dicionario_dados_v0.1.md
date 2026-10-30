# Dicionário de Dados v0.1 — Camada Bruta (Tarefa 1)

**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Equipe:** Grupo 42  
**Versão:** v0.1 (Ingestão Bruta — Sem Baseline e Sem Classe)  
**Origem:** API RIPE Atlas REST v2 (`GET`, ping IPv4, Anchoring Mesh / Medição 1001)

---

## 1. Esquema do Dado Bruto (`data/raw/ripe_atlas_14dias_20260920T043200Z.csv`)

| Coluna | Tipo | Unidade | Descrição | Regras de Integridade |
|---|---|---|---|---|
| `timestamp` | `int64` | Unix epoch (s) | Instante UTC da execução da rajada ICMP | Chave de ordenação temporal; sem duplicatas por `fluxo_id` |
| `msm_id` | `int64` | ID | Identificador da medição no RIPE Atlas (`1001`) | Constante da campanha de medição |
| `prb_id` | `int64` | ID | Identificador único da sonda de origem (*probe*) | 18 probes distribuídos em diferentes países |
| `dst_addr` | `string` | IPv4 | Endereço IPv4 do servidor/anchor de destino | 25 destinos IPv4 em 12 rotas geográficas |
| `fluxo_id` | `string` | `prb_id\|dst_addr` | Identificador único do par origem–destino | 67 fluxos monitorados ao longo de 14 dias |
| `sent` | `int64` | pacotes | Quantidade de pacotes ICMP enviados na rajada | Valor nominal igual a `3` |
| `rcvd` | `int64` | pacotes | Quantidade de pacotes ICMP respondidos na rajada | Inteiro no intervalo `[0, 3]` |
| `min` | `float64` | ms | Menor RTT observado entre os pacotes respondidos | Nulo (`NaN`) quando `rcvd = 0` (nunca `0.0`) |
| `max` | `float64` | ms | Maior RTT observado entre os pacotes respondidos | Nulo (`NaN`) quando `rcvd = 0` (nunca `0.0`) |
| `avg` | `float64` | ms | RTT médio da rajada ICMP (latência bruta atual) | Nulo (`NaN`) quando `rcvd = 0`. **Proibido gravar `0` para ausências** |
| `jitter_ms` | `float64` | ms | Dispersão intra-rajada dos RTTs respondidos | Nulo (`NaN`) quando `rcvd < 2` |
| `perda_pct` | `float64` | % | Percentual de perda na rajada: `(sent - rcvd) / sent * 100` | Valores observáveis em 3 pacotes: `0.0`, `33.33`, `66.67`, `100.0` |
| `timeout_atual` | `int64` | binário (`0`/`1`) | Indicador de ausência total de resposta na rajada | `1` se `avg` ausente ou `perda_pct = 100`; `0` caso contrário |
| `af` | `int64` | código | Família de endereços IP (`4` = IPv4) | Fixo em IPv4 (proibido misturar IPv6 na mesma coluna) |
| `step` | `int64` | segundos | Cadência nominal de amostragem do mesh | `240` segundos (4 minutos) |
| `proto` | `string` | texto | Protocolo utilizado na medição | `"ICMP"` |
