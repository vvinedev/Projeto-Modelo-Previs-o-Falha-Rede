# Quadro de Observação — Artigo Técnico: Árvore de Decisão, Random Forest e XGBoost

**Projeto:** Preditor de degradação de rede com RTT normalizado (independente da rota)  
**Disciplina:** Estrutura de Dados II — Profa. Dra. Andréa Ono Sakai  
**Equipe (Grupo 42):** Wendell Rodrigues Macedo, Vinicius Firmino Souto, Fernando Paiva Coelho, João Gustavo Sanches, Daniel Dias Paranhos  

---

## 1. Duas Referências Analisadas (da lista oficial do projeto)

| # | Referência Observada | Estilo | Elementos Observados e Por Que Funcionam |
|---|---|---|---|
| **1** | **ActiveState:** *Comparing Decision Tree Algorithms: Random Forest vs. XGBoost* (`https://www.activestate.com/blog/comparing-decision-tree-algorithms-random-forest-vs-xgboost/`) | Blog técnico de engenharia | **Progressão incremental de complexidade:** o texto começa pela intuição de uma única Árvore de Decisão (nós, folhas e *overfitting*), mostra por que combinar árvores em paralelo (*Bagging* / Random Forest) estabiliza a variância e, só então, introduz a correção sequencial de erros (*Boosting* / XGBoost). Funciona porque o leitor de TI nunca precisa dar um salto conceitual no escuro: cada modelo nasce de uma limitação concreta do modelo anterior. |
| **2** | **Chen & Guestrin (KDD 2016) + Documentação Oficial do XGBoost:** *XGBoost: A Scalable Tree Boosting System* (`https://arxiv.org/abs/1603.02754` e `https://xgboost.readthedocs.io/en/stable/tutorials/model.html`) | Artigo primário + Documentação oficial | **Separação em camadas entre intuição visual e formulação matemática:** a documentação oficial usa diagramas de árvores aditivas somando pontuações nas folhas antes de apresentar a função objetivo regularizada $\mathcal{L}^{(t)} = \sum_i l(y_i, \hat{y}_i^{(t-1)} + f_t(x_i)) + \Omega(f_t)$ com $\Omega(f) = \gamma T + \frac{1}{2}\lambda \sum w_j^2$. Funciona porque leitores práticos entendem imediatamente o papel do *shrinkage* ($\eta$) e da poda ($\gamma$), enquanto quem deseja rigor encontra a derivação de 2ª ordem ($g_i, h_i$) isolada em blocos específicos. |

---

## 2. Três Decisões Próprias do Grupo ("Vamos adotar X porque Y")

1. **Decisão 1 — Vamos adotar um exemplo concreto real de pacote ICMP (caminhos curtos de `14 ms` vs. transoceânicos de `340 ms`) antes de qualquer fórmula matemática porque o leitor de TI entende imediatamente o erro de um limiar fixo (`RTT > 100 ms`) antes de estudar Gini, Entropia, Bagging ou Boosting.**
   - *Como aparece na página:* abrimos a explicação da Árvore de Decisão percorrendo uma medição real do fluxo `301|14.139.0.1` (`BR -> IN`, `342,77 ms`, `z_robusto = 0,9347` $\rightarrow$ `OK`) e uma medição do fluxo `101|194.109.133.10` (`DE -> DE`, `31,62 ms`, `z_robusto = 20,37` $\rightarrow$ `FALHA`).

2. **Decisão 2 — Vamos adotar caixas recolhíveis/destacadas de "Aprofundamento Matemático" separadas do texto corrido porque isso mantém a leitura fluida para estudantes de TI e preserva o rigor de Estrutura de Dados II.**
   - *Como aparece na página:* no texto principal explicamos impureza, *bootstrap* e correção de resíduos com figuras SVG e analogias operacionais de NOC; logo abaixo de cada seção, incluímos a caixa formal com as equações de Entropia de Shannon ($H(S)$), erro *Out-of-Bag* e ganho de 2ª ordem de Chen & Guestrin ($\mathcal{G}_{\text{split}}$).

3. **Decisão 3 — Vamos adotar a medição empírica de latência de inferência em microssegundos por amostra ($\mu\text{s}$) ao lado do `F1 Macro` e do `Recall` da classe rara `RISCO` (`0,39%`) porque em telemetria de redes a escolha do modelo depende tanto de não perder incidentes quanto do custo computacional e da auditabilidade das regras.**
   - *Como aparece na página:* mostramos com dados do nosso experimento que, embora o **XGBoost** empate com a **Árvore de Decisão** em `F1 Macro = 1,0000` (enquanto a **Random Forest** cai para `F1 Macro = 0,7544` por diluir a classe rara `RISCO` no sorteio de `max_features`), a Árvore de Decisão simples de 7 folhas é **`42,5x` mais rápida na predição** (`0,1765` $\mu\text{s}$ vs `7,4960` $\mu\text{s}$) e **`100%` auditável** em 7 regras em português.

---

## 3. Uma Coisa que o Grupo Decidiu NÃO Fazer

- **O que decidimos NÃO fazer:** **Decidimos NÃO usar *Accuracy* (acurácia global) como critério de escolha do modelo e NÃO incluir variáveis de identificação geográfica (`pais`, `dst_addr`, `rota_id`) nem `avg_rtt_ms` bruto nos modelos.**
  - *Por que tomamos essa decisão:* no nosso conjunto de teste (`48.270` medições), a classe `RISCO` representa apenas `0,39%` (`189` amostras). A **Random Forest** obteve **`99,67%` de acurácia global**, mas errou **`84,66%` da classe `RISCO`** (`Recall de RISCO = 15,34%`, `F1 Macro = 0,7544`). Se escolhêssemos pela acurácia ou permitíssemos atalhos geográficos, ocultaríamos o colapso na classe minoritária e ensinaríamos os três modelos a decorar que "rota intercontinental para o Japão/Índia = FALHA", inutilizando o detector em produção.
