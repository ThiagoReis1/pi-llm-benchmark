"""Executor do benchmark para submissões C11."""
import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import re
import statistics
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .reference import reference_pi, decimal_metrics
from .algorithm_analysis import analise_custo_empirica, analise_do_algoritmo
from .c_code_analysis import analisar_codigo_c
from .aggregation import configuration_outcome, configuration_time_medians, group_configurations, is_compile_failure

try:  # Linux/macOS: permite limitar a memória do processo filho.
    import resource
except ImportError:  # Windows: não existe o módulo `resource`; o limite de memória não é aplicado.
    resource = None

BINARY_NAME = "pi_benchmark.exe" if os.name == "nt" else "pi_benchmark"

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = ROOT / "submissions"
RESULTS = ROOT / "results"
PROMPT = ROOT / "prompts" / "benchmark_prompt.txt"
# A métrica de qualidade (0,10) foi removida do score; os demais pesos são renormalizados para somar 1.
SCORE_NORMALIZER = 1 / 0.90
FORBIDDEN_TOKENS = ("M_PI", "math.pi", "numpy.pi", "np.pi", "mp.pi", "sympy.pi")


def _compiler_command(path, output, platform=None):
    """Monta o comando GCC; habilita printf ANSI no MinGW para suporte correto a %Lf."""
    platform = os.name if platform is None else platform
    command = ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra"]
    if platform == "nt":
        command.append("-D__USE_MINGW_ANSI_STDIO=1")
    return command + [str(path), "-lm", "-o", str(output)]


def metadata_for(directory):
    'Carrega os metadados de uma tentativa; retorna um dicionário vazio quando o arquivo não é válido.'
    try:
        return json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def submission_entries():
    'Itera pelas submissões e tentativas disponíveis em ordem determinística.'
    for provider_dir in sorted(SUBMISSIONS.iterdir()):
        if not provider_dir.is_dir():
            continue
        attempts = sorted(d for d in provider_dir.glob("attempt_*") if d.is_dir() and (d / "submission.c").exists())
        if attempts:
            for attempt in attempts:
                yield provider_dir.name, attempt, metadata_for(attempt)
        else:
            yield provider_dir.name, provider_dir, metadata_for(provider_dir)


def _compile(path, output, workdir):
    'Compila uma submissão C em um diretório de trabalho temporário.'
    return subprocess.run(
        _compiler_command(path, output),
        cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )


def _declared_algorithms(source):
    """Lê os cinco algoritmos declarados no comentário inicial.

    Aceita, nesta ordem de prioridade:
      1. uma linha legível por máquina: ``ALGORITHMS: nome1, nome2, ...``;
      2. itens numerados (1. nome ... 5. nome), com ou sem ``*``, ``_``, crases ou aspas
         simples/duplas ao redor do nome (ex.: ``1. "machin" - ...``).
    """
    block = re.match(r"\s*/\*(.*?)\*/", source, re.S)
    head = block.group(1) if block else source[:6000]
    names = []
    line = re.search(r"(?im)^[ \t]*\*?[ \t]*ALGORITHMS[ \t]*:[ \t]*(.+)$", head)
    if line:
        for raw in re.split(r"[,;]", line.group(1)):
            match = re.match(r"[\s*_`\"']*([A-Za-z][A-Za-z0-9_\-]*)", raw)
            if match and match.group(1).lower() not in names:
                names.append(match.group(1).lower())
        if names:
            return names
    declared = {}
    for number, name in re.findall(r"(?m)^[ \t]*\*?[ \t]*(\d+)[.)][ \t]*[*_`\"']*([A-Za-z][A-Za-z0-9_\-]*)", head):
        if 1 <= int(number) <= 5 and int(number) not in declared:
            declared[int(number)] = name.lower()
    for number in sorted(declared):
        if declared[number] not in names:
            names.append(declared[number])
    return names


def _resolve_cli_name(binary, declared):
    """Descobre qual valor de --algorithm o programa aceita para o nome declarado."""
    for candidate in dict.fromkeys([declared, declared.replace("-", "_"), declared.replace("-", ""), declared.replace("_", "")]):
        try:
            proc = subprocess.run([str(binary), "--algorithm", candidate, "--digits", "5"], capture_output=True, text=True, timeout=5)
        except Exception:
            continue
        if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
            return candidate
    return None


def static_checks(path):
    'Executa verificações estáticas, compilação de prova e análise individual do código C.'
    source = path.read_text(encoding="utf-8", errors="replace")
    code_only = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    forbidden = [token for token in FORBIDDEN_TOKENS if token.lower() in code_only.lower()]
    declared = _declared_algorithms(source)
    resolved = {}
    with tempfile.TemporaryDirectory(prefix="pi_compile_") as td:
        binary = Path(td) / BINARY_NAME
        try:
            proc = _compile(path, binary, td)
            compile_ok = proc.returncode == 0
            compile_error = proc.stderr[-4000:]
            if compile_ok:
                for name in declared:
                    resolved[name] = _resolve_cli_name(binary, name)
        except Exception as exc:
            compile_ok, compile_error = False, repr(exc)
    analise_codigo = analisar_codigo_c(path, [resolved.get(n) or n for n in declared]) if declared else {}
    return {
        "forbidden_tokens": forbidden,
        "syntax_ok": compile_ok,
        "compile_ok": compile_ok,
        "compile_error": compile_error,
        "declared_algorithms": declared,
        "selected_algorithms": [resolved.get(n) or n for n in declared],
        "unresolved_algorithms": [n for n in declared if compile_ok and not resolved.get(n)],
        "algorithm_selection_ok": len(declared) >= 5,
        "signature_ok": compile_ok,
        "ranking_ok": len(declared) >= 5,
        "theoretical_ranking": None,
        "probe_error": "" if compile_ok else compile_error,
        "static_ok": compile_ok and not forbidden and len(declared) >= 5,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_path": str(path),
        "attempt": path.parent.name,
        "analise_codigo": analise_codigo,
    }


def _limit_memory(memory_mb):
    'Aplica o limite de memória ao processo filho em sistemas que oferecem RLIMIT_AS.'
    if memory_mb and resource is not None:
        limit = int(memory_mb * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def run_one(path, case, timeout, memory_mb):
    'Executa uma configuração do benchmark e registra tempo, memória, saída e falhas.'
    with tempfile.TemporaryDirectory(prefix="pi_run_") as td:
        binary = Path(td) / BINARY_NAME
        try:
            compiled = _compile(path, binary, td)
        except Exception as exc:
            return {"ok": False, "error": f"compile_error: {exc}", "compile_error": repr(exc), "command": [], "compile_command": []}
        if compiled.returncode != 0:
            return {"ok": False, "error": "compile_error", "stderr": getattr(compiled, "stderr", ""), "compile_stderr": getattr(compiled, "stderr", ""),
                    "compile_stdout": getattr(compiled, "stdout", ""), "command": [], "compile_command": _compiler_command(path, binary)}
        args = [str(binary), "--algorithm", str(case["algorithm"]), "--digits", str(case.get("digits", 10))]
        try:
            extra = {"preexec_fn": (lambda: _limit_memory(memory_mb))} if resource is not None else {}
            # A compilação já terminou. O intervalo medido cobre apenas a execução
            # do processo C (incluindo inicialização e captura da saída).
            started = time.perf_counter()
            proc = subprocess.Popen(args, cwd=td, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace", **extra)
            pico_memoria_kb = None
            while proc.poll() is None:
                if os.name == "posix":
                    try:
                        status = Path(f"/proc/{proc.pid}/status").read_text(encoding="utf-8")
                        valores = [linha for linha in status.splitlines() if linha.startswith("VmHWM:") or linha.startswith("VmRSS:")]
                        amostras = [float(linha.split()[1]) for linha in valores if len(linha.split()) >= 2]
                        if amostras:
                            pico_memoria_kb = max(pico_memoria_kb or 0, max(amostras))
                    except (FileNotFoundError, OSError, ValueError):
                        pass
                if time.perf_counter() - started > timeout:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    return {"ok": False, "error": f"TimeoutError: excedeu {timeout} segundos", "stdout": stdout, "stderr": stderr,
                            "compile_stderr": getattr(compiled, "stderr", ""), "compile_stdout": getattr(compiled, "stdout", ""), "command": args, "compile_command": _compiler_command(path, binary),
                            "peak_rss_kb": pico_memoria_kb, "elapsed": time.perf_counter() - started}
                time.sleep(0.002)
            stdout, stderr = proc.communicate()
            elapsed = time.perf_counter() - started
        except OSError as exc:
            return {"ok": False, "error": f"falha ao iniciar processo: {exc}", "compile_stderr": getattr(compiled, "stderr", ""),
                    "compile_stdout": getattr(compiled, "stdout", ""), "command": args, "compile_command": _compiler_command(path, binary)}
        if proc.returncode != 0:
            return {"ok": False, "error": f"processo terminou com código {proc.returncode}", "stderr": stderr, "stdout": stdout,
                    "compile_stderr": getattr(compiled, "stderr", ""), "compile_stdout": getattr(compiled, "stdout", ""), "command": args, "compile_command": _compiler_command(path, binary),
                    "returncode": proc.returncode, "peak_rss_kb": pico_memoria_kb, "elapsed": elapsed}
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            return {"ok": False, "error": "saída não contém exatamente uma linha JSON", "stdout": stdout, "stderr": stderr,
                    "compile_stderr": getattr(compiled, "stderr", ""), "compile_stdout": getattr(compiled, "stdout", ""), "command": args, "compile_command": _compiler_command(path, binary),
                    "returncode": proc.returncode, "peak_rss_kb": pico_memoria_kb, "elapsed": elapsed}
        try:
            result = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"JSON inválido: {exc}", "stdout": stdout, "stderr": stderr,
                    "compile_stderr": getattr(compiled, "stderr", ""), "compile_stdout": getattr(compiled, "stdout", ""), "command": args, "compile_command": _compiler_command(path, binary),
                    "returncode": proc.returncode, "peak_rss_kb": pico_memoria_kb, "elapsed": elapsed}
        return {"ok": True, "result": result, "elapsed": elapsed, "peak_rss_kb": pico_memoria_kb,
                "stdout": stdout, "stderr": stderr, "compile_stderr": getattr(compiled, "stderr", ""), "compile_stdout": getattr(compiled, "stdout", ""),
                "command": args, "compile_command": _compiler_command(path, binary), "returncode": proc.returncode}


def timeout_for_case(case, override=None):
    'Determina o tempo limite padrão para uma configuração de teste.'
    if override is not None:
        return float(override)
    if case.get("expect_error"):
        return 5.0
    digits = int(case.get("digits") or 10)
    return 5.0 if digits <= 10 else 20.0


def classify_failure(case, error):
    'Classifica uma falha de execução segundo a taxonomia do benchmark.'
    text = str(error).lower()
    if "timeout" in text or "excedeu" in text:
        return "timeout", "A execução excedeu o timeout configurado."
    if "compile_error" in text:
        return "compile_error", "A submissão não compilou como C11."
    if case.get("expect_error") and ("código" in text or "return" in text or "processo terminou" in text):
        return "expected_invalid_input", "A entrada inválida foi rejeitada pelo programa C."
    if "json" in text:
        return "invalid_result", "A saída do programa não é um único objeto JSON válido."
    return "runtime_exception", "O processo C terminou com erro antes de produzir um resultado válido."


def score(row, case):
    'Compara a saída da submissão com o oráculo e acrescenta as métricas ao registro.'
    result = row.pop("raw_result", None)
    if case.get("expect_error"):
        row.update({"status": "unexpected_success" if result is not None else "error", "correct": result is None,
                    "comparison_type": "invalid_input_contract", "expected_value": "nonzero exit code",
                    "observed_value": "normal return" if result is not None else "nonzero exit code",
                    "correct_digits": None, "absolute_error": None, "relative_error": None,
                    "tolerance": "contrato: código de saída diferente de zero"})
        return row
    if not isinstance(result, dict):
        row.update({"status": "invalid_result", "error": "JSON não é objeto", "correct": False,
                    "comparison_type": "structural_contract", "expected_value": "objeto com value/iterations",
                    "observed_value": repr(result)})
        return row
    row["iterations"] = result.get("iterations")
    row["value"] = str(result.get("value", ""))
    expected = reference_pi(case["digits"])
    metrics = decimal_metrics(row["value"], expected, case["digits"])
    row.update({"expected": expected, "expected_value": expected, "observed_value": row["value"],
                "comparison_type": "decimal_prefix", **metrics, "correct": metrics["correct"]})
    return row


def _write_execution_log(log_dir, row, outcome, source_path):
    'Persiste o log completo de uma execução individual em formato JSON.'
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_case = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(row["case_id"]))
    target = log_dir / f"{safe_case}__repeticao_{row['repetition']}.json"
    payload = {
        "plataforma": row["llm_id"], "tentativa": row["generation_attempt"], "caso": row["case_id"],
        "algoritmo": row["algorithm"], "digitos": row.get("digits"), "repeticao": row["repetition"],
        "codigo_fonte": str(source_path), "comando_compilacao": outcome.get("compile_command", []),
        "comando_execucao": outcome.get("command", []), "tempo_execucao_segundos": outcome.get("elapsed"),
        "pico_memoria_kb": outcome.get("peak_rss_kb"), "codigo_saida": outcome.get("returncode"),
        "resultado_runner": {k: v for k, v in outcome.items() if k not in {"result"}},
        "saida_stdout_completa": outcome.get("stdout", ""), "saida_stderr_completa": outcome.get("stderr", ""),
        "stderr_compilacao_completo": outcome.get("compile_stderr", ""),
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(target.relative_to(RESULTS))


def _evaluate_case(path, llm_id, metadata, prompt_hash, case_index, case, repetition, memory_mb, timeout_override, log_dir):
    'Monta e executa uma avaliação de caso para uma submissão e repetição.'
    case_type = "invalid" if case.get("expect_error") else "decimal"
    row = {"llm_id": llm_id, "model_name": metadata.get("model_version", ""), "prompt_sha256": prompt_hash,
           "case_id": case.get("case_id", str(case_index)), "case_type": case_type, "algorithm": case["algorithm"],
           "digits": case.get("digits"), "case_parameters": {k: v for k, v in case.items() if k != "case_id"},
           "expected_behavior": "nonzero exit code" if case.get("expect_error") else "return valid JSON", "timeout_seconds": timeout_for_case(case, timeout_override),
           "execution_completed": False, "operational_success": False, "error_expected": False,
           "mathematical_correctness": "not_applicable" if case.get("expect_error") else "not_evaluable", "repetition": repetition,
           "generation_attempt": metadata.get("attempt", 1), "status": "error"}
    outcome = run_one(path, case, row["timeout_seconds"], memory_mb)
    row["log_execucao"] = _write_execution_log(log_dir, row, outcome, path)
    if outcome.get("ok"):
        row.update({"status": "ok", "time_seconds": outcome["elapsed"], "peak_rss_kb": outcome.get("peak_rss_kb"), "raw_result": outcome["result"], "execution_completed": True, "operational_success": True})
        row = score(row, case)
        row["mathematical_correctness"] = "not_applicable" if case.get("expect_error") else ("correct" if row.get("correct") else "incorrect")
        if not case.get("expect_error") and row.get("correct") is False:
            row.update({"failure_class": "wrong_answer", "error_type": "wrong_answer", "diagnosis": "A execução terminou, mas o valor retornado não atingiu a precisão exigida pelo caso."})
    else:
        failure, diagnosis = classify_failure(case, outcome.get("error", ""))
        row.update({"error": outcome.get("error", ""), "stderr": outcome.get("stderr", ""), "stdout": outcome.get("stdout", ""), "peak_rss_kb": outcome.get("peak_rss_kb"),
                    "failure_class": failure, "error_type": failure, "diagnosis": diagnosis, "execution_completed": failure != "timeout"})
        if case.get("expect_error") and failure == "expected_invalid_input":
            row.update({"status": "error", "correct": True, "error_expected": True, "operational_success": True})
        else:
            row["mathematical_correctness"] = "not_evaluable"
    return row


def _median(values):
    'Calcula a mediana de uma sequência ou retorna nulo quando não há valores.'
    values = [x for x in values if isinstance(x, (int, float)) and math.isfinite(x)]
    return statistics.median(values) if values else None


def aggregate(rows, static_by_llm):
    """Compatibilidade: qualquer agregação é sempre por algoritmo e arquivo C."""
    return aggregate_algorithms(rows, static_by_llm)


def aggregate_algorithms(rows, static_by_llm=None):
    """Agrega por implementação e algoritmo; nunca combina códigos de provedores distintos."""
    static_by_llm=static_by_llm or {}
    result=[]
    units=sorted({(str(r.get("llm_id","desconhecida")),str(r.get("algorithm"))) for r in rows
                  if r.get("case_type")=="decimal" and r.get("algorithm") and not is_compile_failure(r)})
    cost_analyses=analise_custo_empirica(rows)
    for llm,algorithm in units:
        subset=[r for r in rows if str(r.get("llm_id","desconhecida"))==llm
                and str(r.get("algorithm"))==algorithm and r.get("case_type")=="decimal" and not is_compile_failure(r)]
        groups=group_configurations(subset,"decimal")
        if not groups:
            continue
        outcomes={key:configuration_outcome(group,"decimal") for key,group in groups.items()}
        correct_count=sum(value=="correct" for value in outcomes.values())
        evaluated=[key for key,value in outcomes.items() if value in {"correct","incorrect"}]
        precisions=[min(1.0,(groups[key][0].get("correct_digits") or 0)/max(1,groups[key][0].get("digits") or 1)) for key in evaluated]
        config_times=[_median(configuration_time_medians(group)) for group in groups.values() if configuration_time_medians(group)]
        code_analysis=static_by_llm.get(llm,{}).get("analise_codigo",{}).get(algorithm)
        analysis_by_impl={llm:code_analysis} if code_analysis else {}
        result.append({"llm_id":llm,"algorithm":algorithm,"cases":len(groups),"unique_configurations":len(groups),
                       "timing_measurements":sum(r.get("status")=="ok" and isinstance(r.get("time_seconds"),(int,float)) for r in subset),
                       "correct_cases":correct_count,
                       "incorrect_configurations":sum(value=="incorrect" for value in outcomes.values()),
                       "execution_failure_configurations":sum(value=="execution_failure" for value in outcomes.values()),
                       "inconsistent_configurations":sum(value=="inconsistent" for value in outcomes.values()),
                       "evaluated_cases":len(evaluated),"implementations":1,
                       "functional_accuracy":correct_count/len(groups),
                       "precision_score":statistics.mean(precisions) if precisions else 0.0,
                       "median_time_seconds":_median(config_times),
                       "analise_assintotica":analise_do_algoritmo(algorithm),"analise_codigo_por_submissao":analysis_by_impl})
    fastest=min([r["median_time_seconds"] for r in result if r["median_time_seconds"]] or [1.0])
    for r in result:
        r["performance_score"]=min(1.0,fastest/r["median_time_seconds"]) if r["median_time_seconds"] else 0.0
        r["empirical_score"]=None if not r["evaluated_cases"] else 100*(0.50*r["functional_accuracy"]+0.35*r["precision_score"]+0.15*r["performance_score"])
        r["score_status"]="not_evaluable_no_valid_execution" if not r["evaluated_cases"] else "provisional_single_implementation"
        r["analise_custo_empirica"]=cost_analyses.get(f"{r['llm_id']}/{r['algorithm']}",{})
    return sorted(result,key=lambda r:(-(r["empirical_score"] if r["empirical_score"] is not None else -1),r["llm_id"],r["algorithm"]))

def execution_summary(rows, wall_time_seconds, started_utc, finished_utc):
    """Resume desfechos por método implementado, sem agregar por origem do código."""
    decimal_groups = group_configurations(rows, "decimal")
    invalid_groups = group_configurations(rows, "invalid")
    by_method = {}
    pairs = sorted({(key[0], key[1]) for key in decimal_groups})
    for provider, algorithm in pairs:
        groups = {key: group for key, group in decimal_groups.items() if key[0] == provider and key[1] == algorithm}
        outcomes = [configuration_outcome(group, "decimal") for group in groups.values()]
        per_config_time = [_median(configuration_time_medians(group)) for group in groups.values() if configuration_time_medians(group)]
        by_method[f"{provider}/{algorithm}"] = {
            "configuracoes_unicas": len(groups),
            "desfechos": {name: outcomes.count(name) for name in ("correct", "incorrect", "execution_failure", "inconsistent")},
            "mediana_dos_tempos_medianos_segundos": _median(per_config_time),
        }
    invalid_outcomes = [configuration_outcome(group, "invalid") for group in invalid_groups.values()]
    failed_sources = sorted({str(row.get("llm_id")) for row in rows if is_compile_failure(row)})
    measurements = [r for r in rows if r.get("case_type")=="decimal" and isinstance(r.get("time_seconds"), (int, float)) and r.get("time_seconds") > 0]
    return {
        "inicio_utc": started_utc,
        "fim_utc": finished_utc,
        "tempo_total_parede_segundos": wall_time_seconds,
        "linhas_brutas_de_repeticao_preservadas_somente_para_auditoria": len(rows),
        "configuracoes_decimais_unicas": len(decimal_groups),
        "medicoes_de_tempo_repetidas": len(measurements),
        "casos_invalidos_unicos_rejeitados": invalid_outcomes.count("rejected"),
        "falhas_unicas_no_gate_de_compilacao": len(failed_sources),
        "origens_com_falha_no_gate": failed_sources,
        "por_metodo_implementado": by_method,
        "observacao": "Cada configuração algoritmo-precisão tem um desfecho; repetições são usadas somente para sumarizar o tempo. Não há agregação ou score por origem de IA.",
    }


def load_cases(smoke=False):
    """Retorna (casas decimais testadas, casos inválidos). Os casos decimais são expandidos por algoritmo declarado."""
    data = json.loads((ROOT / "benchmark" / "cases.json").read_text(encoding="utf-8"))
    return (data["decimal_digits"][:2], data["invalid"][:1]) if smoke else (data["decimal_digits"], data["invalid"])


def cases_for(algorithms, decimal_digits, invalid):
    'Expande os casos-base para cada algoritmo declarado pela submissão.'
    first = algorithms[0] if algorithms else "unknown"
    cases = [{"case_id": f"{name}_{digits}", "algorithm": name, "digits": digits} for name in algorithms for digits in decimal_digits]
    for case in invalid:
        case = dict(case)
        if case["algorithm"] == "$first":
            case["algorithm"] = first
        cases.append(case)
    return cases


def main():
    'Executa o fluxo principal do módulo ou da ferramenta de coleta.'
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--memory-mb", type=int, default=1024)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--workers", type=int, default=max(1, min(os.cpu_count() or 1, 4)))
    args = parser.parse_args()
    if args.repetitions < 1 or args.workers < 1:
        raise SystemExit("--repetitions e --workers devem ser >= 1")
    RESULTS.mkdir(exist_ok=True)
    logs_root = RESULTS / "logs"
    if logs_root.exists():
        import shutil
        shutil.rmtree(logs_root)
    logs_root.mkdir(parents=True, exist_ok=True)
    started_wall = time.perf_counter()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    decimal_digits, invalid_cases = load_cases(args.smoke)
    repetitions = 1 if args.smoke else args.repetitions
    prompt_hash = hashlib.sha256(PROMPT.read_bytes()).hexdigest() if PROMPT.exists() else ""
    rows, static_by_llm, jobs = [], {}, []
    for llm_id, directory, metadata in submission_entries():
        path = directory / "submission.c"
        static_by_llm[llm_id] = static_checks(path) if path.exists() else {"static_ok": False}
        if not path.exists():
            rows.append({"llm_id": llm_id, "status": "missing_submission.c"})
            continue
        cases = cases_for(static_by_llm[llm_id].get("selected_algorithms", []), decimal_digits, invalid_cases)
        if not static_by_llm[llm_id].get("compile_ok", static_by_llm[llm_id].get("syntax_ok", False)):
            rows.append({"llm_id": llm_id, "model_name": metadata.get("model_version", ""),
                         "generation_attempt": metadata.get("attempt", path.parent.name),
                         "case_type": "submission", "status": "compile_error", "failure_class": "compile_error",
                         "error": "compile_error", "diagnosis": "A submissão falhou no gate de compilação; nenhum caso de execução foi repetido.",
                         "compile_error": static_by_llm[llm_id].get("compile_error", ""),
                         "planned_cases_skipped": len(cases) * repetitions,
                         "source_sha256": static_by_llm[llm_id].get("source_sha256")})
            continue
        for case_index, case in enumerate(cases):
            for repetition in range(repetitions):
                attempt_name = str(metadata.get("attempt", path.parent.name))
                log_dir = logs_root / llm_id / attempt_name
                jobs.append((len(jobs), path, llm_id, metadata, prompt_hash, case_index, case, repetition, args.memory_mb, args.timeout, log_dir))
    print(f"Executando {len(jobs)} casos com até {min(args.workers, max(1, len(jobs)))} workers paralelos")
    result_map = {}
    with ThreadPoolExecutor(max_workers=min(args.workers, max(1, len(jobs)))) as pool:
        futures = {pool.submit(_evaluate_case, *job[1:]): job[0] for job in jobs}
        for index, future in ((futures[f], f) for f in as_completed(futures)):
            result_map[index] = future.result()
    rows.extend(result_map[i] for i in sorted(result_map))
    finished_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary = execution_summary(rows, time.perf_counter() - started_wall, started_utc, finished_utc)
    results_payload = {"records": rows, "execution_summary": summary}
    (RESULTS / "results.json").write_text(json.dumps(results_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    analise_por_submissao = {
        f"{llm_id}/{static_by_llm.get(llm_id, {}).get('attempt', 'attempt_01')}": {
            "llm_id": llm_id,
            "arquivo_codigo": static_by_llm.get(llm_id, {}).get("source_path", ""),
            "sha256_codigo": static_by_llm.get(llm_id, {}).get("source_sha256", ""),
            "compila": static_by_llm.get(llm_id, {}).get("compile_ok", False),
            "algoritmos": static_by_llm.get(llm_id, {}).get("analise_codigo", {}),
        }
        for llm_id in sorted(static_by_llm)
    }
    (RESULTS / "individual_code_analysis.json").write_text(json.dumps(analise_por_submissao, indent=2, ensure_ascii=False), encoding="utf-8")
    (RESULTS / "algorithm_ranking.json").write_text(json.dumps({"comparison_unit": "método implementado: algoritmo declarado + arquivo C de origem", "provenance_note": "llm_id identifica somente a origem do código; não representa score comparativo do modelo", "method": "empírica; análise estática individual de cada submission.c; análise teórica geral e ajuste empírico mantidos separadamente", "ranking": aggregate_algorithms(rows, static_by_llm), "analise_codigo_por_submissao": analise_por_submissao}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Gerados {len(rows)} registros em {RESULTS}")


if __name__ == "__main__":
    main()
