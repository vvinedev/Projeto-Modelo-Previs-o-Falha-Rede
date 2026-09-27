# Diário da Tarefa 1 — Problema e coleta bruta (sem rótulo)

**Período:** 17/08/2026 a 17/09/2026  
**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Modelo desta disciplina:** árvore de decisão. Nesta tarefa não se treina árvore.

**Equipe:** Grupo 42  
**Integrantes:**  
- Wendell Rodrigues Macedo  
- Vinicius Firmino Solto  
- Fernando Paiva Coelho  
- João Gustavo Sanches  
- Daniel Dias Paranhos  
**Scrum Master da tarefa:** Vinicius Firmino Solto  
**Repositório GitHub:** [https://github.com/vini-wine-coder/Projeto-Modelo-Previs-o-Falha-Rede](https://github.com/vini-wine-coder/Projeto-Modelo-Previs-o-Falha-Rede)

> Esta tarefa entrega a contextualização do problema e a **ingestão do dado bruto**. Não há classe OK, RISCO ou FALHA. Não há baseline, não há mediana e não há árvore. Quem rotular aqui mistura a coleta com a decisão da Tarefa 2.
>
> A coleta foca na diversidade espacial das sondas (probes) mundiais medindo o mesmo destino. RTT alto por distância geográfica **não** é falha. País, IP e nome da sonda **não** serão atributos da futura árvore.

### Contrato desta tarefa

| | Artefato | Quem usa depois |
|---|---|---|
| **Entra** | Memorando de decisão de fontes de dados e especificações da disciplina | — |
| **Sai** | Notebook oficial executado ([`2_Coleta_de_dados.ipynb`](../2_Coleta_de_dados.ipynb)) com dados brutos | Tarefa 2 e avaliação docente |
| **Sai** | Arquivo de metadados da coleta ([`data/raw/ripe_atlas_m1001_20260916T015838Z_metadata.json`](../data/raw/ripe_atlas_m1001_20260916T015838Z_metadata.json)) | Tarefa 2 e repositório Git |
| **Sai** | Tríade de arquivos brutos preservada no ambiente (`.json`, `.csv`, `_metadata.json`) | Tarefa 2 **é obrigada a usar este bruto** |
| **Sai** | Este diário de bordo com as contribuições individuais e respostas à correção | Tarefas seguintes |

**Não sai daqui:** baseline, rótulo, `z_robusto`, split, árvore, métrica de modelo.

---

## 1. Definição do problema

| Pergunta | Resposta do grupo |
|---|---|
| Qual evento a árvore vai classificar? | Degradação do fluxo em relação ao **próprio** normal: OK, RISCO ou FALHA. Não é “rota longa” nem “RTT acima de 100 ms”. |
| O que é um fluxo? | `fluxo_id = probe_id \| dst_addr` (identificador da sonda de origem e endereço do servidor de destino). |
| O que é cada linha do bruto? | Uma resposta de medição ICMP desse fluxo, com timestamp UTC e granularidade de rajada (`sent`, `rcvd`, `result`). Ainda **sem** classe. |
| Qual horizonte fica para depois? | Detector: estado da medição atual. Preditor: estado em janelas futuras. A árvore só entra na Tarefa 3. |
| Quem usa o alerta? | Operadores de enlace/NOC: investigar (FALHA), observar (RISCO) ou não agir (OK). |
| O que está proibido como definição de falha? | Limiar global fixo de RTT (ex: > 100 ms), país, continente ou IP da rota. |

---

## 2. O que coletar (e o que não criar)

Fonte: Medição pública permanente *built-in* **1001** da API RIPE Atlas v2 (ping IPv4 até `k.root-servers.net` / `193.0.14.129`). A coleta foi executada exclusivamente via requisições HTTP `GET`, sem consumo de créditos e sem exposição de chaves privadas.

### Parâmetros Oficiais da Coleta
- `MEASUREMENT_ID = 1001` (ping IPv4 contínuo mundial para o K-Root Server)
- `HORAS_COLETA = 1` (janela móvel representativa de 1 hora)
- `TIMEOUT_REQUISICAO = 60` segundos
- `FORMATO_TABELAR = "csv"`
- **Janela temporal auditada (UTC):** `2026-09-16T00:58:30Z` até `2026-09-16T01:58:30Z`
- **Timestamp oficial dos arquivos:** `20260916T015838Z`

Cada registro bruto guarda, conforme retornado pela API:

| Campo | Unidade | Papel agora |
|---|---|---|
| `timestamp` | Unix / UTC | Ordenar temporalmente a série |
| `prb_id` | inteiro | Identificador único da sonda (origem) |
| `dst_addr` | IPv4 | Destino da medição (`193.0.14.129`) |
| `sent`, `rcvd` | contagem | Pacotes transmitidos e recebidos na rajada (típico: 3 pacotes) |
| `avg`, `min`, `max` | ms | RTT da rajada ICMP. Nulo se não houver resposta. **Nunca gravado como 0** |
| `result` | lista de objetos | RTT individual de cada pacote respondido |
| `step` | segundos | Frequência nominal da medição (240 s) |
| `af` | inteiro | Família de endereços (`4` para IPv4) |

### Regras de Governança e Decisões Técnicas
- [x] **Tríade de Salvamento:** Preservação do JSON íntegro original (`ripe_atlas_m1001_20260916T015838Z.json`, ~138,6 MB), da tabela normalizada em CSV (`ripe_atlas_m1001_20260916T015838Z.csv`, ~47,5 MB) e do arquivo de metadados (`ripe_atlas_m1001_20260916T015838Z_metadata.json`, 542 bytes).
- [x] **Tratamento de Anycast:** O destino `k.root-servers.net` utiliza roteamento anycast (múltiplas instâncias físicas globais anunciam `193.0.14.129`). Portanto, sondas em continentes distintos conectam-se a nós físicos diferentes. A análise é estritamente particionada por `prb_id|dst_addr`, impedindo comparações espúrias de RTT absoluto entre probes diferentes.
- [x] **Tratamento de Timeouts:** Timeouts e ausências de resposta permanecem com RTT vazio (`null`), sendo estritamente proibido imputar 0 ms para mascarar falhas de comunicação.
- [x] **Desacoplamento do SIMET:** A base SIMET do memorando da etapa preliminar serviu como estudo comparativo de viabilidade; a fonte oficial, auditável e padronizada para este projeto integrador é a API do RIPE Atlas.
- [x] **Metadados Versionados:** O arquivo `ripe_atlas_m1001_20260916T015838Z_metadata.json` está integrado ao repositório Git para garantir reprodutibilidade.

---

## 3. Relatório de qualidade — ainda sem classe

- [x] Status HTTP 200 verificado e auditado na execução
- [x] Contagem total de registros confirmada via `len(dados_json)` e `df_raw.shape`
- [x] Granularidade bruta inspecionada (`prb_id`, `sent`, `rcvd`, `result`)
- [x] Tipos de dados e valores ausentes verificados via `df_raw.info()`
- [x] Nenhuma coluna de classe (OK, RISCO, FALHA) atribuída nesta etapa

**Métricas Globais da Coleta:**
- **Nº de registros brutos recebidos:** 203.925 medições ICMP.
- **Dimensões do DataFrame:** 203.925 linhas × 25 colunas.
- **Destino monitorado:** `193.0.14.129` (`k.root-servers.net`).
- **Natureza da amostra:** Prova de conceito espacial de 1 hora com milhares de probes simultâneos distribuídos globalmente.
- **Cadência observada:** Intervalo nominal `step = 240s` (4 minutos) por sonda.
- **Integridade de armazenamento:** Integridade validada por testes com `assert` de existência de arquivos e checagem de tamanhos das saídas.

---

## 4. Scrum

- [x] **Product Owner:** Profa. Andréa Ono Sakai
- [x] **Scrum Master da tarefa:** Vinicius Firmino Solto
- [x] **Equipe de Desenvolvimento:** Wendell Rodrigues Macedo, Fernando Paiva Coelho, João Gustavo Sanches, Daniel Dias Paranhos
- [x] Board Kanban atualizado com histórias priorizadas e entregues

**Histórias de Usuário:**

1. **História 1 — Ingestão Confiável de Dados da Medição Pública 1001:**  
   *Como* desenvolvedor do sistema preditor,  
   *quero* consumir os resultados públicos da medição 1001 via API REST v2 do RIPE Atlas sem exigência de credenciais privadas ou créditos,  
   *para que* a equipe disponha de um volume expressivo de medições reais de ping IPv4 em nível mundial.  
   *Critérios de Aceitação:*  
   - Requisição realizada via HTTP GET com retorno status 200.  
   - Parâmetros centralizados em bloco de configuração (ID 1001, janela móvel de 1h UTC, timeout 60s).  
   - Retorno validado contendo 203.925 registros válidos.

2. **História 2 — Preservação Íntegra do Dado Bruto e Conversão Tabular:**  
   *Como* engenheiro de dados,  
   *quero* salvar o JSON original íntegro e convertê-lo em um DataFrame Pandas estruturado de 25 colunas,  
   *para que* os atributos brutos de latência e perda sejam preservados sem perda de granularidade e sem imputação artificial de zero para timeouts.  
   *Critérios de Aceitação:*  
   - JSON original armazenado sem truncamento (~138,6 MB).  
   - DataFrame com 203.925 linhas exibido e inspecionado via `df_raw.info()`.  
   - Campos de rajada (`sent`, `rcvd`, `result`) mantidos na camada bruta sem agregação prematura.

3. **História 3 — Reprodutibilidade, Auditoria e Versionamento de Metadados:**  
   *Como* analista de qualidade do projeto,  
   *quero* gerar e versionar no Git o arquivo de metadados da coleta junto com a documentação do repositório,  
   *para que* qualquer auditor docente possa rastrear a origem, timestamp, parâmetros e integridade da coleta realizada.  
   *Critérios de Aceitação:*  
   - Arquivo `_metadata.json` gerado com timestamp UTC oficial (`20260916T015838Z`) e salvo no Git.  
   - Notebook `2_Coleta_de_dados.ipynb` documentado com checklist completo e identificação unificada da Equipe 42.  
   - Contribuições individuais técnicas detalhadas e justificadas para cada membro.

---

## 5. Diário de bordo

| Integrante | O que fiz nesta tarefa | Dificuldades | O que pretendo manter/ajustar |
|---|---|---|---|
| **Vinicius Firmino Solto** (Scrum Master) | Coordenação do escopo da equipe, condução das discussões, elaboração da justificativa técnica da escolha do ping IPv4 na medição 1001 em relação ao memorando SIMET e preenchimento do checklist/resumo final. | Alinhar a escolha da fonte de dados mantendo o escopo restrito à ingestão bruta sem rotulagem prematura. | Manter a rotina de reuniões de alinhamento e garantir que os contratos de dados sejam seguidos na Tarefa 2. |
| **Wendell Rodrigues Macedo** | Configuração dos parâmetros de consulta da API RIPE Atlas (ID 1001, janela móvel de 1h em UTC e timeout de 60s), execução da requisição HTTP com validação do status 200 e versionamento do notebook no repositório GitHub. | Tratar as especificidades de formato temporal em UTC e garantir que a consulta retornasse status HTTP 200 estável. | Manter o controle de versão contínuo e a parametrização explícita para as próximas etapas. |
| **Fernando Paiva Coelho** | Recepção do payload JSON da API RIPE Atlas, validação estrutural dos dados brutos recebidos e implementação da conversão dos 203.925 registros em DataFrame do Pandas. | Normalizar a estrutura aninhada do JSON original da API sem perda de dimensionalidade de colunas. | Aprimorar as rotinas de tratamento tabular para as tabelas intermediárias da Tarefa 2. |
| **João Gustavo Sanches** | Inspeção de integridade dos dados brutos no DataFrame, análise dos tipos de colunas, contagem de registros e verificação da granularidade de medição (`prb_id`, `sent`, `rcvd`, `result`). | Evitar que campos nulos de timeout fossem incorretamente imputados como 0 ms durante a análise exploratória. | Automatizar checagens de consistência nos dados brutos antes de iniciar o cálculo do baseline. |
| **Daniel Dias Paranhos** | Desenvolvimento e execução da rotina de exportação dos arquivos da tríade (JSON original, CSV tabular e metadados da coleta) e implementação dos testes de validação com `assert` de existência e tamanho. | Assegurar que os arquivos gerados no Drive/ambiente contivessem nomenclatura rastreável e compatível entre si. | Padronizar as rotinas de exportação para que as tarefas seguintes gerem saídas auditáveis. |

---

## 6. Evidências gerais

- **Notebook Oficial da Coleta:** [`2_Coleta_de_dados.ipynb`](../2_Coleta_de_dados.ipynb)
- **Metadados Versionados da Ingestão:** [`data/raw/ripe_atlas_m1001_20260916T015838Z_metadata.json`](../data/raw/ripe_atlas_m1001_20260916T015838Z_metadata.json)
- **Memorando Prévio de Decisão:** [`README.md`](../README.md)
- **Parecer e Correção Docente Atendida:** [`Correcao_Grupo42.md`](../../Correcao_Grupo42.md)
- **Repositório GitHub Oficial:** [https://github.com/vini-wine-coder/Projeto-Modelo-Previs-o-Falha-Rede](https://github.com/vini-wine-coder/Projeto-Modelo-Previs-o-Falha-Rede)

---

## Rubrica — Tarefa 1 (0 a 4,0)

| Critério | Peso | Nota máxima | Autoavaliação / Justificativa |
|---|---|---|---|
| **Problema e Escopo** | 0,5 | 0,50 | Unidade de observação (`prb_id\|dst_addr`), granularidade de medição e proibição formal de RTT absoluto como falha estão explicitados no diário e no notebook. |
| **Coleta Bruta e Integridade** | 1,5 | 1,50 | Medição 1001 executada com HTTP 200 e 203.925 registros; tríade JSON/CSV/metadados íntegra; timeouts preservados sem imputação de 0 ms; anycast explicitado. |
| **Documentação e Decisões** | 1,0 | 1,00 | Janela temporal auditada (00:58 a 01:58 UTC de 16/09/2026), timestamp oficial unificado, papel do SIMET esclarecido e metadados anexados ao repositório. |
| **Scrum e Contribuições Individuais** | 1,0 | 1,00 | Papéis definidos (PO, SM, Devs), 3 histórias de usuário com critérios de aceitação e diário de bordo com contribuições técnicas individualizadas e verificáveis para os 5 integrantes. |
| **Total** | **4,0** | **4,00 / 4,00** | Entrega totalmente alinhada ao notebook executado e às orientações formativas da correção. |
