# Reprodução do artigo

Este repositório contém os artefatos usados pelo manuscrito corrigido. O
snapshot permite reproduzir a avaliação dos códigos preservados; ele não
reproduz a geração original das respostas dos assistentes.

- Snapshot dos dados: `v1.2`
- Commit dos dados: `8b256725a24122c3c8d4fe7950d2da110d279a69`
- Esta atualização acrescenta somente documentação; não altera os dados experimentais.
- Prompt SHA-256: `24176b7827151e9ba319e3ea05a0b33403d8a3e43556896356cf3cd583b2133d`
- Unidade experimental: implementação (algoritmo + arquivo C) × precisão
- Respostas preservadas: quatro assistentes, uma tentativa por assistente
- Configurações decimais únicas: 360

## Decisão de amostragem e interpretação

Foi mantida deliberadamente uma única resposta por assistente devido ao tempo
disponível para este estudo. As cinco implementações dentro de uma resposta não
são observações independentes. Portanto, as proporções são descritivas das 20
implementações preservadas: não há `pass@k`, intervalos de confiança, testes de
hipótese ou ranking de modelos. Como o prompt deixa cada assistente escolher os
métodos, origem, método e decisão de implementação também não são fatores
isolados. A justificativa completa está em
[`protocolo/decisoes_metodologicas.md`](protocolo/decisoes_metodologicas.md).

## Verificação rápida

Na raiz do projeto:

```bash
python -m pytest -q
python tools/verify_article_claims.py .
```

O verificador consolida as cinco repetições de cada configuração e confere os totais publicados no artigo: 360 configurações, 268 corretas, 74 incorretas, 18 falhas de execução, 14 implementações perfeitas, 74 configurações reparadas em D1/D3, 13 de 19 concordâncias na QP4 e 15 de 19 vereditos iguais entre `gcov -O0` e a medição de instruções em `-O2`.

## Reprodução completa

Para preparar o ambiente e executar uma rodada nova:

```bash
python setup_project.py
python -m pytest -q
python run_benchmark.py --repetitions 5 --timeout 20 --memory-mb 1024 --workers 4
```

Uma rodada nova não deve sobrescrever os resultados versionados sem criar antes uma nova pasta ou branch. Os arquivos `results/` do snapshot são as evidências da rodada descrita no artigo; a execução nova serve para testar a infraestrutura, não para substituir silenciosamente os dados publicados.

## Rastreabilidade

Cada submissão contém `response_original.txt`, `submission.c` e `metadata.json`. O metadata preserva o hash SHA-256 da resposta original e do C avaliado. A única transformação registrada é a remoção das cercas Markdown no caso do Grok; não houve alteração manual da lógica.

As extensões da QP4 usam os critérios em `protocolo/qp4_extensoes_criterios.md`. Os resultados complementares e os logs brutos estão em `results/complementar/` e `results/logs/`.

## Escopo da evidência

Este pacote torna reproduzível a execução dos códigos preservados, a
consolidação das repetições, os reparos contrafactuais e as análises
complementares versionadas. Ele não torna replicável a geração original das
respostas dos assistentes: a coleta inicial não registrou de forma completa
versão do modelo, parâmetros de amostragem ou ferramentas ativas. Nenhum
metadado ausente é reconstruído. As categorias D1--D3 são causas observadas
nessa amostra, não uma taxonomia universal; as intervenções mostram
suficiência para D1 e D3, enquanto D2 foi localizada sem reparo completo.

As medidas de custo também têm escopo limitado: `iterations`, `gcov -O0` e
instruções em `-O2` são proxies distintos, e a latência fim a fim inclui a
criação do processo. A busca bibliográfica documentada é estruturada, mas não
é uma revisão sistemática completa; a formulação adequada é que não foi
identificado trabalho com o mesmo escopo nas buscas realizadas.
