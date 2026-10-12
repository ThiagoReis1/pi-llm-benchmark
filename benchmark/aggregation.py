"""Consolidação de repetições em configurações experimentais únicas."""

from __future__ import annotations

from collections import defaultdict


def is_compile_failure(row: dict) -> bool:
    """Identifica um diagnóstico de falha do gate de compilação."""
    return (
        row.get("failure_class") == "compile_error"
        or row.get("error_type") == "compile_error"
        or row.get("error") == "compile_error"
    )


def group_configurations(rows, case_type: str = "decimal") -> dict:
    """Agrupa as medições repetidas pela unidade lógica do caso, sem incluir tempo."""
    groups = defaultdict(list)
    for row in rows:
        if row.get("case_type") != case_type or is_compile_failure(row):
            continue
        provider = str(row.get("llm_id", "desconhecida"))
        if case_type == "decimal":
            if row.get("algorithm") is None or row.get("digits") is None:
                continue
            key = (provider, str(row["algorithm"]), int(row["digits"]))
        else:
            key = (provider, str(row.get("case_id", "caso_desconhecido")))
        groups[key].append(row)
    return dict(groups)


def _result_signature(row: dict, case_type: str):
    """Extrai apenas campos que definem o resultado, excluindo duração e repetição."""
    if row.get("status") == "ok":
        return (
            "ok",
            row.get("correct"),
            str(row.get("value", row.get("observed_value", ""))),
            row.get("correct_digits"),
        )
    return (
        row.get("status"),
        row.get("failure_class"),
        row.get("error_type"),
        bool(row.get("correct")) if case_type == "invalid" else None,
    )


def configuration_outcome(repetitions, case_type: str = "decimal") -> str:
    """Classifica uma configuração uma única vez e expõe eventual divergência."""
    if not repetitions:
        return "not_evaluated"
    signatures = {_result_signature(row, case_type) for row in repetitions}
    if len(signatures) > 1:
        return "inconsistent"
    row = repetitions[0]
    if case_type == "decimal":
        if row.get("status") == "ok":
            return "correct" if row.get("correct") is True else "incorrect"
        return "execution_failure"
    if row.get("correct") is True:
        return "rejected"
    if row.get("status") == "ok":
        return "unexpected_acceptance"
    return "execution_failure"


def configuration_time_medians(repetitions) -> list[float]:
    """Retorna tempos válidos para a mediana temporal, sem criar novos desfechos."""
    return [
        float(row["time_seconds"])
        for row in repetitions
        if row.get("status") == "ok"
        and isinstance(row.get("time_seconds"), (int, float))
        and row.get("time_seconds") > 0
    ]
