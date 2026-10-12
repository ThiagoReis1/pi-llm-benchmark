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
├── submissions/                    # Entradas: respostas e códigos C coletados
├── tools/                          # Código gerador de tabelas e figuras
│   ├── generate_presentation.py
│   └── generate_scientific_figures.py
├── results/                        # Saídas geradas e evidências da rodada
│   ├── presentation/               # Tabelas LaTeX e figuras
│   └── logs/                       # Evidências individuais por execução
├── setup_project.py                # Inicialização e limpeza multiplataforma
├── run_benchmark.py                # Pipeline completo
├── requirements.txt
└── .gitignore
```

Os nomes dos módulos descrevem diretamente sua responsabilidade. Não há um segundo script que replique a preparação de respostas: `prepare_submission.py` concentra a transformação determinística e `prepare_interactive.py` fornece apenas a interface interativa.

## Requisitos e instalação

É necessário ter Python 3.11 ou superior e GCC com suporte a C11 (`gcc` no
Linux/WSL ou GCC/MinGW no Windows). O arquivo `setup_project.py` faz o restante:

1. cria `.venv` se o ambiente virtual ainda não existir;
2. instala `requirements.txt` dentro de `.venv`;
3. cria as pastas de `submissions/` e `results/`.

Se `.venv` já existir e contiver `pyvenv.cfg` e o executável Python, ele é
reutilizado; não é recriado a cada execução.

Em qualquer sistema, execute na raiz do projeto:

```bash
python setup_project.py
```

O script usa o Python do ambiente virtual para instalar as dependências e, ao
final, mostra o comando de ativação. Ele nunca abre uma nova sessão de
PowerShell ou Bash. Execute o comando mostrado no mesmo terminal para ativar o
ambiente.

Para remover somente o ambiente virtual, sem apagar código, submissões ou
resultados:

```bash
python setup_project.py --remove-venv
```

Para removê-lo e criá-lo novamente:

```bash
python setup_project.py --recreate-venv
```

Há duas limpezas de dados diferentes:

- `--clean-results`: remove os JSONs da rodada, `results/logs/`, tabelas
  e figuras geradas. Mantém `submissions/`, para repetir a análise dos mesmos
  códigos coletados.
- `--reset`: executa a limpeza completa: remove os resultados, todos os
  logs, tabelas, figuras e também as tentativas dentro de `submissions/`.

Portanto, os logs são apagados no `--reset`, pois eles ficam dentro de
`results/logs/`. Não existe uma opção separada para apagar somente submissões.

Os scripts de ativação são criados automaticamente pelo `venv` e usados pelo
próprio `setup_project.py`:

```text
Windows: .venv/Scripts/Activate.ps1
Linux/WSL: .venv/bin/activate
```

Como um processo Python não consegue alterar o shell pai, a ativação é feita
manualmente no terminal atual com o comando exibido pelo setup.

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

## Inicialização limpa e manutenção

A estrutura pode ser criada em Linux, macOS, WSL ou Windows PowerShell com o mesmo comando:

```bash
python setup_project.py
```

Para apagar somente os resultados gerados e começar uma nova rodada, preservando os códigos coletados:

```bash
python setup_project.py --clean-results
```

Para apagar resultados e também todas as tentativas coletadas:

```bash
python setup_project.py --reset
```

Sem ``, nenhuma operação destrutiva é executada. O script preserva as pastas-base e os arquivos `.gitkeep`.

## Execução do benchmark

### Qualquer sistema com Python e GCC

O mesmo comando é usado em Linux, macOS, WSL e Windows PowerShell:

```bash
python run_benchmark.py --repetitions 5 --timeout 20 --memory-mb 1024 --workers 4
```

O fluxo executa validação das submissões, testes automatizados, smoke test, benchmark completo, registro do ambiente da rodada e a geração da apresentação. Não são necessários scripts Bash ou PowerShell. Os geradores ficam em `tools/`; nenhum código gerador fica dentro de `results/`.

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

A pasta `results/presentation/` contém somente saídas geradas: tabelas LaTeX em `tables/`, figuras PNG/PDF em `figures/` e `presentation_manifest.json`. Todas as linhas das figuras e tabelas de resultados identificam método e arquivo de origem. Essa pasta é regenerada por `python tools/generate_presentation.py` e não deve conter código-fonte gerador nem ser preenchida manualmente.

O ranking exportado em `algorithm_ranking.json` é por método implementado, mantendo algoritmo e origem do arquivo em cada linha. Não é produzido ranking agregado por IA. O `.gitignore` ignora somente ambientes virtuais, caches, segredos locais e executáveis temporários. Portanto, os arquivos de `results/` e o restante da evidência experimental podem ser versionados normalmente.

## Convenções de código

- Python segue PEP 8 e usa docstrings em todos os módulos e funções;
- docstrings são escritas em português e descrevem o efeito observável da função;
- nomes de módulos, diretórios e arquivos são descritivos e estáveis;
- cada módulo possui uma responsabilidade principal;
- o código coletado em `submissions/` não deve ser editado manualmente;
- resultados devem ser regenerados pelos scripts em `tools/`, nunca alterados à mão;
- código gerador fica em `tools/`; `results/` contém somente saídas e evidências;
- novas alterações devem ser acompanhadas por testes quando modificarem o contrato.

## Reprodutibilidade e limitações

Para comparar rodadas, registre o prompt, a versão do compilador, o sistema operacional, os parâmetros do runner e as versões das plataformas. O ranking depende desses fatores e dos códigos efetivamente coletados.

O runner executa cada submissão em um processo separado, com timeout e limite de memória quando o sistema oferece suporte. Isso não constitui uma sandbox de segurança completa. Código não confiável deve ser executado em ambiente isolado, sem acesso à rede e com permissões restritas.

## Licença e autoria

Defina a licença e os dados de autoria antes da publicação pública no GitHub. As respostas de modelos de linguagem e os códigos coletados devem ser distribuídos somente quando isso for compatível com os termos das respectivas plataformas.
