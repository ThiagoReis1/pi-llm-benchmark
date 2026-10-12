# PI LLM Benchmark

Benchmark reprodutível para coletar, executar e avaliar implementações em C11 do cálculo de Pi geradas por modelos de linguagem.

O projeto trata cada arquivo `submission.c` como uma implementação independente. O mesmo nome de algoritmo pode aparecer em mais de uma plataforma, mas os resultados não são misturados: a implementação, a plataforma e a tentativa permanecem identificadas em todos os registros.

## Objetivos

- coletar respostas de diferentes modelos de linguagem usando um prompt único;
- preservar a resposta original e o código executável sem alterações manuais;
- verificar compilação e conformidade com o contrato C11;
- executar métodos para 1 a 18 casas decimais;
- medir correção, precisão, tempo, memória e robustez;
- gerar registros individuais, logs e relatórios reproduzíveis;
- manter separadas as evidências experimentais e as interpretações teóricas.

## Estrutura do projeto

```text
pi-llm-benchmark/
├── benchmark/
│   ├── algorithm_analysis.py       # Descrições teóricas e ajustes empíricos
│   ├── c_code_analysis.py          # Análise estática heurística de cada submission.c
│   ├── cases.json                  # Casos válidos e entradas inválidas
│   ├── reference.py                # Oráculo independente e métricas decimais
│   ├── runner.py                   # Compilação, execução, medição e agregação
│   └── test_benchmark_contract.py  # Testes do contrato e da infraestrutura
├── data_collection/
│   ├── prepare_interactive.py      # Coleta interativa de uma resposta
│   ├── prepare_submission.py       # Conversão determinística de uma resposta
│   └── example_metadata.json       # Exemplo do formato de metadados
├── prompts/
│   └── benchmark_prompt.txt         # Prompt oficial usado nas coletas
├── submissions/                    # Código e respostas coletadas por plataforma
├── results/                        # Dados brutos, tabelas, figuras e logs
│   ├── presentation/               # Tabelas LaTeX, figuras PNG e índice humano
│   └── logs/                       # Evidências individuais por execução
├── run_benchmark.py                # Pipeline completo, independente do sistema operacional
├── requirements.txt
└── .gitignore
```

Os nomes dos módulos descrevem diretamente sua responsabilidade. Não há um segundo script que replique a preparação de respostas: `prepare_submission.py` concentra a transformação determinística e `prepare_interactive.py` fornece apenas a interface interativa.

## Requisitos

- Python 3.11 ou superior;
- GCC com suporte a C11 (`gcc` no Linux/WSL ou GCC/MinGW no Windows);
- ambiente virtual Python recomendado;
- dependências de `requirements.txt`.

### Linux, macOS ou WSL

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip gcc
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows PowerShell

Instale Python e GCC/MinGW, garantindo que `gcc` esteja no `PATH`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Coleta de respostas

Use exatamente [`prompts/benchmark_prompt.txt`](prompts/benchmark_prompt.txt), em uma conversa nova para cada plataforma. O prompt solicita um programa C11 com cinco algoritmos declarados e uma interface de linha de comando padronizada.

Para usar a coleta interativa:

```bash
python data_collection/prepare_interactive.py
```

O programa cria, por plataforma e tentativa:

```text
submissions/<plataforma>/attempt_01/
├── response_original.txt
├── submission.c
└── metadata.json
```

A resposta original é preservada byte a byte. O código é extraído somente quando existe um único bloco bloco C, evitando que menus ou texto da interface sejam salvos como código.

## Testes

Execute os testes antes do benchmark completo:

```bash
python -m pytest -q
```

Os testes verificam o parser dos algoritmos, a cobertura de 1 a 18 casas, a métrica decimal, a flag específica do MinGW, a exclusão do tempo de compilação e a consolidação das repetições em um único desfecho por configuração. Divergências entre saídas repetidas são cobertas como instabilidade, não como votação por maioria.

## Execução do benchmark

### Qualquer sistema com Python e GCC

O mesmo comando é usado em Linux, macOS, WSL e Windows PowerShell:

```bash
python run_benchmark.py --repetitions 5 --timeout 20 --memory-mb 1024 --workers 4
```

O fluxo executa validação das submissões, testes automatizados, smoke test, benchmark completo, registro do ambiente da rodada. Não são necessários scripts Bash ou PowerShell.

Para uma execução rápida da infraestrutura:

```bash
python -m benchmark.runner --smoke --repetitions 1 --timeout 5 --memory-mb 512
```

Use `--allow-incomplete` somente para testar a infraestrutura. Uma rodada oficial deve conter uma tentativa completa por plataforma.

## Métricas e escopo

O runner compara a saída textual com um oráculo independente baseado em aritmética de precisão múltipla. Cada arquivo passa primeiro por um gate de compilação: se falhar, nenhum método daquele arquivo é executado e a falha é registrada uma vez. A unidade de correção é a configuração **método implementado (algoritmo + arquivo C) × precisão**: como a saída é determinística, cinco repetições idênticas contam como um único desfecho, não como cinco acertos ou erros. As repetições são mantidas para estimar o tempo; `time_seconds` começa depois da compilação e inclui somente a execução do processo C, sua inicialização e a captura da saída.

O objeto comparado é cada **método implementado**: algoritmo declarado + arquivo C de origem. Gráficos e tabelas apresentam uma linha própria para cada par método--arquivo, com o algoritmo em primeiro plano e a origem somente para distinguir códigos. Assim, dois métodos chamados `machin` em arquivos diferentes não são combinados. Não são produzidos scores ou ranking comparativo das IAs. Desfechos são contados uma vez por método--precisão; as medianas temporais usam as repetições. Uma submissão por origem tampouco permite inferir desempenho geral do modelo.

Os registros podem conter casas decimais corretas, erro absoluto e relativo, status, classe de falha, tempo, pico de memória residente, stdout e stderr completos, comandos de compilação e execução, hash do código-fonte e análise estática individual.

A análise em `c_code_analysis.py` é heurística e reprodutível. Ela extrai evidências como limites de laços, uso de `digits` ou `prec`, capacidade fixa de limbs e crescimento da representação. Ela não é uma prova formal de complexidade para C arbitrário.

## Resultados versionados

Os arquivos de `results/` são evidências da rodada executada e devem ser enviados ao GitHub junto com o código. Uma execução completa produz, entre outros:

```text
results/
├── results.json
├── algorithm_ranking.json   # uma linha por método implementado
├── individual_code_analysis.json
├── run_metadata.json
├── presentation/
│   ├── article_includes.tex
│   ├── tables/*.tex
│   ├── figures/*.png
│   └── presentation_manifest.json
└── logs/<plataforma>/<tentativa>/
```

Os logs individuais preservam comandos, saídas, tempos, códigos de retorno e evidências de cada execução. Resultados, rankings e logs não são ignorados pelo `.gitignore`.

A pasta `results/presentation/` contém uma camada de leitura humana gerada automaticamente a partir dos JSONs: tabelas LaTeX em `tables/`, incluindo `formula_catalog_chatgpt.tex`, `formula_catalog_claude.tex`, `formula_catalog_gemini.tex` e `formula_catalog_grok.tex` para copiar e colar no artigo, figuras PNG/PDF em `figures/` e `presentation_manifest.json`. Todas as linhas das figuras e tabelas de resultados identificam método e arquivo de origem, sem barras ou médias agregadas por IA. Desfechos são contados uma vez por método–precisão; as repetições aparecem somente nas medianas temporais. Logs e dados brutos históricos permanecem preservados. Essa pasta é regenerada por `python results/presentation/generate_presentation.py` e não deve ser preenchida manualmente.

O ranking exportado em `algorithm_ranking.json` é por método implementado, mantendo algoritmo e origem do arquivo em cada linha. Não é produzido ranking agregado por IA. O `.gitignore` ignora somente ambientes virtuais, caches, segredos locais e executáveis temporários. Portanto, os arquivos de `results/` e o restante da evidência experimental podem ser versionados normalmente.

## Convenções de código

- Python segue PEP 8 e usa docstrings em todos os módulos e funções;
- docstrings são escritas em português e descrevem o efeito observável da função;
- nomes de módulos, diretórios e arquivos são descritivos e estáveis;
- cada módulo possui uma responsabilidade principal;
- o código coletado em `submissions/` não deve ser editado manualmente;
- resultados devem ser regenerados pelo runner, nunca alterados à mão;
- novas alterações devem ser acompanhadas por testes quando modificarem o contrato.

## Reprodutibilidade e limitações

Para comparar rodadas, registre o prompt, a versão do compilador, o sistema operacional, os parâmetros do runner e as versões das plataformas. O ranking depende desses fatores e dos códigos efetivamente coletados.

O runner executa cada submissão em um processo separado, com timeout e limite de memória quando o sistema oferece suporte. Isso não constitui uma sandbox de segurança completa. Código não confiável deve ser executado em ambiente isolado, sem acesso à rede e com permissões restritas.

## Licença e autoria

Defina a licença e os dados de autoria antes da publicação pública no GitHub. As respostas de modelos de linguagem e os códigos coletados devem ser distribuídos somente quando isso for compatível com os termos das respectivas plataformas.
