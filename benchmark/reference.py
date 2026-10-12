"""Oráculo independente e métricas exatas do benchmark (séries decimais)."""
import mpmath as mp


def reference_pi(digits: int) -> str:
    'Gera o valor de referência de Pi com a quantidade solicitada de casas decimais.'
    if not isinstance(digits, int) or isinstance(digits, bool) or digits < 0:
        raise ValueError("digits deve ser inteiro não negativo")
    with mp.workdps(max(40, digits + 25)):
        return mp.nstr(mp.pi, n=digits + 1, strip_zeros=False)


def decimal_metrics(value: str, expected: str, requested_digits: int) -> dict:
    """Compara strings decimais sem converter para float.

    `correct_digits` conta somente dígitos após o separador decimal e considera
    como corretas as casas do prefixo solicitado. O erro é calculado em mp.mpf.
    """
    if not isinstance(requested_digits, int) or requested_digits < 0:
        raise ValueError("requested_digits deve ser inteiro não negativo")
    candidate = str(value).strip()
    truth = str(expected).strip()
    try:
        with mp.workdps(max(50, requested_digits + 30)):
            candidate_mp = mp.mpf(candidate)
            truth_mp = mp.mpf(truth)
            absolute = abs(candidate_mp - truth_mp)
            relative = absolute / abs(truth_mp) if truth_mp else absolute
            absolute_exact = mp.nstr(absolute, n=max(25, requested_digits + 8), strip_zeros=False)
            relative_exact = mp.nstr(relative, n=max(25, requested_digits + 8), strip_zeros=False)
            absolute_float = float(absolute) if absolute < mp.mpf("1e308") else float("inf")
            relative_float = float(relative) if relative < mp.mpf("1e308") else float("inf")
    except Exception:
        return {"correct_digits": 0, "absolute_error": None, "relative_error": None, "absolute_error_exact": None, "relative_error_exact": None, "correct": False}
    if "." not in candidate or "." not in truth:
        count = 0
    else:
        a_int, a_frac = candidate.split(".", 1)
        b_int, b_frac = truth.split(".", 1)
        count = 0
        if a_int == b_int:
            for left, right in zip(a_frac[:requested_digits], b_frac[:requested_digits]):
                if left != right:
                    break
                count += 1
    return {
        "correct_digits": count,
        "absolute_error": absolute_float,
        "relative_error": relative_float,
        "absolute_error_exact": absolute_exact,
        "relative_error_exact": relative_exact,
        "correct": count >= requested_digits,
    }


def correct_decimal_prefix(value: str, expected: str, requested_digits: int) -> int:
    'Retorna a quantidade de casas decimais corretas no prefixo produzido.'
    return decimal_metrics(value, expected, requested_digits)["correct_digits"]
