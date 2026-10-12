"""Testes automatizados do contrato e da infraestrutura do benchmark."""

import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmark import runner
from benchmark.aggregation import configuration_outcome, group_configurations
from benchmark.reference import correct_decimal_prefix, reference_pi

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ["chatgpt", "claude", "gemini", "grok"]


def test_collection_directories_exist_and_any_collected_sources_compile():
    """A distribuição limpa não contém respostas; valida todas as que existirem."""
    found_sources = []
    for provider in PROVIDERS:
        directory = ROOT / "submissions" / provider
        assert directory.is_dir()
        found_sources.extend(directory.glob("attempt_*/submission.c"))
    for source in found_sources:
        output = source.parent / (".test_pi.exe" if runner.os.name == "nt" else ".test_pi")
        proc = subprocess.run(
            runner._compiler_command(source, output),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            # O benchmark deve registrar submissões que não compilam; a coleta não
            # pode falhar globalmente apenas porque uma IA forneceu C inválido.
            if proc.returncode != 0:
                assert proc.stderr
                continue
            text = source.read_text(encoding="utf-8", errors="replace").lower()
            assert len(runner._declared_algorithms(text)) == 5
            assert "--algorithm" in text
        finally:
            output.unlink(missing_ok=True)


def test_windows_compilation_enables_mingw_ansi_stdio():
    'Verifica a flag de compilação específica do MinGW.'
    command = runner._compiler_command("input.c", "output.exe", platform="nt")
    assert "-D__USE_MINGW_ANSI_STDIO=1" in command
    linux_command = runner._compiler_command("input.c", "output", platform="linux")
    assert "-D__USE_MINGW_ANSI_STDIO=1" not in linux_command


def test_execution_time_excludes_compilation(monkeypatch, tmp_path):
    'Verifica que o tempo de compilação não entra na medição de execução.'
    source = tmp_path / "fake.c"
    source.write_text("/* test */\n", encoding="utf-8")

    def fake_compile(_source, _output, _workdir):
        'Simula uma compilação lenta para o teste de escopo temporal.'
        time.sleep(0.20)
        return SimpleNamespace(returncode=0, stderr="")

    class FakeProcess:
        pid = 999999999
        returncode = 0
        def poll(self):
            'Retorna o estado simulado do processo de teste.'
            return self.returncode
        def communicate(self):
            'Retorna a saída simulada do processo de teste.'
            time.sleep(0.04)
            return '{"value":"3.1","iterations":1}\n', ""
        def kill(self):
            'Marca o processo simulado como encerrado.'
            self.returncode = -9

    monkeypatch.setattr(runner, "_compile", fake_compile)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    outcome = runner.run_one(source, {"algorithm": "test", "digits": 1}, timeout=2, memory_mb=None)

    assert outcome["ok"] is True
    assert 0.025 <= outcome["elapsed"] < 0.15


def test_cases_cover_1_to_18_digits_and_expand_per_algorithm():
    'Verifica a cobertura de precisão e expansão dos casos.'
    data = json.loads((ROOT / "benchmark" / "cases.json").read_text(encoding="utf-8"))
    assert data["decimal_digits"] == list(range(1, 19))
    assert data["invalid"]
    expanded = runner.cases_for(["a", "b"], data["decimal_digits"], data["invalid"])
    assert len([case for case in expanded if not case.get("expect_error")]) == 36
    assert all(case["algorithm"] != "$first" for case in expanded)


def test_declared_algorithms_parser():
    'Verifica a leitura de algoritmos numerados no código C.'
    assert runner._declared_algorithms("/*\n * 1. Chudnovsky (1988)\n * 2. takano  - x\n */") == ["chudnovsky", "takano"]
    assert runner._declared_algorithms("/*\n1) chudnovsky\n   - x\n\n2) ramanujan\n*/") == ["chudnovsky", "ramanujan"]
    assert runner._declared_algorithms("/*\n1. madhava: serie\n4. Machin-2 ? x\n*/") == ["madhava", "machin-2"]


def test_decimal_metric_counts_fractional_digits_only():
    'Verifica a contagem de casas decimais corretas.'
    truth = reference_pi(5)
    assert correct_decimal_prefix("3.1415", truth, 5) == 4
    assert correct_decimal_prefix("3.14159", truth, 5) == 5
    assert correct_decimal_prefix("3.141592653", reference_pi(10), 10) == 9


def test_reference_rejects_invalid_precision():
    'Verifica a rejeição de precisão inválida pelo oráculo.'
    with pytest.raises(ValueError):
        reference_pi(-1)


def test_declared_algorithms_accepts_quoted_names_and_machine_line():
    'Verifica nomes entre aspas e a linha legível por máquina.'
    # Formato real do Gemini: nome entre aspas duplas.
    quoted = '/*\n * 1. "machin" - x\n * 2. "euler" - y\n * 3. \'newton\' - z\n */'
    assert runner._declared_algorithms(quoted) == ["machin", "euler", "newton"]
    # Linha legível por máquina tem prioridade sobre a lista numerada.
    machine = "/*\n * ALGORITHMS: Machin, euler; takano\n * 1. outro\n */"
    assert runner._declared_algorithms(machine) == ["machin", "euler", "takano"]


def test_algorithm_ranking_ignores_build_failures():
    'Verifica que falhas de compilação não entram no ranking empírico.'
    ok = {"llm_id": "a", "algorithm": "euler", "case_type": "decimal", "status": "ok", "correct": True,
          "correct_digits": 5, "digits": 5, "time_seconds": 0.1}
    broken = {"llm_id": "b", "algorithm": "euler", "case_type": "decimal", "status": "error",
              "error": "compile_error", "correct": False}
    only_broken = {"llm_id": "b", "algorithm": "machin", "case_type": "decimal", "status": "error",
                   "error": "compile_error", "correct": False}
    ranking = runner.aggregate_algorithms([ok, broken, only_broken])
    assert [r["algorithm"] for r in ranking] == ["euler"]
    assert ranking[0]["functional_accuracy"] == 1.0
    assert ranking[0]["implementations"] == 1
    assert ranking[0]["score_status"] == "provisional_single_implementation"


def test_algorithm_ranking_keeps_implementations_separate():
    'Verifica que códigos distintos com o mesmo rótulo não sejam agregados.'
    rows = [
        {"llm_id": "a", "algorithm": "euler", "case_type": "decimal", "status": "ok",
         "correct": True, "correct_digits": 5, "digits": 5, "time_seconds": 0.1},
        {"llm_id": "b", "algorithm": "euler", "case_type": "decimal", "status": "ok",
         "correct": False, "correct_digits": 2, "digits": 5, "time_seconds": 0.2},
    ]
    ranking = runner.aggregate_algorithms(rows)
    assert {(r["llm_id"], r["algorithm"]) for r in ranking} == {("a", "euler"), ("b", "euler")}
    assert all(r["implementations"] == 1 for r in ranking)


def test_compile_failure_has_no_functional_accuracy():
    'Verifica que falha no gate seja contada uma vez, sem configuração ou nota por IA.'
    row = {"llm_id": "broken", "case_type": "decimal", "status": "error",
           "failure_class": "compile_error", "correct": False}
    assert runner.aggregate([row], {}) == []
    summary = runner.execution_summary([row], 0.1, "start", "finish")
    assert summary["configuracoes_decimais_unicas"] == 0
    assert summary["falhas_unicas_no_gate_de_compilacao"] == 1
    assert summary["origens_com_falha_no_gate"] == ["broken"]
    assert "por_implementacao" not in summary
    assert "por_metodo_implementado" in summary


def test_repetitions_are_one_configuration_outcome_and_time_only():
    'Verifica que repetições idênticas contem um desfecho e preservem seus tempos à parte.'
    rows = [
        {"llm_id":"a", "case_type":"decimal", "algorithm":"euler", "digits":3,
         "status":"ok", "correct":True, "correct_digits":3, "value":"3.141", "time_seconds":t}
        for t in (0.01, 0.02, 0.03, 0.02, 0.04)
    ]
    groups = group_configurations(rows)
    assert len(groups) == 1
    assert len(next(iter(groups.values()))) == 5
    assert configuration_outcome(next(iter(groups.values()))) == "correct"
    ranking = runner.aggregate_algorithms(rows, {"a": {}})
    assert ranking[0]["unique_configurations"] == 1
    assert ranking[0]["correct_cases"] == 1
    assert ranking[0]["timing_measurements"] == 5
    summary = runner.execution_summary(rows, 1.0, "start", "finish")
    assert summary["configuracoes_decimais_unicas"] == 1
    assert summary["medicoes_de_tempo_repetidas"] == 5


def test_repeated_configuration_with_different_output_is_marked_inconsistent():
    'Verifica que um resultado instável não seja escondido por uma maioria.'
    rows = [
        {"llm_id":"a", "case_type":"decimal", "algorithm":"euler", "digits":3,
         "status":"ok", "correct":True, "correct_digits":3, "value":"3.141"},
        {"llm_id":"a", "case_type":"decimal", "algorithm":"euler", "digits":3,
         "status":"ok", "correct":False, "correct_digits":2, "value":"3.142"},
    ]
    assert configuration_outcome(rows) == "inconsistent"


def test_extract_code_rejects_pasted_page():
    'Verifica a rejeição de uma página colada em vez do código.'
    import sys
    sys.path.insert(0, str(ROOT / "data_collection"))
    from prepare_submission import extract_code

    page = "Pular para o conteúdo principal\nCtrl+J\n```c\nint main(void){return 0;}\n```\nAdicionar ao bate-papo\n"
    with pytest.raises(ValueError):
        extract_code(page)
    assert extract_code("/* c */\nint main(void){return 0;}\n")[1] == "raw_response"
    assert extract_code("```c\nint main(void){return 0;}\n```\n")[1] == "removed_markdown_fence"
