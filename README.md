# Memorando de Decisão — Fonte de Dados do Projeto

| Campo | Informação |
|---|---|
| Curso / Disciplina | Ciência da Computação |
| Projeto integrador | Preditor de Falha e Risco em Dispositivos de Rede |
| Orientador(a) | Andrea Ono Sakai |
| Data de entrega desta etapa | 08/09/2026 |
| Integrantes do grupo | Wendell Rodrigues Macedo, Vinicius Firmino Souto, Fernando Paiva Coelho, Joao Gustavo Sanches, Daniel Dias Paranhos |

---

## 1. Situação

A equipe precisa decidir se a próxima fase do projeto utilizará um dataset real já publicado ou a API do RIPE Atlas como fonte de dados, garantindo que sejam obtidas as métricas de latência, perda de pacotes e jitter necessárias para treinar, testar e validar o modelo de predição de falhas da rede.

## 2. Opção A — Dataset real

- **Origem / link:** Base de dados do SIMET — Sistema de Medição de Tráfego Internet, desenvolvido e mantido pelo NIC.br (Núcleo de Informação e Coordenação do Ponto BR). O portal disponibiliza bases de medições Web e Mobile para download.
- **Formato:** Os dados são disponibilizados em arquivos CSV, incluindo uma base das medições Web, uma base Mobile e um arquivo de dicionário dos dados.
- **Período coberto:** O portal do NIC.br utiliza, em suas visualizações públicas, informações dos últimos seis meses, reunindo mais de 5 milhões de medições realizadas pelo SIMET. A página de download não informa explicitamente o período histórico total existente dentro dos arquivos CSV.
- **Campos disponíveis:** As medições armazenam informações como horário da medição, operadora, tipo de dispositivo, localização aproximada, velocidade de download, latência, perda de pacotes e jitter. Essas três últimas métricas são diretamente compatíveis com os atributos necessários pelo projeto.
- **Licença de uso:** A página de disponibilização dos dados informa que o conteúdo do portal está sob licença Creative Commons Atribuição-CompartilhaIgual 4.0 Internacional (CC BY-SA 4.0), salvo quando houver restrições adicionais indicadas.

**Resumo do que foi encontrado:**
O SIMET é uma alternativa brasileira consolidada para obtenção de dados reais de qualidade de Internet, mantido e desenvolvido pelo NIC.br, fornecendo datasets estruturados com as variáveis exigidas pelo projeto.

## 3. Opção B — API do RIPE Atlas

- **Documentação consultada (link):** Documentação oficial da RIPE Atlas REST API v2.
- **Autenticação exigida:** Para criar novas medições, é necessário utilizar uma API Key com permissão para criação de medições, normalmente enviada no cabeçalho `Authorization`. Já a consulta de medições e resultados públicos pode ser feita sem autenticação.
- **Como se cria uma medição:** Uma medição é criada enviando uma requisição POST para `https://atlas.ripe.net/api/v2/measurements/`. No corpo da requisição são informados, em JSON, o tipo da medição (por exemplo, ping), o destino, a versão de IP, os probes que realizarão a medição e, opcionalmente, o período e a frequência da coleta.
- **Como se consultam os resultados:** Os resultados podem ser consultados por meio de uma requisição GET para `https://atlas.ripe.net/api/v2/measurements/{id}/results/`, substituindo `{id}` pelo identificador da medição. Também é possível filtrar os resultados por probes e por período de tempo. Medições públicas podem ser consultadas sem autenticação.

**Resumo do que foi encontrado:**
A API do RIPE Atlas permite criar medições de rede sob demanda usando probes distribuídos mundialmente. Para o projeto, pode ser criada uma medição do tipo ping, permitindo coletar dados reais de latência e perda de pacotes diretamente via API REST.

## 4. Comparação

| Critério | Opção A — Dataset real | Opção B — API RIPE Atlas |
|---|---|---|
| Controle sobre a coleta | Baixo — os dados já foram coletados e não é possível definir exatamente como cada medição foi realizada. | Alto — permite escolher o destino, os probes, o tipo de medição e a frequência da coleta. |
| Diversidade geográfica | Boa dentro do Brasil — o SIMET possui medições realizadas em diferentes regiões brasileiras. | Muito alta — possui probes distribuídos em diversos países e regiões do mundo. |
| Custo / complexidade de implementação | Baixo — basta baixar os dados em CSV, tratar e adaptar ao formato do projeto. | Médio — exige integração com a API, autenticação, configuração das medições e tratamento das respostas. |
| Tempo até os primeiros dados estarem disponíveis | Imediato — os dados já estão disponíveis para download e análise. | Maior — é necessário configurar a medição e aguardar a coleta e disponibilização dos resultados. |

## 5. Recomendação

Opção A — Dataset real do SIMET, por oferecer dados já disponíveis, com menor complexidade de implementação.

## 6. Justificativa

O dataset real do SIMET é a opção mais adequada porque os dados já estão prontamente disponíveis para uso, possuem métricas diretamente compatíveis com o projeto (latência, perda de pacotes e jitter) e exigem menor esforço de implementação. Em comparação, a API do RIPE Atlas oferece maior controle e diversidade geográfica, porém exige autenticação, configuração das medições e integração via API, aumentando a complexidade técnica e o tempo até a obtenção dos primeiros dados. Portanto, para esta etapa do projeto, o dataset do SIMET apresenta a melhor relação entre disponibilidade, facilidade de uso e compatibilidade com o modelo preditivo.

## 7. Riscos e limitações

O principal risco da opção escolhida é que a equipe não possui controle direto sobre a frequência e o método com que os dados foram coletados originalmente. Além disso, pode ser necessário tratar valores ausentes, filtrar registros ruidosos e adaptar os campos ao formato de schema exigido pelo projeto. Para mitigar esses riscos, o grupo realizará uma etapa prévia de limpeza e validação dos dados, selecionando apenas registros válidos contendo latência, perda de pacotes e jitter, convertendo o dataset para o padrão exigido pelo contrato de dados do projeto.

## 8. Contribuição Individual dos Integrantes

### Integrante 1 — Wendell Rodrigues Macedo
- **O que fez nesta etapa:** Pesquisei informações sobre o dataset real do SIMET, verificando as métricas disponíveis, como latência, perda de pacotes e jitter. Também analisei a compatibilidade desses dados com as necessidades do projeto e apresentei os principais pontos encontrados ao grupo.
- **Tempo dedicado (aprox.):** 2h30
- **Evidência da contribuição:** *(prints de conversas no grupo e histórico de commits no repositório)*

### Integrante 2 — Vinicius Firmino Souto
- **O que fez nesta etapa:** Pesquisei a documentação da API do RIPE Atlas, analisando como funciona a autenticação, a criação de medições e a consulta dos resultados. Também comparei a complexidade da API com a utilização de um dataset já disponível.
- **Tempo dedicado (aprox.):** 2h30
- **Evidência da contribuição:** *(prints de conversas no grupo e anotações técnicas compartilhadas)*

### Integrante 3 — Fernando Paiva Coelho
- **O que fez nesta etapa:** Realizei a comparação entre o dataset do SIMET e a API do RIPE Atlas considerando controle sobre a coleta, diversidade geográfica, complexidade de implementação e tempo para obtenção dos dados. Também participei da elaboração da recomendação e da justificativa final do memorando.
- **Tempo dedicado (aprox.):** 3h00
- **Evidência da contribuição:** *(documento compartilhado de rascunho e registros de reuniões do grupo)*

### Integrante 4 — Joao Gustavo Sanches
- **O que fez nesta etapa:** Analisei os riscos e limitações relacionados ao uso do dataset real do SIMET, identificando possíveis problemas como falta de controle sobre a coleta, necessidade de limpeza dos dados e adaptação dos campos ao formato definido pelo projeto. Também sugeri formas de reduzir esses riscos.
- **Tempo dedicado (aprox.):** 2h00
- **Evidência da contribuição:** *(registros de mensagens no grupo e trechos de análise de mitigação)*

### Integrante 5 — Daniel Dias Paranhos
- **O que fez nesta etapa:** Revisei as informações pesquisadas pelo grupo, conferi o preenchimento das seções do memorando e organizei as fontes utilizadas. Também revisei a recomendação e a justificativa para verificar se estavam de acordo com os resultados obtidos na pesquisa.
- **Tempo dedicado (aprox.):** 2h00
- **Evidência da contribuição:** *(histórico de edições do arquivo no repositório e validação final)*

---

## Fontes consultadas

1. NIC.br — Dados SIMET e informações sobre as métricas de qualidade da Internet: https://bandalarga.nic.br/
2. NIC.br — Documentação do SIMET sobre medições de latência, jitter e perda de pacotes: https://docs.medicoes.nic.br/simet-integrado/debian/periodicidade/
3. RIPE Atlas — Documentação oficial e visão geral: https://atlas.ripe.net/docs/
4. RIPE Atlas — Documentação oficial da API REST: https://atlas.ripe.net/docs/apis/
5. RIPE Atlas — Autenticação e uso de API Key: https://atlas.ripe.net/docs/apis/rest-api-manual/authentication/
6. RIPE Atlas — Criação de medições: https://atlas.ripe.net/docs/apis/rest-api-manual/measurements/creating-measurements/
7. RIPE Atlas — Consulta dos resultados das medições: https://atlas.ripe.net/docs/apis/rest-api-reference/measurements/measurements_results
