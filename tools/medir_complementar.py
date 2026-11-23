#!/usr/bin/env python3
"""Medição complementar de memória de pico e latência (sequencial, CPU fixada).

Uso: python tools/medir_complementar.py . [SAIDA_JSON]

Diferenças em relação à rodada original do runner:
  * memória de pico lida de ru_maxrss via os.wait4 (exata, sem polling);
  * execução sequencial em uma única CPU (os.sched_setaffinity);
  * uma execução de aquecimento descartada, depois N=10 repetições.
É uma medição COMPLEMENTAR, em outra máquina; não substitui results.json.
"""
import json, os, platform, subprocess, sys, tempfile, time, statistics, resource
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
saida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/complementar/medicao_complementar.json")
N = 10
DIGITS = (1, 9, 18)
IMPLS = {  # origem -> algoritmos declarados (iguais aos do results.json da rodada)
    "chatgpt": ["machin7", "gauss", "machin", "atan23", "euler"],
    "claude": ["chudnovsky", "ramanujan", "takano", "machin", "euler"],
    "gemini": ["machin", "euler", "newton", "nilakantha", "ramanujan"],
    "grok": ["nilakantha", "machin", "gauss", "hutton", "twinarctan"],
}
cpus = sorted(os.sched_getaffinity(0))
os.sched_setaffinity(0, {cpus[-1]})

# ru_maxrss de um filho herda o pico do processo que fez fork (o Python, ~16 MiB),
# o que mascararia a memória real. Por isso o filho é lançado por um lançador C
# mínimo (~1 MiB), que imprime o ru_maxrss do alvo.
LAUNCHER = r"""
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <fcntl.h>
int main(int c, char **v) {
    pid_t p = fork();
    if (p == 0) { int n = open("/dev/null", O_WRONLY); dup2(n, 1); dup2(n, 2); execv(v[1], v + 1); _exit(127); }
    int st; struct rusage ru; wait4(p, &st, 0, &ru);
    printf("%ld\n", ru.ru_maxrss);
    return 0;
}
"""
_ld = Path(tempfile.mkdtemp())
(_ld / "l.c").write_text(LAUNCHER)
subprocess.run(["gcc", "-O2", "-o", str(_ld / "l"), str(_ld / "l.c")], check=True)

def uma(exe, alg, d):
    t0 = time.perf_counter()
    out = subprocess.run([str(_ld / "l"), str(exe), "--algorithm", alg, "--digits", str(d)],
                         capture_output=True, text=True).stdout
    return time.perf_counter() - t0, int(out.strip())  # KiB no Linux

dados = {"ambiente": {"plataforma": platform.platform(), "python": platform.python_version(),
                      "cpu_fixada": cpus[-1], "n_cpus_visiveis": len(cpus),
                      "gcc": subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.splitlines()[0],
                      "repeticoes": N, "aquecimento": 1,
                      "modelo_cpu": next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "?")},
         "medidas": {}}
with tempfile.TemporaryDirectory() as td:
    for origem, algs in IMPLS.items():
        exe = Path(td) / f"{origem}.out"
        r = subprocess.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-o", str(exe),
                            str(repo / f"submissions/{origem}/attempt_01/submission.c"), "-lm"], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        # processo vazio de referência (piso do sistema)
        for alg in algs:
            for d in DIGITS:
                uma(exe, alg, d)
                ts, ms = zip(*(uma(exe, alg, d) for _ in range(N)))
                dados["medidas"][f"{origem}/{alg}/{d}"] = {
                    "latencia_mediana_s": statistics.median(ts), "latencia_min_s": min(ts), "latencia_max_s": max(ts),
                    "pico_memoria_kib_mediana": statistics.median(ms), "pico_memoria_kib_max": max(ms)}
# piso: processo C trivial
triv = Path(tempfile.mkdtemp()) / "t.c"
triv.write_text("int main(void){return 0;}")
subprocess.run(["gcc", "-O2", "-o", str(triv.with_suffix("")), str(triv)], check=True)
ts, ms = zip(*(uma(triv.with_suffix(""), "x", 1) for _ in range(N * 5)))
dados["piso_processo_vazio"] = {"latencia_mediana_s": statistics.median(ts), "pico_memoria_kib_mediana": statistics.median(ms)}
saida.parent.mkdir(parents=True, exist_ok=True)
saida.write_text(json.dumps(dados, indent=1, ensure_ascii=False))
print("ok", len(dados["medidas"]))
