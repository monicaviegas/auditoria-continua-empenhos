# Auditoria Contínua de Empenhos por Trilhas

Protótipo de painel que aplica a qualquer base de empenhos o protocolo de trilhas analíticas de Auditoria Contínua descrito na tese (Capítulo 4). O painel e sua verificação técnica são o produto do Capítulo 5.

**O problema.** O auditor dispõe de dados abertos com todos os empenhos de um órgão, mas não de um método padronizado que diga quais registros examinar primeiro. Analisada de uma só vez, a base mistura folha, transferências, compras e pagamentos a pessoas, e produz listas longas de sinais com pouca relevância.

**A proposta.** O painel recorta a base em trilhas pela natureza da despesa e aplica a cada trilha o teste que responde à sua pergunta de auditoria. Para cada trilha, devolve uma lista curta de registros priorizados, com o critério de cada sinal e os procedimentos de verificação correspondentes.

> Os resultados são sinais para priorizar exames. Não comprovam erro, fraude ou irregularidade.

## Trilhas e procedimentos

| Trilha | Pergunta | Procedimento |
|---|---|---|
| Base | O que a base permite analisar? Ela é consistente? A que trilha pertence cada linha? | T0 executabilidade · T1 qualidade · T2 recorte |
| Fornecedores | Que empenho tem valor incomum para o seu grupo? Que fornecedores concentram o gasto? | T3 escore robusto por estrato (GND × elemento × exercício) · T7 concentração |
| Pessoal | Que rubrica variou fora do padrão em um exercício? | T8 razão sobre a mediana dos demais exercícios |
| Pagamentos a pessoas | Quem acumulou valor atípico em uma rubrica e exercício? | T9 escore robusto do acumulado por beneficiário |
| Transversais | A distribuição de dígitos é conforme? Quando o gasto se concentra? Há linhas duplicadas? | T4 Benford · T5 temporal · T6 repetições |

O recorte usa apenas a classificação orçamentária (GND, elemento e modalidade de aplicação), presente em extrações federais, estaduais e municipais. As listas de elementos de cada trilha e os limiares ficam em [`config/params.yaml`](config/params.yaml). A matriz de procedimentos por trilha (questão, critério, informações requeridas, verificação e possíveis achados) fica em [`config/matriz_procedimentos.yaml`](config/matriz_procedimentos.yaml).

## Instalação

Requer Python 3.11 ou superior.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

## Uso do painel

```bash
streamlit run app_streamlit.py
```

1. **Base:** carregue um ou mais arquivos CSV ou Excel (por exemplo, um por exercício), ou use a base de demonstração (sintética).
2. **Perfil:** escolha um perfil pronto em `config/perfis/` (ex.: `siga_brasil`) ou associe as colunas da sua base aos campos do protocolo na própria tela. O mapeamento pode ser baixado como perfil e reutilizado.
3. **Parâmetros:** mantenha os valores-padrão ou ajuste os limiares e as listas de elementos.
4. **Executar protocolo.** Os resultados aparecem em abas: Visão geral, Trilhas, Fornecedores, Pessoal, Pagamentos a pessoas, Transversais e Exportar. Cada aba de trilha traz os procedimentos de verificação.

A aba **Exportar** fornece o relatório Excel (uma aba por procedimento), os metadados da execução (SHA-256 da entrada, versão, parâmetros, tempo e memória), o registro de exclusões e os parâmetros usados.

## Linha de comando (reprodutibilidade)

O mesmo motor roda sem o painel:

```bash
python -m protocolo_ac perfil --entrada base.xlsx                       # sugere o mapeamento de colunas
python -m protocolo_ac rodar  --entrada "dados/*.xlsx" --perfil config/perfis/siga_brasil.yaml
```

(com `src` no `PYTHONPATH`). Cada execução grava `outputs/run_<data>_<hash>/`. Mesma entrada e mesmos parâmetros produzem as mesmas saídas.

## Dados

O repositório não inclui bases de dados. Os dados do caso da tese são públicos e foram extraídos do [SIGA Brasil](https://www12.senado.leg.br/orcamento/sigabrasil) (Senado Federal). Qualquer extração de empenhos com exercício, valor empenhado, GND e elemento pode ser usada. Campos adicionais (número e data do empenho, favorecido, CNPJ/CPF, número do documento, modalidade de empenho) habilitam mais procedimentos, e o painel informa quais.

## Testes

```bash
pytest
```

Os testes geram uma base sintética com anomalias de resultado conhecido em cada trilha e verificam: as contagens de qualidade e de recorte; a recuperação das anomalias (T3 a T9); a igualdade de resultados entre formatos de origem diferentes; a executabilidade com campos ausentes; a reprodutibilidade; e a execução do painel de ponta a ponta.

## Limites

- Protótipo: não houve avaliação com usuários nem verificação documental dos sinais em dados reais.
- Execução em lote sobre arquivos carregados: não há coleta automática, execução periódica, alertas nem classificação de risco.
- Sem CNPJ/CPF, não é possível classificar exatamente os favorecidos nem calcular o índice de concentração sobre pessoas jurídicas. Na trilha de pagamentos a pessoas, a separação entre pessoas e pagamentos agregados (feitos em nome de unidades) usa uma regra declarada sobre o nome, que pode ser conferida na aba `T9_pagamentos_agregados`.
- Sem número de documento, não é possível verificar duplicidades por documento.

## Estrutura

```text
app_streamlit.py            painel
config/params.yaml          parâmetros do protocolo (trilhas e limiares)
config/matriz_procedimentos.yaml
config/perfis/              perfis de entrada (siga_brasil, generico)
src/protocolo_ac/           motor: t0_perfil … t9_pessoas, pipeline, relatório
tests/                      base sintética, avaliação técnica e teste do painel
```
