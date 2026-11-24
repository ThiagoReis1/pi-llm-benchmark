#!/usr/bin/env python3
"""Verifica os números centrais publicados no artigo contra os artefatos do benchmark.

O script não recalcula a rodada. Ele apenas consolida os registros brutos por
configuração única (assistente, algoritmo e precisão), ignorando as repetições
como desfechos independentes, e confere os totais que aparecem no manuscrito.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

EXPECTED = {
    "configurations": 360,
    "correct": 268,
    "incorrect": 74,
    "execution_failure": 18,
    "perfect_implementations": 14,
    "repaired_d1_d3": 74,
    "qp4_valid": 19,
    "qp4_concordant": 13,
    "e3_total": 19,
    "e3_same_verdict": 15,
}


def unique_decimal_outcomes(records: list[dict]) -> dict[tuple, dict]:
    """Consolida cinco repetições em um único resultado por configuração."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in records:
        if row.get("case_type") != "decimal":
            continue
        key = (row.get("llm_id"), row.get("algorithm"), row.get("digits"))
        grouped[key].append(row)
    outcomes = {}
    for key, rows in grouped.items():
        signatures = {
            (
                row.get("status"),
                row.get("correct"),
                row.get("value"),
                row.get("correct_digits"),
                row.get("failure_class"),
                row.get("error_type"),
            )
            for row in rows
        }
        if len(signatures) != 1:
            raise AssertionError(f"resultado inconsistente em {key}: {signatures}")
        outcomes[key] = rows[0]
    return outcomes


def check(root: Path) -> dict[str, int]:
    """Calcula e valida os números centrais do artigo."""
    raw = json.loads((root / "results/results.json").read_text(encoding="utf-8"))
    outcomes = unique_decimal_outcomes(raw["records"])
    counts = {
        "configurations": len(outcomes),
        "correct": sum(row.get("correct") is True for row in outcomes.values()),
        "incorrect": sum(
            row.get("status") == "ok" and row.get("correct") is not True
            for row in outcomes.values()
        ),
        "execution_failure": sum(row.get("status") != "ok" for row in outcomes.values()),
    }
    by_impl: dict[tuple, list[dict]] = defaultdict(list)
    for (llm, algorithm, _digits), row in outcomes.items():
        by_impl[(llm, algorithm)].append(row)
    counts["perfect_implementations"] = sum(
        len(rows) == 18 and all(row.get("correct") is True for row in rows)
        for rows in by_impl.values()
    )

    repairs = json.loads(
        (root / "results/complementar/reparos_contrafactuais.json").read_text(
            encoding="utf-8"
        )
    )
    repaired_cases = []
    for key, item in repairs.items():
        if key.startswith(("D1/", "D1+D4/", "D3/")):
            original = item.get("original_corretas")
            repaired = item.get("reparado_corretas")
            if repaired == 18:
                repaired_cases.append(18 - original)
    counts["repaired_d1_d3"] = sum(repaired_cases)

    qp4 = json.loads(
        (root / "results/complementar/qp4_analise.json").read_text(encoding="utf-8")
    )
    counts["qp4_valid"] = len(qp4)
    counts["qp4_concordant"] = sum(bool(item.get("concorda")) for item in qp4.values())

    e3 = json.loads(
        (root / "results/complementar/qp4_extensoes.json").read_text(encoding="utf-8")
    )
    verdicts = e3["vereditos"]["E3"]["por_impl"]
    counts["e3_total"] = len(verdicts)
    counts["e3_same_verdict"] = sum(
        bool(item.get("igual"))
        for item in verdicts.values()
    )

    mismatches = {
        key: (value, EXPECTED[key])
        for key, value in counts.items()
        if key in EXPECTED and value != EXPECTED[key]
    }
    if mismatches:
        raise AssertionError(f"divergências nos números publicados: {mismatches}")
    return counts


def main() -> int:
    """Executa a verificação e imprime os números conferidos."""
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", help="raiz do repositório")
    args = parser.parse_args()
    counts = check(Path(args.root).resolve())
    print("Números centrais conferidos com sucesso:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
