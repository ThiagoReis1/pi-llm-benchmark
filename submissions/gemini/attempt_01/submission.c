/*
 * Academic Experiment: Numerical Computation of Pi using Convergent Series
 * 
 * Algorithm Selection and Priority Justifications:
 * 1. "machin" - Machin's Formula (1706): pi = 16*arctan(1/5) - 4*arctan(1/239)
 *    Justification: Combines two rapidly converging Taylor series for arctan with geometric
 *    bases 1/25 and 1/57121. Historically the gold standard for high-precision pi benchmarks.
 * 
 * 2. "euler" - Euler's Accelerated Series (1755): pi = 2 * sum_{k=0}^{\infty} (k! / (2k+1)!!)
 *    Justification: Derived from transforming the arctan series into a fast positive-term
 *    accelerated series. Exhibits steady linear geometric convergence (ratio 1/2, ~0.301 digits/term).
 * 
 * 3. "newton" - Newton's Arcsine Series (1665): pi = 3 * sum_{k=0}^{\infty} ((2k)! / (16^k * (k!)^2 * (2k+1)))
 *    Justification: Maclaurin expansion of 6*arcsin(1/2) with geometric ratio 1/4 (~0.602 digits/term),
 *    demonstrating classical power series integration.
 * 
 * 4. "nilakantha" - Nilakantha's Series (c. 1500): pi = 3 + 4 * sum_{k=1}^{\infty} ((-1)^(k+1) / (2k*(2k+1)*(2k+2)))
 *    Justification: Polynomial convergence rate O(1/k^3). Provides an essential baseline for sub-geometric
 *    alternating series behavior compared to exponential and hypergeometric series.
 * 
 * 5. "ramanujan" - Ramanujan's Hypergeometric Series (1914): 1/pi = (2*sqrt(2)/9801) * sum_{k=0}^{\infty} ...
 *    Justification: Ultra-fast hypergeometric convergence (~8 decimal places per iteration).
 *    Represents the modern state-of-the-art for series-based pi computation algorithms.
 * 
 * Strategy for High Precision & Cross-Platform Stability:
 * - Employs a custom 45-decimal-digit fixed-point integer arithmetic engine (Base 10^9, 6 limbs) implemented
 *   entirely within C11 standard code, eliminating platform-dependent floating-point representation differences
 *   (such as long double behavior differences between GCC x86_64 80-bit and MinGW 64-bit IEEE 754).
 * - Avoids external libraries, platform-specific APIs, compiler extensions (__int128), and precomputed constants.
 * - Format string output performs exact decimal rounding at the N-th requested decimal place.
 * 
 * Limitations:
 * - Designed for high precision up to 18 decimal places (N in [1, 18]).
 * - Fixed limb count (6 limbs x 9 digits = 45 digits internal precision) guarantees zero roundoff error
 *   accumulation for N <= 18, but is not arbitrary-precision for N > 45.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <inttypes.h>

#define NUM_LIMBS 6
#define BASE 1000000000ULL

typedef struct {
    uint32_t d[NUM_LIMBS];
} BigNum;

static void bignum_init_zero(BigNum *num) {
    memset(num, 0, sizeof(BigNum));
}

static void bignum_from_uint(BigNum *num, uint64_t val) {
    memset(num, 0, sizeof(BigNum));
    num->d[5] = (uint32_t)(val % BASE);
}

static bool bignum_is_zero(const BigNum *num) {
    for (int i = 0; i < NUM_LIMBS; i++) {
        if (num->d[i] != 0) return false;
    }
    return true;
}

static int bignum_cmp(const BigNum *a, const BigNum *b) {
    for (int i = NUM_LIMBS - 1; i >= 0; i--) {
        if (a->d[i] > b->d[i]) return 1;
        if (a->d[i] < b->d[i]) return -1;
    }
    return 0;
}

static void bignum_add(BigNum *res, const BigNum *a, const BigNum *b) {
    uint64_t carry = 0;
    for (int i = 0; i < NUM_LIMBS; i++) {
        uint64_t sum = (uint64_t)a->d[i] + b->d[i] + carry;
        res->d[i] = (uint32_t)(sum % BASE);
        carry = sum / BASE;
    }
}

static void bignum_sub(BigNum *res, const BigNum *a, const BigNum *b) {
    int64_t borrow = 0;
    for (int i = 0; i < NUM_LIMBS; i++) {
        int64_t diff = (int64_t)a->d[i] - b->d[i] - borrow;
        if (diff < 0) {
            diff += BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }
        res->d[i] = (uint32_t)diff;
    }
}

static void bignum_mul_uint(BigNum *res, const BigNum *a, uint64_t u) {
    uint64_t carry = 0;
    for (int i = 0; i < NUM_LIMBS; i++) {
        uint64_t prod = (uint64_t)a->d[i] * u + carry;
        res->d[i] = (uint32_t)(prod % BASE);
        carry = prod / BASE;
    }
}

static void bignum_div_uint(BigNum *res, const BigNum *a, uint64_t u) {
    if (u == 0) return;
    uint64_t rem = 0;
    for (int i = NUM_LIMBS - 1; i >= 0; i--) {
        uint64_t cur = rem * BASE + a->d[i];
        res->d[i] = (uint32_t)(cur / u);
        rem = cur % u;
    }
}

static void bignum_mul(BigNum *res, const BigNum *a, const BigNum *b) {
    uint64_t temp[12] = {0};
    for (int i = 0; i < NUM_LIMBS; i++) {
        for (int j = 0; j < NUM_LIMBS; j++) {
            temp[i + j] += (uint64_t)a->d[i] * b->d[j];
        }
    }
    uint64_t carry = 0;
    for (int k = 0; k < 11; k++) {
        uint64_t sum = temp[k] + carry;
        temp[k] = sum % BASE;
        carry = sum / BASE;
    }
    temp[11] += carry;

    if (temp[4] >= BASE / 2) {
        temp[5]++;
        for (int k = 5; k < 11; k++) {
            if (temp[k] >= BASE) {
                temp[k] %= BASE;
                temp[k + 1]++;
            } else {
                break;
            }
        }
    }

    for (int i = 0; i < NUM_LIMBS; i++) {
        res->d[i] = (uint32_t)temp[i + 5];
    }
}

static double bignum_to_double(const BigNum *a) {
    double res = (double)a->d[5];
    double factor = 1.0 / (double)BASE;
    double scale = factor;
    for (int i = 4; i >= 0; i--) {
        res += (double)a->d[i] * scale;
        scale *= factor;
    }
    return res;
}

static void bignum_from_double(BigNum *res, double val) {
    bignum_init_zero(res);
    if (val < 0.0) val = 0.0;
    uint64_t int_part = (uint64_t)val;
    res->d[5] = (uint32_t)int_part;
    double frac = val - (double)int_part;
    for (int i = 4; i >= 0; i--) {
        frac *= (double)BASE;
        uint32_t digit = (uint32_t)frac;
        if (digit >= BASE) digit = (uint32_t)(BASE - 1);
        res->d[i] = digit;
        frac -= (double)digit;
    }
}

static void bignum_reciprocal(BigNum *res, const BigNum *B) {
    double d = bignum_to_double(B);
    if (d <= 0.0) return;
    double inv0 = 0.999999999999 / d;
    BigNum Y;
    bignum_from_double(&Y, inv0);

    BigNum two, BY, diff;
    bignum_from_uint(&two, 2);

    for (int iter = 0; iter < 4; iter++) {
        bignum_mul(&BY, B, &Y);
        bignum_sub(&diff, &two, &BY);
        bignum_mul(&Y, &Y, &diff);
    }
    *res = Y;
}

static void bignum_sqrt2(BigNum *res) {
    BigNum x, inv_x, two_inv, sum;
    bignum_from_double(&x, 1.41421356237309504880);
    for (int iter = 0; iter < 4; iter++) {
        bignum_reciprocal(&inv_x, &x);
        bignum_mul_uint(&two_inv, &inv_x, 2);
        bignum_add(&sum, &x, &two_inv);
        bignum_div_uint(&x, &sum, 2);
    }
    *res = x;
}

static void bignum_set_pow10_neg(BigNum *num, int neg_exp) {
    bignum_init_zero(num);
    if (neg_exp <= 0) return;
    int idx = neg_exp - 1;
    int limb = 4 - (idx / 9);
    int pos = idx % 9;
    if (limb >= 0 && limb < NUM_LIMBS) {
        uint32_t val = 1;
        for (int i = 0; i < 8 - pos; i++) {
            val *= 10;
        }
        num->d[limb] = val;
    }
}

static void bignum_format(char *out, const BigNum *num, int digits) {
    char frac[64];
    snprintf(frac, sizeof(frac), "%09" PRIu32 "%09" PRIu32 "%09" PRIu32 "%09" PRIu32 "%09" PRIu32,
             num->d[4], num->d[3], num->d[2], num->d[1], num->d[0]);

    int int_part = (int)num->d[5];

    if (frac[digits] >= '5') {
        int carry = 1;
        for (int i = digits - 1; i >= 0; i--) {
            int val = (frac[i] - '0') + carry;
            if (val >= 10) {
                frac[i] = '0' + (val - 10);
                carry = 1;
            } else {
                frac[i] = '0' + val;
                carry = 0;
                break;
            }
        }
        if (carry) {
            int_part += 1;
        }
    }

    frac[digits] = '\0';
    snprintf(out, 64, "%d.%s", int_part, frac);
}

static void run_machin(BigNum *pi, int digits, uint64_t *out_iters) {
    BigNum threshold, S1, S2, P, Q, one;
    bignum_set_pow10_neg(&threshold, digits + 3);
    bignum_init_zero(&S1);
    bignum_init_zero(&S2);
    bignum_from_uint(&one, 1);

    bignum_div_uint(&P, &one, 5);
    bignum_div_uint(&Q, &one, 239);

    uint64_t k = 0;
    int p_active = 1, q_active = 1;

    while (p_active || q_active) {
        uint64_t denom = 2 * k + 1;
        if (p_active) {
            BigNum termP;
            bignum_div_uint(&termP, &P, denom);
            if (bignum_cmp(&termP, &threshold) < 0 || bignum_is_zero(&termP)) {
                p_active = 0;
            } else {
                if (k % 2 == 0) bignum_add(&S1, &S1, &termP);
                else bignum_sub(&S1, &S1, &termP);
                bignum_div_uint(&P, &P, 25);
            }
        }
        if (q_active) {
            BigNum termQ;
            bignum_div_uint(&termQ, &Q, denom);
            if (bignum_cmp(&termQ, &threshold) < 0 || bignum_is_zero(&termQ)) {
                q_active = 0;
            } else {
                if (k % 2 == 0) bignum_add(&S2, &S2, &termQ);
                else bignum_sub(&S2, &S2, &termQ);
                bignum_div_uint(&Q, &Q, 57121);
            }
        }
        k++;
    }

    BigNum term1, term2;
    bignum_mul_uint(&term1, &S1, 16);
    bignum_mul_uint(&term2, &S2, 4);
    bignum_sub(pi, &term1, &term2);
    *out_iters = k;
}

static void run_euler(BigNum *pi, int digits, uint64_t *out_iters) {
    BigNum threshold, S, T;
    bignum_set_pow10_neg(&threshold, digits + 3);
    bignum_from_uint(&S, 1);
    bignum_from_uint(&T, 1);

    uint64_t k = 1;
    while (1) {
        BigNum nextT;
        bignum_mul_uint(&nextT, &T, k);
        bignum_div_uint(&T, &nextT, 2 * k + 1);

        if (bignum_cmp(&T, &threshold) < 0 || bignum_is_zero(&T)) {
            break;
        }
        bignum_add(&S, &S, &T);
        k++;
    }

    bignum_mul_uint(pi, &S, 2);
    *out_iters = k;
}

static void run_newton(BigNum *pi, int digits, uint64_t *out_iters) {
    BigNum threshold, S, C;
    bignum_set_pow10_neg(&threshold, digits + 3);
    bignum_from_uint(&S, 1);
    bignum_from_uint(&C, 1);

    uint64_t k = 1;
    while (1) {
        BigNum tempC, T;
        bignum_mul_uint(&tempC, &C, 2 * k - 1);
        bignum_div_uint(&C, &tempC, 8 * k);
        bignum_div_uint(&T, &C, 2 * k + 1);

        if (bignum_cmp(&T, &threshold) < 0 || bignum_is_zero(&T)) {
            break;
        }
        bignum_add(&S, &S, &T);
        k++;
    }

    bignum_mul_uint(pi, &S, 3);
    *out_iters = k;
}

static void run_nilakantha(BigNum *pi, int digits, uint64_t *out_iters) {
    BigNum threshold, S;
    bignum_set_pow10_neg(&threshold, digits + 3);
    bignum_from_uint(&S, 3);

    uint64_t k = 1;
    while (1) {
        BigNum T;
        bignum_from_uint(&T, 2);
        bignum_div_uint(&T, &T, k);
        bignum_div_uint(&T, &T, 2 * k + 1);
        bignum_div_uint(&T, &T, 2 * k + 2);

        if (bignum_cmp(&T, &threshold) < 0 || bignum_is_zero(&T)) {
            break;
        }

        if (k % 2 == 1) {
            bignum_add(&S, &S, &T);
        } else {
            bignum_sub(&S, &S, &T);
        }
        k++;
    }

    *pi = S;
    *out_iters = k;
}

static void run_ramanujan(BigNum *pi, int digits, uint64_t *out_iters) {
    BigNum threshold, S, R;
    bignum_set_pow10_neg(&threshold, digits + 3);
    bignum_from_uint(&S, 1103);
    bignum_from_uint(&R, 1);

    uint64_t k = 1;
    while (1) {
        BigNum tempR;
        uint64_t num_factor = (4 * k - 3) * (4 * k - 2) * (4 * k - 1) * 4;
        bignum_mul_uint(&tempR, &R, num_factor);
        bignum_div_uint(&tempR, &tempR, k);
        bignum_div_uint(&tempR, &tempR, k);
        bignum_div_uint(&tempR, &tempR, k);
        bignum_div_uint(&tempR, &tempR, 256);
        bignum_div_uint(&R, &tempR, 96059601ULL);

        BigNum T;
        uint64_t term_factor = 1103 + 26390 * k;
        bignum_mul_uint(&T, &R, term_factor);

        if (bignum_cmp(&T, &threshold) < 0 || bignum_is_zero(&T)) {
            break;
        }

        bignum_add(&S, &S, &T);
        k++;
    }

    BigNum V, VS, D, invD;
    bignum_sqrt2(&V);
    bignum_mul(&VS, &V, &S);
    bignum_mul_uint(&D, &VS, 2);
    bignum_reciprocal(&invD, &D);
    bignum_mul_uint(pi, &invD, 9801);
    *out_iters = k;
}

int main(int argc, char *argv[]) {
    char *algo = NULL;
    int digits = 18;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--algorithm=", 12) == 0) {
            algo = argv[i] + 12;
        } else if (strcmp(argv[i], "--algorithm") == 0) {
            if (i + 1 < argc) {
                algo = argv[++i];
            } else {
                fprintf(stderr, "Error: missing value for --algorithm\n");
                return 1;
            }
        } else if (strncmp(argv[i], "--digits=", 9) == 0) {
            digits = atoi(argv[i] + 9);
        } else if (strcmp(argv[i], "--digits") == 0) {
            if (i + 1 < argc) {
                digits = atoi(argv[++i]);
            } else {
                fprintf(stderr, "Error: missing value for --digits\n");
                return 1;
            }
        } else {
            fprintf(stderr, "Error: unrecognized argument '%s'\n", argv[i]);
            return 1;
        }
    }

    if (!algo) {
        fprintf(stderr, "Error: --algorithm parameter is required\n");
        return 1;
    }

    if (digits < 1 || digits > 18) {
        fprintf(stderr, "Error: --digits must be an integer between 1 and 18\n");
        return 1;
    }

    BigNum pi;
    uint64_t iters = 0;

    if (strcmp(algo, "machin") == 0) {
        run_machin(&pi, digits, &iters);
    } else if (strcmp(algo, "euler") == 0 || strcmp(algo, "euler_arctan") == 0) {
        run_euler(&pi, digits, &iters);
    } else if (strcmp(algo, "newton") == 0 || strcmp(algo, "newton_arcsin") == 0) {
        run_newton(&pi, digits, &iters);
    } else if (strcmp(algo, "nilakantha") == 0) {
        run_nilakantha(&pi, digits, &iters);
    } else if (strcmp(algo, "ramanujan") == 0) {
        run_ramanujan(&pi, digits, &iters);
    } else {
        fprintf(stderr, "Error: unknown algorithm '%s'\n", algo);
        return 1;
    }

    char out_str[64];
    bignum_format(out_str, &pi, digits);

    printf("{\"value\":\"%s\",\"iterations\":%" PRIu64 "}\n", out_str, iters);
    return 0;
}
