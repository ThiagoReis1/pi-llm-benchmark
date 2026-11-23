#!/usr/bin/env python3
"""Teste de intervenção (contrafactual) das causas-raiz D1, D2 e D3.

Uso: python tools/reparos_contrafactuais.py . [SAIDA_JSON]

Para cada defeito aplica a menor alteração textual que corrige a causa
apontada, compila a cópia (o original nunca é modificado) e confere as 18
precisões contra o oráculo mpmath do próprio benchmark. D2 não é "consertado":
a cópia é apenas instrumentada para registrar onde a subtração falha.
"""
import json, subprocess, sys, tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
saida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/complementar/reparos_contrafactuais.json")
sys.path.insert(0, str(repo))
from benchmark.reference import reference_pi, decimal_metrics  # noqa: E402

def aplicar(src, trocas):
    for velho, novo in trocas:
        assert src.count(velho) == 1, f"trecho não único/ausente: {velho[:50]!r}"
        src = src.replace(velho, novo)
    return src

def rodar(codigo, alg, d, cwd):
    exe = Path(cwd) / "a.out"
    r = subprocess.run(["gcc", "-std=c11", "-O2", "-o", str(exe), str(codigo), "-lm"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr)
    p = subprocess.run([str(exe), "--algorithm", alg, "--digits", str(d)], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(p.stdout), p.returncode, p.stderr
    except Exception:
        return None, p.returncode, p.stderr

def avaliar(codigo, alg, cwd):
    # compila uma vez por chamada de rodar(); 18 precisões
    ok, saidas = [], []
    for d in range(1, 19):
        res, rc, err = rodar(codigo, alg, d, cwd)
        if res is None:
            ok.append(False); saidas.append(None); continue
        m = decimal_metrics(str(res["value"]), reference_pi(d), d)
        ok.append(bool(m["correct"])); saidas.append(res["value"])
    return ok, saidas

resultados = {}
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # ---- D1: recorrência do termo da série de arco-tangente (ChatGPT) ----
    src = (repo / "submissions/chatgpt/attempt_01/submission.c").read_text()
    fix = aplicar(src, [
        ("if (!big_mul_small(&next, &term, (uint32_t)num2)) {",
         "if (!big_mul_small(&next, &term, (uint32_t)(num2 * odd1))) {"),
        ("uint64_t divisor = den2 * odd1 * odd3;", "uint64_t divisor = den2 * odd3;"),
    ])
    (td / "d1.c").write_text(fix)
    for alg in ("atan23", "gauss", "machin", "machin7"):
        ok, _ = avaliar(td / "d1.c", alg, td)
        orig, _ = avaliar(repo / "submissions/chatgpt/attempt_01/submission.c", alg, td)
        resultados[f"D1/{alg}"] = {"original_corretas": sum(orig), "reparado_corretas": sum(ok), "precisoes_reparado": ok}
    # M1: D1 + escala errada (64 e 16 dão 4*pi; os coeficientes corretos são 16 e 4)
    fix4 = aplicar(fix, [
        ("big_add_mul_small(&out->value, &a, 64, 0)", "big_add_mul_small(&out->value, &a, 16, 0)"),
        ("big_mul_small(&t, &b, 16)", "big_mul_small(&t, &b, 4)"),
    ])
    (td / "d1d4.c").write_text(fix4)
    ok, _ = avaliar(td / "d1d4.c", "machin", td)
    resultados["D1+D4/machin"] = {"original_corretas": 0, "reparado_corretas": sum(ok), "precisoes_reparado": ok}
    # ---- D3: guarda de 32 bits do Nilakantha (Grok): divisão em três passos ----
    src = (repo / "submissions/grok/attempt_01/submission.c").read_text()
    fix = aplicar(src, [
        ("""        uint64_t den = (uint64_t)(2 * k) * (2 * k + 1) * (2 * k + 2);
        if (den == 0 || den > UINT32_MAX) {
            /* overflow guard ? stop */
            break;
        }
        bi_copy(&tmp, &term);
        bi_div_small(&tmp, &tmp, (uint32_t)den);
""", """        bi_copy(&tmp, &term);
        bi_div_small(&tmp, &tmp, 2 * k);
        bi_div_small(&tmp, &tmp, 2 * k + 1);
        bi_div_small(&tmp, &tmp, 2 * k + 2);
"""),
        ("if (iters > 5000000) break;", "if (iters > 50000000) break;"),
    ])
    (td / "d3.c").write_text(fix)
    ok, saidas = avaliar(td / "d3.c", "nilakantha", td)
    orig, _ = avaliar(repo / "submissions/grok/attempt_01/submission.c", "nilakantha", td)
    resultados["D3/nilakantha"] = {"original_corretas": sum(orig), "reparado_corretas": sum(ok), "precisoes_reparado": ok}
    # ---- D2: instrumentação do ponto exato de falha (ChatGPT, euler) ----
    src = (repo / "submissions/chatgpt/attempt_01/submission.c").read_text()
    inst = aplicar(src, [
        ("""                if (!big_sub(&d, &differences[j], &differences[j + 1])) {
                    return 0;""", """                if (!big_sub(&d, &differences[j], &differences[j + 1])) {
                    fprintf(stderr, "D2 k=%u j=%zu\\n", k, j);
                    return 0;"""),
    ])
    (td / "d2.c").write_text(inst)
    res, rc, err = rodar(td / "d2.c", "euler", 18, td)
    resultados["D2/euler"] = {"codigo_saida": rc, "stderr": err.strip().splitlines()}

saida.parent.mkdir(parents=True, exist_ok=True)
saida.write_text(json.dumps(resultados, indent=2, ensure_ascii=False))
print(json.dumps(resultados, indent=1, ensure_ascii=False))
