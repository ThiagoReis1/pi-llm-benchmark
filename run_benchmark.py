#!/usr/bin/env python3
"""Executa todo o pipeline de dados do PI LLM Benchmark em qualquer sistema com Python e GCC."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
PLATFORMS = ("chatgpt", "claude", "gemini", "grok")
RESULT_FILES = (
    "results.json",
    "ranking.json",
    "algorithm_ranking.json",
    "individual_code_analysis.json",
    "run_metadata.json",
)


def parse_arguments() -> argparse.Namespace:
    """Lê e valida os parâmetros da execução universal."""
    parser = argparse.ArgumentParser(
        description="Executa testes, smoke test, benchmark, rankings, logs e metadados."
    )
    parser.add_argument("--repetitions", type=int, default=5, help="Repetições por caso.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Tempo limite em segundos.")
    parser.add_argument("--memory-mb", type=int, default=1024, help="Limite de memória por processo.")
    parser.add_argument("--workers", type=int, default=4, help="Número de execuções paralelas.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Permite testar sem cinco coletas completas.")
    parser.add_argument("--skip-tests", action="store_true", help="Não executa pytest antes do benchmark.")
    parser.add_argument("--smoke-only", action="store_true", help="Executa somente o smoke test.")
    args = parser.parse_args()
    if args.repetitions < 1 or args.timeout <= 0 or args.memory_mb < 1 or args.workers < 1:
        parser.error("repetitions, timeout, memory-mb e workers devem ser positivos")
    return args


def run_command(arguments: list[str], label: str) -> None:
    """Executa um comando Python no diretório do projeto e propaga falhas."""
    print(f"\n[{label}] {' '.join(arguments)}", flush=True)
    completed = subprocess.run(arguments, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"o comando falhou com código {completed.returncode}: {' '.join(arguments)}")


def complete_attempt_count(provider: str) -> int:
    """Conta tentativas que possuem código, resposta original e metadados."""
    directory = ROOT / "submissions" / provider
    if not directory.is_dir():
        return 0
    return sum(
        all((attempt / filename).is_file() for filename in ("submission.c", "metadata.json", "response_original.txt"))
        for attempt in directory.glob("attempt_*")
        if attempt.is_dir()
    )


def validate_collection(allow_incomplete: bool) -> None:
    """Valida a coleta antes de iniciar uma rodada oficial."""
    counts = {provider: complete_attempt_count(provider) for provider in PLATFORMS}
    print("Coletas completas: " + ", ".join(f"{provider}={count}" for provider, count in counts.items()))
    if not allow_incomplete and any(count != 1 for count in counts.values()):
        raise RuntimeError("cada plataforma deve possuir exatamente uma tentativa completa; use --allow-incomplete apenas para testes")


def clean_results() -> None:
    """Remove somente artefatos regeneráveis da rodada anterior."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    for filename in RESULT_FILES:
        (RESULTS / filename).unlink(missing_ok=True)
    shutil.rmtree(RESULTS / "logs", ignore_errors=True)


def write_run_metadata(args: argparse.Namespace, started_utc: str) -> None:
    """Registra ambiente, parâmetros, contagens e resumo temporal da rodada."""
    payload = json.loads((RESULTS / "results.json").read_text(encoding="utf-8"))
    rows = payload.get("records", payload) if isinstance(payload, dict) else payload
    execution = payload.get("execution_summary", {}) if isinstance(payload, dict) else {}
    gcc = shutil.which("gcc")
    compiler = "gcc não encontrado"
    if gcc:
        result = subprocess.run([gcc, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0 and result.stdout:
            compiler = result.stdout.splitlines()[0]
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = {
        "run_at_utc": started_utc,
        "repetitions": args.repetitions,
        "timeout_seconds": args.timeout,
        "memory_mb": args.memory_mb,
        "workers": args.workers,
        "execution_environment": platform.platform(),
        "python_version": platform.python_version(),
        "compiler": compiler,
        "compiler_flags": ["-std=c11", "-O2", "-Wall", "-Wextra", "-lm"],
        "timing_scope": "compiled process execution only; compile time excluded",
        "correctness_unit": "one outcome per unique method-implementation-precision configuration (algorithm + C source file)",
        "repetition_role": "repetitions are used only to summarize execution-time variation; identical deterministic outputs are not counted as independent outcomes",
        "unique_invalid_scenarios_rejected": execution.get("casos_invalidos_unicos_rejeitados", 0),
        "execution_summary": execution,
        "logs_directory": "results/logs",
        "raw_repetition_records_preserved_for_audit": len(rows),
        "raw_repetition_records_scope": "stored execution-log rows only; not independent correctness outcomes or benchmark result counts",
        "unique_decimal_configurations": execution.get("configuracoes_decimais_unicas"),
        "status_counts": status_counts,
        "status_counts_scope": "counts in the preserved raw records only",
        "note": "Preserve os arquivos de evidência e não altere o código coletado.",
    }
    (RESULTS / "run_metadata.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    """Executa o pipeline completo ou somente o smoke test."""
    args = parse_arguments()
    validate_collection(args.allow_incomplete or args.smoke_only)
    clean_results()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        if not args.skip_tests:
            run_command([sys.executable, "-m", "pytest", "-q"], "1/5 testes")
        run_command(
            [sys.executable, "-m", "benchmark.runner", "--smoke", "--timeout", str(args.timeout), "--memory-mb", str(args.memory_mb), "--workers", str(args.workers)],
            "2/5 smoke test",
        )
        if args.smoke_only:
            print("Smoke test concluído. Os artefatos estão em results/.")
            return 0
        clean_results()
        run_command(
            [sys.executable, "-m", "benchmark.runner", "--repetitions", str(args.repetitions), "--timeout", str(args.timeout), "--memory-mb", str(args.memory_mb), "--workers", str(args.workers)],
            "3/5 benchmark completo",
        )
        write_run_metadata(args, started_utc)
        print("[4/5 metadados] results/run_metadata.json")
        run_command([sys.executable, "results/presentation/generate_presentation.py"], "5/5 tabelas e figuras")
        print("Benchmark concluído com sucesso.")
        return 0
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Falha no benchmark: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
