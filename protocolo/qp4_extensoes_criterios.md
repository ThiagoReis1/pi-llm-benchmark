# Critérios das extensões da QP4 (fixados antes das novas medições)

Data de redação: 2026-11-24, antes de rodar `tools/qp4_extensoes.py`.
Os scripts gravam o SHA-256 deste arquivo em cada JSON de saída, para que se possa
verificar que os critérios abaixo são os que estavam em vigor na execução.

**Alcance.** Estes critérios valem só para as medições *novas* (E1 a E3). Os dados de
`d = 1..18` já existentes (`qp4_gcov.json`) não são reclassificados, e o critério de
concordância original continua o mesmo (item C0). Os critérios foram escritos depois de a
medição `gcov` de `d = 1..18` já existir; por isso a análise `gcov` original é
confirmatória apenas em parte, e só as extensões abaixo foram definidas antes de medir.
Este arquivo e os resultados entram no mesmo commit; a ordem de escrita é atestada apenas
pelo hash gravado nos JSONs e pela data acima, não por commits separados.

## C0. Concordância entre a classe estática e o custo medido (herdada, inalterada)

- `Theta(1)`: `H` é constante em `d = 1..18`.
- `Theta(d)`: `N` é linear (BIC, `dBIC <= 2`), `H` não é constante e `H/N` não cresce mais
  de 10% entre `d = 5` e `d = 18` (`LIM_KAPPA = 1,10`).
- `Theta(10^(d/3))`: `N` é exponencial e vale a mesma condição sobre `H/N`.

## E1. Intervenção no Grok: número de limbs fixo

**Hipótese (já registrada no artigo como inferência):** o custo por termo `H/N` cresce com
`d` no Grok porque a linha mais executada é um laço sobre os limbs ativos (`a->n`), e `n`
cresce com o tamanho do valor.

**Intervenção:** cópia de `submissions/grok/attempt_01/submission.c` em que todo
`BigInt` tem sempre `n = FIXL` limbs (sem encolher nem crescer), com `FIXL = 3` (mínimo que
comporta `pi * 10^26`) e `FIXL = 6`. Algoritmos: `machin`, `gauss`, `hutton`, `twinarctan`
(o Nilakantha fica de fora, pois o defeito D3 o interrompe). Compilação `-O0 --coverage`,
`d = 1..18`, mesmo procedimento da QP4.

**Critérios:**

1. *Resultado preservado:* `value` e `iterations` iguais aos do original em todos os
   `d` e algoritmos. Se falhar, a intervenção é inválida e é descartada.
2. *Causa sustentada* se, para os quatro algoritmos e para `FIXL = 3` e `FIXL = 6`,
   `(H/N)(d=18) / (H/N)(d=5) <= 1,10`. *Causa refutada* se qualquer razão passar de 1,10.
3. *Dose-resposta:* `(H/N)(FIXL=6) > (H/N)(FIXL=3)` em `d = 18` para os quatro
   algoritmos.

## E2. Faixa além de d = 18 (cópias com a verificação `d <= 18` removida)

**E2a. Claude (cinco implementações).** Cópia A: só a verificação de faixa é removida
(`FR = 5`, escala interna de 45 casas). `d = 19..44`. Cópia B: verificação removida e
escala ampliada (`FR = 10`, `NL = 17`, 90 casas), `d = 1, 18, 44, 80`.

1. *`N` é função da escala interna, não de `d`:* na cópia A, `iterations(d) = iterations(18)`
   para todo `d` testado, nas cinco implementações.
2. *Escala maior, mais termos:* `iterations` da cópia B em `d = 18` é maior que o da
   cópia A em `d = 18` nas cinco implementações.
3. *Limite teórico:* a saída é incorreta para todo `d > N*delta` (com `N` da cópia
   correspondente e `delta` como na QP4). Se alguma implementação acertar além de
   `N*delta`, o limite é refutado.
4. Registra-se também o maior `d` correto contíguo (`dmax`) de cada implementação.

**E2b. Grok (quatro algoritmos de arco-tangente).** Cópia com a verificação removida e
os buffers de saída ampliados; `d = 19..50`.

1. `iterations` cresce linearmente em `d` e a inclinação `b` fica no intervalo teórico
   `[1/delta_min, soma(1/delta_i)]` com tolerância de 10% (como na QP4).
2. A saída é correta em todos os `d` (senão, registra-se `dmax`).
3. `(H/N)(d=50) / (H/N)(d=18) > 1,10`, isto é, o custo por termo continua a crescer
   (limbs ativos), em vez de estabilizar.

**Fora do alcance:** ChatGPT (defeitos D1/D2) e Gemini (representação com limbs e
posições fixas no código, o que exigiria reescrita, não uma alteração mínima).

## E3. Contagem de instruções com `-O2`

**Medida:** instruções executadas (`Ir`) por `valgrind --tool=callgrind`, em binários
compilados com as opções da rodada (`-std=c11 -O2 -Wall -Wextra`), `d = 1..18`, todas as
implementações que não abortam. `Ir_liq(d) = Ir(d) - Ir_vazio`, em que `Ir_vazio` é o
valor de um programa com `main` vazio compilado com as mesmas opções.

**Critério de concordância com `Ir_liq` no lugar de `H`** (mesma estrutura de C0):

- `Theta(1)`: `(max - min)/min` de `Ir_liq` em `d = 1..18` é no máximo 5%.
- `Theta(d)`: `N` linear, `Ir_liq` não é constante (variação > 5%) e `Ir_liq/N` não cresce
  mais de 10% entre `d = 5` e `d = 18`.
- `Theta(10^(d/3))`: `N` exponencial e a mesma condição sobre `Ir_liq/N`.

**Leitura:** a medida com `gcov` em `-O0` é *robusta à otimização* se o veredito
(concorda ou não) com `Ir_liq` em `-O2` for igual ao veredito com `H` em todas as
implementações. Qualquer divergência é relatada implementação por implementação, sem
reajustar os limiares.

## Regras gerais

- Nenhum limiar é alterado depois de ver os resultados. Se um critério falhar, o resultado
  é relatado como falha do critério.
- Cópias nunca substituem os `submission.c` originais, que não são editados.
