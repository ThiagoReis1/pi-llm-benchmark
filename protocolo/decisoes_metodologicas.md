# Decisões metodológicas e limites do estudo

Este documento registra as decisões que delimitam a interpretação dos resultados do benchmark e evita que a avaliação dos códigos preservados seja confundida com uma comparação populacional de modelos.

## Amostragem intencional

O estudo preserva uma única resposta de cada um dos quatro assistentes. Essa decisão é intencional e decorre do tempo disponível para a execução deste estudo; não deve ser interpretada como uma tentativa de estimar a variabilidade dos modelos. As cinco implementações dentro de uma resposta também não são observações independentes de geração.

Consequentemente, os resultados são descritivos das 20 implementações preservadas e de suas 360 configurações de precisão. Não são calculados `pass@k`, intervalos de confiança, testes de hipótese ou ranking entre assistentes. A expansão para várias respostas por modelo, versões e parâmetros registrados é trabalho futuro, não uma exigência retroativa para este snapshot.

## Confundimento entre assistente, método e implementação

O prompt permite que cada assistente escolha os cinco métodos. Portanto, origem, identidade matemática, representação numérica, condição de parada e decisões de implementação não são fatores isolados. Comparações entre origens não têm interpretação causal. A análise de identidade matemática é usada apenas para mostrar que a mesma fórmula pode ter desfechos diferentes quando implementada de formas diferentes.

## Correção numérica

A unidade de correção é a configuração única implementação–precisão. As cinco repetições temporais não são contadas como cinco observações de correção. O oráculo usa referência decimal de alta precisão, casas de guarda e comparação textual; a margem de guarda foi verificada para a faixa experimental, mas não é uma prova de exatidão arbitrária.

## Diagnóstico de defeitos

D1–D3 são categorias observadas nos códigos preservados, não uma taxonomia universal. As intervenções demonstram suficiência da alteração para D1 e D3; não demonstram exclusividade nem exaustividade das causas. D2 foi localizada por instrumentação e não recebeu reparo completo no snapshot.

## Custo e desempenho

`iterations`, contagens `gcov` em `-O0` e instruções em `-O2` são medidas distintas. Nenhuma delas é tratada como tempo direto ou como custo universal de aritmética multiprecisão. A latência da rodada principal inclui criação do processo e foi obtida com execução paralela; a medição complementar usa execução sequencial, aquecimento e `wait4`, mas cobre apenas `d=1,9,18`.

## Reprodutibilidade

Os artefatos preservados permitem reproduzir a avaliação dos códigos, os agregados e as análises complementares no snapshot do repositório. A geração original das respostas não é reproduzível porque a coleta inicial não registrou completamente versão do modelo, parâmetros de amostragem e ferramentas ativas. Nenhum metadado ausente é reconstruído ou inferido.

## Busca bibliográfica

A busca documentada é uma busca estruturada de escopo, não uma revisão sistemática completa. Ela não deve sustentar a afirmação de que nenhum trabalho semelhante existe. A formulação apropriada é: não foi identificado trabalho com o mesmo escopo nas buscas realizadas. A literatura futura deve ser atualizada com acesso direto às bases e dupla triagem humana.

## Uso de IA na preparação

A declaração no manuscrito informa que um assistente foi usado na revisão editorial, na conferência de consistência, na análise e na geração de scripts. O autor permanece responsável pelo conteúdo; os dados e resultados versionados são os artefatos usados para conferir os números publicados.
