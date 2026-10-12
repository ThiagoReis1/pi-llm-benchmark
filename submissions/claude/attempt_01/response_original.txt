/*
 * pi_benchmark.c - Calculo de pi por series convergentes, em aritmetica decimal
 * de ponto fixo (45 casas fracionarias), sem ponto flutuante.
 *
 * Compilar: gcc -std=c11 -O2 -Wall -Wextra arquivo.c -lm -o pi_benchmark
 * Uso:      ./pi_benchmark --algorithm NOME --digits N     (1 <= N <= 18)
 *
 * CINCO ALGORITMOS ESCOLHIDOS (ordem de prioridade: precisao/velocidade/estabilidade):
 *  1. chudnovsky : pi = 426880*sqrt(10005) / sum_k (-1)^k (6k)!(13591409+545140134k)
 *                  / ((3k)!(k!)^3 640320^(3k)).  ~14 digitos por termo; convergencia
 *                  mais rapida entre as series classicas; razao de termos so com
 *                  inteiros pequenos (estavel, reprodutivel).
 *  2. ramanujan  : 1/pi = (2*sqrt2/9801) sum (4k)!(1103+26390k)/((k!)^4 396^(4k)).
 *                  ~8 digitos por termo; todos os termos positivos (sem cancelamento).
 *  3. takano     : pi = 4(12 atan(1/49)+32 atan(1/57)-5 atan(1/239)+12 atan(1/110443)).
 *                  Formula tipo Machin com argumentos pequenos: convergencia rapida
 *                  usando apenas divisoes por inteiros pequenos.
 *  4. machin     : pi = 16 atan(1/5) - 4 atan(1/239). Referencia historica robusta,
 *                  simples e bem condicionada.
 *  5. euler      : pi = 2 * sum_{k>=0} k!/(2k+1)!! (serie de Euler/Newton). Razao ~1/2
 *                  (linear), serve como linha de base simples e sem raiz quadrada.
 *  Descartadas: Leibniz/Nilakantha (lentas demais para precisao tao alta), Monte Carlo
 *  e BBP (proibidos).
 *
 * ESTRATEGIA DE PRECISAO: inteiros sem sinal de 12 limbs na base 10^9 (108 digitos
 * decimais), interpretados como ponto fixo com 5 limbs fracionarios (10^45). Termos
 * sao truncados (erro < 1e-42 acumulado), muito abaixo das 18 casas pedidas + digito
 * de arredondamento. Raiz quadrada: metodo digito a digito (inteiro). Divisao grande:
 * divisao longa decimal. Arredondamento final (meio para cima) feito sobre os digitos
 * decimais do texto. Sem long double, __int128, M_PI ou constantes de pi.
 * LIMITES: --digits em [1,18]; "iterations" = numero de termos somados da serie.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NL 12                      /* limbs totais                      */
#define FR 5                       /* limbs fracionarios                */
#define FD (FR * 9)                /* digitos fracionarios (45)         */
#define BASE 1000000000u
#define MAXSMALL 18000000000ULL    /* garante que produtos cabem em uint64 */
#define MAXITER 100000UL

typedef struct { uint32_t d[NL]; } Big; /* d[0] = limb menos significativo */

static int g_err = 0; /* sinaliza overflow / erro interno */

static Big big_zero(void) { Big z; memset(&z, 0, sizeof z); return z; }
static Big big_one(void) { Big z = big_zero(); z.d[FR] = 1; return z; }

static int big_is_zero(const Big *a) {
    for (int i = 0; i < NL; i++) if (a->d[i]) return 0;
    return 1;
}

static int big_cmp(const Big *a, const Big *b) {
    for (int i = NL - 1; i >= 0; i--) {
        if (a->d[i] != b->d[i]) return a->d[i] < b->d[i] ? -1 : 1;
    }
    return 0;
}

static Big big_add(Big a, Big b) {
    uint64_t carry = 0;
    for (int i = 0; i < NL; i++) {
        uint64_t s = (uint64_t)a.d[i] + b.d[i] + carry;
        a.d[i] = (uint32_t)(s % BASE);
        carry = s / BASE;
    }
    if (carry) g_err = 1;
    return a;
}

/* Requer a >= b. */
static Big big_sub(Big a, Big b) {
    int64_t borrow = 0;
    for (int i = 0; i < NL; i++) {
        int64_t s = (int64_t)a.d[i] - (int64_t)b.d[i] - borrow;
        if (s < 0) { s += BASE; borrow = 1; } else borrow = 0;
        a.d[i] = (uint32_t)s;
    }
    if (borrow) g_err = 1;
    return a;
}

static Big big_add_small(Big a, uint32_t v) {
    uint64_t carry = v;
    for (int i = 0; i < NL && carry; i++) {
        uint64_t s = (uint64_t)a.d[i] + carry;
        a.d[i] = (uint32_t)(s % BASE);
        carry = s / BASE;
    }
    if (carry) g_err = 1;
    return a;
}

static Big big_mul_small(Big a, uint64_t m) {
    if (m > MAXSMALL) { g_err = 1; return a; }
    uint64_t carry = 0;
    for (int i = 0; i < NL; i++) {
        uint64_t cur = (uint64_t)a.d[i] * m + carry;
        a.d[i] = (uint32_t)(cur % BASE);
        carry = cur / BASE;
    }
    if (carry) g_err = 1;
    return a;
}

static Big big_div_small(Big a, uint64_t m) {
    if (m == 0 || m > MAXSMALL) { g_err = 1; return a; }
    uint64_t rem = 0;
    for (int i = NL - 1; i >= 0; i--) {
        uint64_t cur = rem * BASE + a.d[i];
        a.d[i] = (uint32_t)(cur / m);
        rem = cur % m;
    }
    return a;
}

/* Escreve NL*9 digitos decimais (com zeros a esquerda) e '\0'. */
static void big_to_dec(const Big *a, char *out) {
    int pos = 0;
    for (int i = NL - 1; i >= 0; i--) {
        uint32_t v = a->d[i];
        for (int j = 8; j >= 0; j--) { out[pos + j] = (char)('0' + v % 10); v /= 10; }
        pos += 9;
    }
    out[pos] = '\0';
}

/* floor(sqrt(n) * 10^45), metodo digito a digito em decimal. n pequeno (>0). */
static Big big_sqrt_fixed(unsigned n) {
    char digs[16], buf[32];
    int len = snprintf(digs, sizeof digs, "%u", n);
    int off = 0;
    if (len % 2) buf[off++] = '0';
    memcpy(buf + off, digs, (size_t)len);
    int pairs = (off + len) / 2;
    Big p = big_zero(), r = big_zero();
    for (int i = 0; i < pairs + FD; i++) {
        unsigned v = 0;
        if (i < pairs) v = (unsigned)((buf[2 * i] - '0') * 10 + (buf[2 * i + 1] - '0'));
        r = big_add_small(big_mul_small(r, 100), v);
        unsigned x = 0;
        for (unsigned c = 9; c >= 1; c--) {
            Big t = big_add_small(big_mul_small(p, 20), c);
            Big tx = big_mul_small(t, c);
            if (big_cmp(&tx, &r) <= 0) { x = c; r = big_sub(r, tx); break; }
        }
        p = big_add_small(big_mul_small(p, 10), x);
    }
    return p;
}

/* Quociente em ponto fixo: floor(A_raw * 10^45 / S_raw), divisao longa decimal. */
static Big big_div_fixed(Big A, Big S) {
    Big Q = big_zero(), R = big_zero();
    if (big_is_zero(&S)) { g_err = 1; return Q; }
    char dec[NL * 9 + 1];
    big_to_dec(&A, dec);
    int start = 0;
    while (start < NL * 9 && dec[start] == '0') start++;
    int len = NL * 9 - start;
    if (len + FD > NL * 9 - 3) { g_err = 1; return Q; }
    for (int i = 0; i < len + FD; i++) {
        unsigned dg = (i < len) ? (unsigned)(dec[start + i] - '0') : 0u;
        R = big_add_small(big_mul_small(R, 10), dg);
        unsigned q = 0;
        while (big_cmp(&R, &S) >= 0 && q < 10) { R = big_sub(R, S); q++; }
        Q = big_add_small(big_mul_small(Q, 10), q);
    }
    return Q;
}

/* atan(1/x) = sum (-1)^j / ((2j+1) x^(2j+1)); x inteiro pequeno. */
static Big atan_inv(uint64_t x, unsigned long *iters) {
    Big pos = big_zero(), neg = big_zero();
    Big p = big_div_small(big_one(), x);
    for (uint64_t j = 0; !big_is_zero(&p) && j < MAXITER; j++) {
        Big t = big_div_small(p, 2 * j + 1);
        if (j % 2 == 0) pos = big_add(pos, t); else neg = big_add(neg, t);
        (*iters)++;
        p = big_div_small(big_div_small(p, x), x);
    }
    return big_sub(pos, neg);
}

/* ---------------- Algoritmos ---------------- */

static Big alg_chudnovsky(unsigned long *iters) {
    Big term = big_one(), pos = big_zero(), neg = big_zero();
    for (uint64_t k = 0; k < 1000; k++) {
        if (k > 0) {
            term = big_mul_small(term, 24);
            term = big_mul_small(term, 6 * k - 5);
            term = big_mul_small(term, 2 * k - 1);
            term = big_mul_small(term, 6 * k - 1);
            for (int i = 0; i < 3; i++) term = big_div_small(term, k);
            for (int i = 0; i < 3; i++) term = big_div_small(term, 640320);
            if (big_is_zero(&term)) break;
        }
        Big t = big_mul_small(term, 13591409ULL + 545140134ULL * k);
        if (k % 2 == 0) pos = big_add(pos, t); else neg = big_add(neg, t);
        (*iters)++;
    }
    Big S = big_sub(pos, neg);
    Big A = big_mul_small(big_sqrt_fixed(10005), 426880);
    return big_div_fixed(A, S);
}

static Big alg_ramanujan(unsigned long *iters) {
    Big term = big_one(), sum = big_zero();
    for (uint64_t k = 0; k < 1000; k++) {
        if (k > 0) {
            term = big_mul_small(term, 8);
            term = big_mul_small(term, 4 * k - 1);
            term = big_mul_small(term, 2 * k - 1);
            term = big_mul_small(term, 4 * k - 3);
            for (int i = 0; i < 3; i++) term = big_div_small(term, k);
            for (int i = 0; i < 4; i++) term = big_div_small(term, 396);
            if (big_is_zero(&term)) break;
        }
        sum = big_add(sum, big_mul_small(term, 1103ULL + 26390ULL * k));
        (*iters)++;
    }
    /* pi = 9801 / (sqrt(8) * S) = (9801*sqrt(8)/8) / S */
    Big N = big_div_small(big_mul_small(big_sqrt_fixed(8), 9801), 8);
    return big_div_fixed(N, sum);
}

static Big alg_takano(unsigned long *iters) {
    Big a = atan_inv(49, iters), b = atan_inv(57, iters);
    Big c = atan_inv(239, iters), d = atan_inv(110443, iters);
    Big pos = big_add(big_add(big_mul_small(a, 48), big_mul_small(b, 128)),
                      big_mul_small(d, 48));
    return big_sub(pos, big_mul_small(c, 20));
}

static Big alg_machin(unsigned long *iters) {
    Big a = big_mul_small(atan_inv(5, iters), 16);
    Big b = big_mul_small(atan_inv(239, iters), 4);
    return big_sub(a, b);
}

static Big alg_euler(unsigned long *iters) {
    Big term = big_one(), sum = big_one();
    *iters = 1;
    for (uint64_t k = 1; k < MAXITER; k++) {
        term = big_div_small(big_mul_small(term, k), 2 * k + 1);
        if (big_is_zero(&term)) break;
        sum = big_add(sum, term);
        (*iters)++;
    }
    return big_mul_small(sum, 2);
}

typedef Big (*AlgFn)(unsigned long *);
static const struct { const char *name; AlgFn fn; } ALGS[] = {
    {"chudnovsky", alg_chudnovsky}, {"ramanujan", alg_ramanujan},
    {"takano", alg_takano},         {"machin", alg_machin},
    {"euler", alg_euler}
};

/* Valor de uma opcao: aceita "--opt valor" e "--opt=valor". */
static const char *opt_value(const char *opt, int argc, char **argv, int *i) {
    size_t n = strlen(opt);
    if (strncmp(argv[*i], opt, n) != 0) return NULL;
    if (argv[*i][n] == '=') return argv[*i] + n + 1;
    if (argv[*i][n] == '\0' && *i + 1 < argc) return argv[++(*i)];
    return NULL;
}

int main(int argc, char **argv) {
    const char *alg = NULL;
    long digits = 10;
    for (int i = 1; i < argc; i++) {
        const char *v;
        if ((v = opt_value("--algorithm", argc, argv, &i)) != NULL) {
            alg = v;
        } else if ((v = opt_value("--digits", argc, argv, &i)) != NULL) {
            char *end = NULL;
            errno = 0;
            digits = strtol(v, &end, 10);
            if (errno != 0 || end == v || *end != '\0') {
                fprintf(stderr, "erro: valor invalido para --digits\n");
                return 2;
            }
        } else {
            fprintf(stderr, "erro: argumento invalido: %s\n", argv[i]);
            return 2;
        }
    }
    if (alg == NULL) {
        fprintf(stderr, "erro: use --algorithm NOME --digits N\n");
        return 2;
    }
    if (digits < 1 || digits > 18) {
        fprintf(stderr, "erro: --digits deve estar entre 1 e 18\n");
        return 2;
    }
    AlgFn fn = NULL;
    for (size_t i = 0; i < sizeof ALGS / sizeof ALGS[0]; i++)
        if (strcmp(alg, ALGS[i].name) == 0) fn = ALGS[i].fn;
    if (fn == NULL) {
        fprintf(stderr, "erro: algoritmo desconhecido: %s\n", alg);
        return 2;
    }

    unsigned long iters = 0;
    Big r = fn(&iters);
    if (g_err) {
        fprintf(stderr, "erro interno: overflow na aritmetica\n");
        return 3;
    }

    /* Converte para texto decimal e arredonda (meio para cima) na casa N. */
    char dec[NL * 9 + 1];
    big_to_dec(&r, dec);
    int ipos = 0;
    int intlen = NL * 9 - FD;
    while (ipos < intlen - 1 && dec[ipos] == '0') ipos++;
    char out[160];
    int pos = 0;
    for (int i = ipos; i < intlen; i++) out[pos++] = dec[i];
    out[pos++] = '.';
    const char *frac = dec + intlen;
    for (int i = 0; i < (int)digits; i++) out[pos++] = frac[i];
    out[pos] = '\0';
    if (frac[digits] >= '5') {
        int i = pos - 1;
        int done = 0;
        while (i >= 0 && !done) {
            if (out[i] == '.') { i--; continue; }
            if (out[i] == '9') { out[i] = '0'; i--; }
            else { out[i]++; done = 1; }
        }
        if (!done) {
            fprintf(stderr, "erro interno: arredondamento\n");
            return 3;
        }
    }
    printf("{\"value\":\"%s\",\"iterations\":%lu}\n", out, iters);
    return 0;
}
