#!/usr/bin/env python3
"""QP4 -- medição independente de custo por contagem de execução de linhas (gcov).

Uso: python tools/qp4_medicao_independente.py . [SAIDA_JSON]

Por que existe: o campo `iterations` é informado pelo próprio programa avaliado e,
em princípio, poderia ser enganoso. Aqui cada submission.c é recompilado SEM alteração
de lógica (apenas -O0 --coverage, em vez de -O2) e, para cada d = 1..18, o gcov informa
quantas vezes cada linha do código foi executada. Duas grandezas independentes do
contador informado são registradas:
  * L(d): soma das contagens de execução de todas as linhas (proxy de operações);
  * H(d): maior contagem de uma única linha (estimativa do laço mais quente).
Também é registrado o `iterations` informado, para compará-lo com L e H.

Observação: ChatGPT/euler aborta (abort() não grava o .gcda) e é registrado como sem
medição, coerente com o artigo (falha de execução em todas as precisões).
Não substitui results.json; é uma medição complementar.
"""
import gzip, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
saida = Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "results/complementar/qp4_gcov.json"
DIGITS = range(1, 19)
TIMEOUT = 300
IMPLS = {
    "chatgpt": ["machin7", "gauss", "machin", "atan23", "euler"],
    "claude": ["chudnovsky", "ramanujan", "takano", "machin", "euler"],
    "gemini": ["machin", "euler", "newton", "nilakantha", "ramanujan"],
    "grok": ["nilakantha", "machin", "gauss", "hutton", "twinarctan"],
}


def medir(exe, workdir, alg, d):
    for f in workdir.glob("*.gcda"):
        f.unlink()
    for f in workdir.glob("*.gcov.json.gz"):
        f.unlink()
    p = subprocess.run([str(exe), "--algorithm", alg, "--digits", str(d)],
                       capture_output=True, text=True, timeout=TIMEOUT, cwd=workdir)
    if p.returncode != 0 or not (workdir / "s.gcda").exists():
        return None
    saida_json = json.loads(p.stdout.strip().splitlines()[-1])
    subprocess.run(["gcov", "-j", "s.c"], cwd=workdir, capture_output=True, check=True)
    dados = json.load(gzip.open(workdir / "s.c.gcov.json.gz" if (workdir / "s.c.gcov.json.gz").exists()
                                else workdir / "s.gcov.json.gz"))
    cont = [l["count"] for f in dados["files"] for l in f["lines"]]
    return {"iterations_informadas": saida_json["iterations"], "L": sum(cont), "H": max(cont),
            "linhas_executadas": sum(1 for c in cont if c > 0)}


res = {}
for origem, algs in IMPLS.items():
    src = repo / "submissions" / origem / "attempt_01" / "submission.c"
    w = Path(tempfile.mkdtemp())
    shutil.copy(src, w / "s.c")
    c = subprocess.run(["gcc", "-std=c11", "-O0", "--coverage", "-Wall", "-Wextra", "s.c", "-lm", "-o", "s"],
                       cwd=w, capture_output=True, text=True)
    if c.returncode != 0:
        sys.exit(f"falha de compilacao {origem}: {c.stderr[:300]}")
    for alg in algs:
        for d in DIGITS:
            try:
                m = medir(w / "s", w, alg, d)
            except subprocess.TimeoutExpired:
                m = None
            res.setdefault(f"{origem}/{alg}", {})[str(d)] = m
        print(origem, alg, "ok" if res[f"{origem}/{alg}"]["18"] else "sem medicao", flush=True)

saida.parent.mkdir(parents=True, exist_ok=True)
saida.write_text(json.dumps({"compilacao": "gcc -std=c11 -O0 --coverage", "digitos": list(DIGITS),
                             "medidas": res}, indent=1))
print("salvo em", saida)
