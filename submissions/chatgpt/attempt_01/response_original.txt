/*
 * Calculo Numerico de pi ? cinco algoritmos baseados exclusivamente em series
 * convergentes:
 *
 * 1. MACHIN7   ? pi = 20*atan(1/7) + 8*atan(3/79).
 *                 Prioridade 1: convergencia extremamente rapida, poucas
 *                 iteracoes e boa estabilidade por usar argumentos pequenos.
 *
 * 2. GAUSS     ? pi = 48*atan(1/18) + 32*atan(1/57) - 20*atan(1/239).
 *                 Prioridade 2: convergencia muito rapida e excelente
 *                 estabilidade, com os termos dominantes tendo razoes pequenas.
 *
 * 3. MACHIN    ? pi = 64*atan(1/5) - 16*atan(1/239).
 *                 Prioridade 3: formula classica, simples, deterministica e
 *                 suficientemente rapida para 18 casas decimais.
 *
 * 4. ATAN23    ? pi = 4*(atan(1/2) + atan(1/3)).
 *                 Prioridade 4: formula simples e independente das identidades
 *                 de Machin, mas com convergencia mais lenta.
 *
 * 5. EULER     ? transformacao de Euler da serie alternada de Gregory:
 *                 pi/4 = 1 - 1/3 + 1/5 - 1/7 + ...
 *                 A transformacao mantem uma serie convergente, mas acelera
 *                 fortemente sua convergencia. E util como metodo independente
 *                 para comparacao e reprodutibilidade.
 *
 * Estrategia de precisao:
 * - Nao e utilizada a precisao de double/long double para o resultado final.
 * - Todas as operacoes numericas sao feitas com inteiro decimal de ponto fixo.
 * - A escala e 10^36, fornecendo 18 casas decimais solicitadas mais 18 casas
 *   de guarda.
 * - O inteiro usa base decimal 10^9 em varios limbs, implementados manualmente.
 * - Divisoes sao realizadas por inteiros pequenos, evitando overflow.
 * - O resultado e convertido diretamente para texto e arredondado decimalmente.
 *
 * Limitacoes:
 * - A implementacao e deliberadamente limitada aos cinco metodos escolhidos.
 * - O numero de iteracoes e determinado quando o proximo termo se torna zero
 *   na escala interna; a escala de 10^36 deixa ampla margem para 18 casas.
 *
 * Compilacao:
 *   gcc -std=c11 -O2 -Wall -Wextra arquivo.c -lm -o pi_benchmark
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>

#define BASE UINT32_C(1000000000)
#define BIG_CAP 16
#define SCALE_LIMB 4
#define MAX_ARCTAN_TERMS 10000
#define MAX_EULER_TERMS 120

typedef struct {
    uint32_t v[BIG_CAP];
    size_t n;
} Big;

typedef struct {
    Big value;
    unsigned int iterations;
} CalcResult;

/* ---------- Operacoes basicas de inteiro decimal ---------- */

static void big_zero(Big *a)
{
    memset(a, 0, sizeof(*a));
    a->n = 0;
}

static void big_normalize(Big *a)
{
    while (a->n > 0 && a->v[a->n - 1] == 0) {
        --a->n;
    }
}

static void big_from_u32(Big *a, uint32_t x)
{
    big_zero(a);
    if (x != 0) {
        a->v[0] = x;
        a->n = 1;
    }
}

static void big_from_scale(Big *a)
{
    big_zero(a);

    /*
     * BASE^4 = (10^9)^4 = 10^36.
     * Assim, o valor representado por SCALE e exatamente 10^36.
     */
    a->v[SCALE_LIMB] = 1;
    a->n = SCALE_LIMB + 1;
}

static int big_is_zero(const Big *a)
{
    return a->n == 0;
}

static int big_cmp(const Big *a, const Big *b)
{
    size_t i;

    if (a->n < b->n) {
        return -1;
    }
    if (a->n > b->n) {
        return 1;
    }

    i = a->n;
    while (i > 0) {
        --i;
        if (a->v[i] < b->v[i]) {
            return -1;
        }
        if (a->v[i] > b->v[i]) {
            return 1;
        }
    }

    return 0;
}

static int big_add(Big *r, const Big *a, const Big *b)
{
    size_t i;
    size_t maxn = (a->n > b->n) ? a->n : b->n;
    uint64_t carry = 0;

    if (maxn >= BIG_CAP) {
        return 0;
    }

    for (i = 0; i < maxn; ++i) {
        uint64_t av = (i < a->n) ? a->v[i] : 0;
        uint64_t bv = (i < b->n) ? b->v[i] : 0;
        uint64_t s = av + bv + carry;

        if (s >= BASE) {
            s -= BASE;
            carry = 1;
        } else {
            carry = 0;
        }

        r->v[i] = (uint32_t)s;
    }

    r->n = maxn;

    if (carry != 0) {
        if (r->n >= BIG_CAP) {
            return 0;
        }
        r->v[r->n++] = (uint32_t)carry;
    }

    return 1;
}

/* r = a - b, assumindo a >= b. */
static int big_sub(Big *r, const Big *a, const Big *b)
{
    size_t i;
    int64_t borrow = 0;

    if (big_cmp(a, b) < 0) {
        return 0;
    }

    for (i = 0; i < a->n; ++i) {
        int64_t av = (int64_t)a->v[i];
        int64_t bv = (i < b->n) ? (int64_t)b->v[i] : 0;
        int64_t d = av - bv - borrow;

        if (d < 0) {
            d += BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }

        r->v[i] = (uint32_t)d;
    }

    r->n = a->n;
    big_normalize(r);
    return 1;
}

static int big_mul_small(Big *r, const Big *a, uint32_t m)
{
    size_t i;
    uint64_t carry = 0;

    if (m == 0 || a->n == 0) {
        big_zero(r);
        return 1;
    }

    if (m > UINT32_MAX) {
        return 0;
    }

    for (i = 0; i < a->n; ++i) {
        uint64_t p = (uint64_t)a->v[i] * (uint64_t)m + carry;
        r->v[i] = (uint32_t)(p % BASE);
        carry = p / BASE;
    }

    r->n = a->n;

    while (carry != 0) {
        if (r->n >= BIG_CAP) {
            return 0;
        }
        r->v[r->n++] = (uint32_t)(carry % BASE);
        carry /= BASE;
    }

    return 1;
}

/*
 * Divisao inteira por um inteiro positivo pequeno.
 * O quociente substitui r e o resto e retornado.
 */
static uint32_t big_div_small(Big *r, const Big *a, uint32_t d)
{
    size_t i;
    uint64_t rem = 0;

    if (d == 0) {
        return 0;
    }

    r->n = a->n;

    i = a->n;
    while (i > 0) {
        uint64_t cur;
        --i;

        cur = rem * (uint64_t)BASE + (uint64_t)a->v[i];
        r->v[i] = (uint32_t)(cur / d);
        rem = cur % d;
    }

    big_normalize(r);
    return (uint32_t)rem;
}

static int big_copy(Big *dst, const Big *src)
{
    *dst = *src;
    return 1;
}

/* ---------- Operacoes compostas ---------- */

static int big_add_mul_small(Big *dst, const Big *src,
                             uint32_t multiplier, int subtract)
{
    Big tmp;

    if (!big_mul_small(&tmp, src, multiplier)) {
        return 0;
    }

    if (subtract) {
        return big_sub(dst, dst, &tmp);
    }

    return big_add(dst, dst, &tmp);
}

/*
 * atan(num/den), calculado pela serie:
 *
 * atan(x) = x - x^3/3 + x^5/5 - x^7/7 + ...
 *
 * Os termos sao mantidos em ponto fixo decimal.
 */
static int arctan_series(uint32_t num, uint32_t den,
                         Big *result, unsigned int *iterations)
{
    Big term;
    Big next;
    Big sum;
    uint64_t den2;
    uint64_t num2;
    unsigned int n;

    if (den == 0 || num == 0 || num >= den) {
        return 0;
    }

    den2 = (uint64_t)den * (uint64_t)den;
    num2 = (uint64_t)num * (uint64_t)num;

    if (den2 > UINT32_MAX || num2 > UINT32_MAX) {
        return 0;
    }

    big_from_scale(&term);

    /*
     * term_0 = SCALE * num / den.
     * Multiplicar antes de dividir preserva a maior quantidade possivel
     * de casas internas.
     */
    if (!big_mul_small(&term, &term, num)) {
        return 0;
    }
    (void)big_div_small(&term, &term, den);

    big_zero(&sum);

    for (n = 0; n < MAX_ARCTAN_TERMS; ++n) {
        if (big_is_zero(&term)) {
            *result = sum;
            *iterations = n;
            return 1;
        }

        if ((n & 1U) == 0U) {
            if (!big_add(&sum, &sum, &term)) {
                return 0;
            }
        } else {
            if (!big_sub(&sum, &sum, &term)) {
                return 0;
            }
        }

        /*
         * term_(n+1) =
         * term_n * num^2 /
         * [den^2 * (2n+1) * (2n+3)].
         */
        {
            uint64_t odd1 = (uint64_t)2U * n + 1U;
            uint64_t odd3 = (uint64_t)2U * n + 3U;
            uint64_t divisor = den2 * odd1 * odd3;

            if (divisor == 0 || divisor > UINT32_MAX) {
                return 0;
            }

            if (!big_mul_small(&next, &term, (uint32_t)num2)) {
                return 0;
            }

            (void)big_div_small(&term, &next, (uint32_t)divisor);
        }
    }

    return 0;
}

/* ---------- Algoritmos ---------- */

/*
 * Algoritmo 1:
 * pi = 20 atan(1/7) + 8 atan(3/79)
 */
static int algorithm_machin7(CalcResult *out)
{
    Big a, b, t;
    unsigned int ia, ib;

    if (!arctan_series(1, 7, &a, &ia)) {
        return 0;
    }

    if (!arctan_series(3, 79, &b, &ib)) {
        return 0;
    }

    big_zero(&out->value);

    if (!big_add_mul_small(&out->value, &a, 20, 0)) {
        return 0;
    }

    if (!big_mul_small(&t, &b, 8)) {
        return 0;
    }

    if (!big_add(&out->value, &out->value, &t)) {
        return 0;
    }

    out->iterations = ia + ib;
    return 1;
}

/*
 * Algoritmo 2:
 * pi = 48 atan(1/18) + 32 atan(1/57) - 20 atan(1/239)
 */
static int algorithm_gauss(CalcResult *out)
{
    Big a, b, c, t;
    unsigned int ia, ib, ic;

    if (!arctan_series(1, 18, &a, &ia)) {
        return 0;
    }
    if (!arctan_series(1, 57, &b, &ib)) {
        return 0;
    }
    if (!arctan_series(1, 239, &c, &ic)) {
        return 0;
    }

    big_zero(&out->value);

    if (!big_add_mul_small(&out->value, &a, 48, 0)) {
        return 0;
    }
    if (!big_add_mul_small(&out->value, &b, 32, 0)) {
        return 0;
    }

    if (!big_mul_small(&t, &c, 20)) {
        return 0;
    }
    if (!big_sub(&out->value, &out->value, &t)) {
        return 0;
    }

    out->iterations = ia + ib + ic;
    return 1;
}

/*
 * Algoritmo 3 ? formula de Machin classica:
 * pi = 64 atan(1/5) - 16 atan(1/239)
 */
static int algorithm_machin(CalcResult *out)
{
    Big a, b, t;
    unsigned int ia, ib;

    if (!arctan_series(1, 5, &a, &ia)) {
        return 0;
    }

    if (!arctan_series(1, 239, &b, &ib)) {
        return 0;
    }

    big_zero(&out->value);

    if (!big_add_mul_small(&out->value, &a, 64, 0)) {
        return 0;
    }

    if (!big_mul_small(&t, &b, 16)) {
        return 0;
    }

    if (!big_sub(&out->value, &out->value, &t)) {
        return 0;
    }

    out->iterations = ia + ib;
    return 1;
}

/*
 * Algoritmo 4:
 * pi = 4 [atan(1/2) + atan(1/3)]
 */
static int algorithm_atan23(CalcResult *out)
{
    Big a, b, s;
    unsigned int ia, ib;

    if (!arctan_series(1, 2, &a, &ia)) {
        return 0;
    }

    if (!arctan_series(1, 3, &b, &ib)) {
        return 0;
    }

    if (!big_add(&s, &a, &b)) {
        return 0;
    }

    if (!big_mul_small(&out->value, &s, 4)) {
        return 0;
    }

    out->iterations = ia + ib;
    return 1;
}

/*
 * Algoritmo 5 ? transformacao de Euler da serie de Gregory.
 *
 * Serie original:
 *
 *   pi/4 = 1 - 1/3 + 1/5 - 1/7 + ...
 *
 * Para uma serie alternada sum (-1)^n a_n, a transformacao de Euler da:
 *
 *   sum (-1)^n a_n = sum_{k=0}^inf Delta^k(a_0) / 2^(k+1),
 *
 * onde Delta^k usa diferencas sucessivas na forma:
 *
 *   a_n - a_(n+1).
 *
 * Todas as diferencas sao calculadas na mesma representacao decimal.
 */
static int algorithm_euler(CalcResult *out)
{
    Big differences[MAX_EULER_TERMS + 1];
    Big term;
    Big contribution;
    Big sum;
    size_t i;
    size_t length = MAX_EULER_TERMS + 1;
    unsigned int k;
    unsigned int iterations = 0;

    for (i = 0; i < length; ++i) {
        big_from_scale(&differences[i]);
        (void)big_div_small(&differences[i],
                            &differences[i],
                            (uint32_t)(2U * i + 1U));
    }

    big_zero(&sum);

    for (k = 0; k < MAX_EULER_TERMS; ++k) {
        if (k > 0) {
            size_t j;

            for (j = 0; j + 1 < length; ++j) {
                Big d;

                if (!big_sub(&d, &differences[j], &differences[j + 1])) {
                    return 0;
                }

                differences[j] = d;
            }

            --length;
        }

        /*
         * contribuicao = Delta^k(a0) / 2^(k+1).
         * A divisao repetida por 2 evita depender de representacao binaria
         * ou de extensoes de inteiros.
         */
        term = differences[0];

        for (i = 0; i < (size_t)k + 1U; ++i) {
            Big half;

            (void)big_div_small(&half, &term, 2);
            term = half;

            if (big_is_zero(&term)) {
                break;
            }
        }

        if (big_is_zero(&term)) {
            break;
        }

        contribution = term;

        if (!big_add(&sum, &sum, &contribution)) {
            return 0;
        }

        ++iterations;
    }

    /*
     * pi = 4 * (pi/4).
     */
    if (!big_mul_small(&out->value, &sum, 4)) {
        return 0;
    }

    out->iterations = iterations;
    return 1;
}

/* ---------- Conversao decimal e arredondamento ---------- */

/*
 * Converte o Big de ponto fixo para uma sequencia decimal.
 *
 * O valor interno e:
 *
 *     inteiro armazenado / 10^36.
 *
 * Para pi, ha exatamente 37 digitos relevantes:
 *     "3" + 36 casas internas.
 */
static int big_to_decimal_digits(const Big *value,
                                 char *digits,
                                 size_t digits_capacity)
{
    size_t pos = 0;
    size_t i;
    int written;

    if (digits_capacity < 40 || value->n == 0) {
        return 0;
    }

    i = value->n;

    written = snprintf(digits + pos,
                       digits_capacity - pos,
                       "%u",
                       value->v[i - 1]);

    if (written < 0) {
        return 0;
    }

    pos += (size_t)written;

    while (i > 1) {
        --i;

        written = snprintf(digits + pos,
                           digits_capacity - pos,
                           "%09u",
                           value->v[i - 1]);

        if (written < 0) {
            return 0;
        }

        pos += (size_t)written;
    }

    digits[pos] = '\0';
    return 1;
}

static int format_pi(const Big *value, unsigned int requested_digits,
                     char *output, size_t output_capacity)
{
    char raw[64];
    char rounded[64];
    size_t prefix_len;
    size_t i;
    size_t pos = 0;
    int carry = 0;

    if (requested_digits < 1 || requested_digits > 18) {
        return 0;
    }

    if (!big_to_decimal_digits(value, raw, sizeof(raw))) {
        return 0;
    }

    /*
     * raw contem pelo menos:
     *   1 digito inteiro + 36 digitos fracionarios.
     */
    prefix_len = (size_t)requested_digits + 1U;

    if (strlen(raw) <= prefix_len) {
        return 0;
    }

    memcpy(rounded, raw, prefix_len);
    rounded[prefix_len] = '\0';

    /*
     * A casa imediatamente posterior as solicitadas determina o
     * arredondamento decimal.
     */
    if (raw[prefix_len] >= '5') {
        i = prefix_len;

        while (i > 0) {
            --i;

            if (rounded[i] < '9') {
                ++rounded[i];
                carry = 0;
                break;
            }

            rounded[i] = '0';
            carry = 1;
        }

        /*
         * Isto nao ocorre para pi nas 18 casas solicitadas, mas mantem
         * a rotina matematicamente consistente caso o inteiro passe de 9.
         */
        if (carry != 0) {
            if (prefix_len + 1U >= sizeof(rounded)) {
                return 0;
            }

            memmove(rounded + 1, rounded, prefix_len + 1U);
            rounded[0] = '1';
            ++prefix_len;
        }
    }

    if (prefix_len + 2U > output_capacity) {
        return 0;
    }

    output[pos++] = rounded[0];
    output[pos++] = '.';

    for (i = 1; i < prefix_len; ++i) {
        output[pos++] = rounded[i];
    }

    output[pos] = '\0';
    return 1;
}

/* ---------- Interface de linha de comando ---------- */

static int parse_digits_argument(const char *s, unsigned int *value)
{
    unsigned long v = 0;
    const unsigned char *p = (const unsigned char *)s;

    if (*p == '\0') {
        return 0;
    }

    while (*p != '\0') {
        unsigned int digit;

        if (*p < (unsigned char)'0' || *p > (unsigned char)'9') {
            return 0;
        }

        digit = (unsigned int)(*p - (unsigned char)'0');

        if (v > (ULONG_MAX - digit) / 10UL) {
            return 0;
        }

        v = v * 10UL + digit;

        if (v > 18UL) {
            return 0;
        }

        ++p;
    }

    if (v < 1UL || v > 18UL) {
        return 0;
    }

    *value = (unsigned int)v;
    return 1;
}

static int select_algorithm(const char *name, CalcResult *result)
{
    if (strcmp(name, "machin7") == 0) {
        return algorithm_machin7(result);
    }

    if (strcmp(name, "gauss") == 0) {
        return algorithm_gauss(result);
    }

    if (strcmp(name, "machin") == 0) {
        return algorithm_machin(result);
    }

    if (strcmp(name, "atan23") == 0) {
        return algorithm_atan23(result);
    }

    if (strcmp(name, "euler") == 0) {
        return algorithm_euler(result);
    }

    return 0;
}

int main(int argc, char **argv)
{
    const char *algorithm_name = NULL;
    unsigned int digits = 15;
    int i;
    CalcResult result;
    char decimal[64];

    for (i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--algorithm") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "erro: --algorithm requer um nome\n");
                return EXIT_FAILURE;
            }

            algorithm_name = argv[++i];
        } else if (strcmp(argv[i], "--digits") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "erro: --digits requer um valor entre 1 e 18\n");
                return EXIT_FAILURE;
            }

            if (!parse_digits_argument(argv[++i], &digits)) {
                fprintf(stderr, "erro: digits deve estar entre 1 e 18\n");
                return EXIT_FAILURE;
            }
        } else {
            fprintf(stderr, "erro: argumento desconhecido\n");
            return EXIT_FAILURE;
        }
    }

    if (algorithm_name == NULL) {
        fprintf(stderr, "erro: --algorithm e obrigatorio\n");
        return EXIT_FAILURE;
    }

    if (strcmp(algorithm_name, "machin7") != 0 &&
        strcmp(algorithm_name, "gauss") != 0 &&
        strcmp(algorithm_name, "machin") != 0 &&
        strcmp(algorithm_name, "atan23") != 0 &&
        strcmp(algorithm_name, "euler") != 0) {
        fprintf(stderr, "erro: algoritmo desconhecido\n");
        return EXIT_FAILURE;
    }

    memset(&result, 0, sizeof(result));

    if (!select_algorithm(algorithm_name, &result)) {
        fprintf(stderr, "erro: falha numerica no algoritmo\n");
        return EXIT_FAILURE;
    }

    if (!format_pi(&result.value, digits, decimal, sizeof(decimal))) {
        fprintf(stderr, "erro: falha ao formatar o resultado\n");
        return EXIT_FAILURE;
    }

    /*
     * stdout contem exclusivamente o objeto JSON solicitado.
     */
    printf("{\"value\":\"%s\",\"iterations\":%u}\n",
           decimal,
           result.iterations);

    return EXIT_SUCCESS;
}
