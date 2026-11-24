#!/usr/bin/env python3
"""QP4 -- extensões: intervenção no Grok (E1), faixa além de d = 18 (E2) e instruções com -O2 (E3).

Uso:
    python tools/qp4_extensoes.py . [DIR_ARTIGO] [--reanalisar] [--so E1,E2,E3]

Critérios: protocolo/qp4_extensoes_criterios.md (escritos antes da medição; o SHA-256 do
arquivo é gravado na saída). Cada submission.c é copiado e alterado em uma CÓPIA; os
originais nunca são editados.

Saídas:
    results/complementar/qp4_extensoes.json      medidas brutas e vereditos
    DIR_ARTIGO/tabelas/benchmark/qp4_ext_macros.tex   macros numéricas do artigo (opcional)
    DIR_ARTIGO/tabelas/benchmark/qp4_ext_tabelas.tex  tabelas do apêndice (opcional)

Requer gcc, gcov, valgrind (E3), numpy, scipy e mpmath.
"""
import gzip, hashlib, json, math, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qp4_comum import FMT, COD, ORIG, SERIES, ESTATICA, LIM_KAPPA, selecionar  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
repo = Path(args[0]).resolve()
art = Path(args[1]).resolve() if len(args) > 1 else None
REANALISAR = "--reanalisar" in sys.argv
SO = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--so=")), ["E1", "E2", "E3"])
sys.path.insert(0, str(repo))
from benchmark.reference import reference_pi, decimal_metrics  # noqa: E402

SAIDA = repo / "results/complementar/qp4_extensoes.json"
CRITERIOS = repo / "protocolo/qp4_extensoes_criterios.md"
IMPLS = {
    "chatgpt": ["machin7", "gauss", "machin", "atan23", "euler"],
    "claude": ["chudnovsky", "ramanujan", "takano", "machin", "euler"],
    "gemini": ["machin", "euler", "newton", "nilakantha", "ramanujan"],
    "grok": ["nilakantha", "machin", "gauss", "hutton", "twinarctan"],
}
GROK_ARCTAN = ["machin", "gauss", "hutton", "twinarctan"]
CC = ["gcc", "-std=c11", "-Wall", "-Wextra"]
FLAGS_RODADA = ["-O2"]                       # opções da rodada original
FLAGS_GCOV = ["-O0", "--coverage"]           # opções da medição QP4
TIMEOUT = 600


# ------------------------------------------------------------------ utilidades
def aplicar(src, trocas):
    """Aplica substituições textuais, cada uma exatamente uma vez."""
    for velho, novo in trocas:
        assert src.count(velho) == 1, f"trecho ausente ou repetido: {velho[:60]!r}"
        src = src.replace(velho, novo)
    return src


def compilar(texto, flags, wd, nome="s"):
    (wd / f"{nome}.c").write_text(texto)
    r = subprocess.run(CC + flags + [f"{nome}.c", "-lm", "-o", nome], cwd=wd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"falha de compilação ({nome}): {r.stderr[:400]}")
    return wd / nome


def rodar(exe, alg, d, cwd):
    p = subprocess.run([str(exe), "--algorithm", alg, "--digits", str(d)], capture_output=True, text=True,
                       timeout=TIMEOUT, cwd=cwd)
    try:
        j = json.loads(p.stdout.strip().splitlines()[-1])
        return {"value": j["value"], "iterations": j["iterations"], "rc": p.returncode}
    except Exception:
        return {"value": None, "iterations": None, "rc": p.returncode}


def correto(value, d):
    if value is None:
        return False
    return bool(decimal_metrics(str(value), reference_pi(d), d)["correct"])


def gcov_medir(exe, wd, alg, d):
    for f in list(wd.glob("*.gcda")) + list(wd.glob("*.gcov.json.gz")):
        f.unlink()
    r = rodar(exe, alg, d, wd)
    if r["rc"] != 0 or r["value"] is None or not (wd / "s.gcda").exists():
        return None
    subprocess.run(["gcov", "-j", "s.c"], cwd=wd, capture_output=True, check=True)
    g = wd / "s.c.gcov.json.gz"
    dados = json.load(gzip.open(g if g.exists() else wd / "s.gcov.json.gz"))
    cont = [l["count"] for f in dados["files"] for l in f["lines"]]
    return {**r, "H": max(cont), "L": sum(cont)}


def src_original(origem):
    return (repo / "submissions" / origem / "attempt_01" / "submission.c").read_text()


# ------------------------------------------------------------------ E1: Grok com limbs fixos
def grok_fixl(src, k):
    """Cópia em que todo BigInt tem sempre n = FIXL limbs (sem encolher nem crescer)."""
    return aplicar(src, [
        ("#define GUARD 8\n", f"#define GUARD 8\n#define FIXL {k}\n"),
        ("    memset(a->d, 0, sizeof(a->d));\n    a->n = 1;\n", "    memset(a->d, 0, sizeof(a->d));\n    a->n = FIXL;\n"),
        ("    a->n = a->d[1] ? 2 : 1;\n", "    a->n = FIXL;\n"),
        ("        carry = s / BASE;\n        t.n = i + 1;\n    }\n    *r = t;\n",
         "        carry = s / BASE;\n        t.n = i + 1;\n    }\n    t.n = FIXL;\n    *r = t;\n"),
        ("        t.n = i + 1;\n    }\n    while (t.n > 1 && t.d[t.n - 1] == 0) t.n--;\n    *r = t;\n",
         "        t.n = i + 1;\n    }\n    t.n = FIXL;\n    *r = t;\n"),
        ("        carry = p / BASE;\n        t.n = i + 1;\n    }\n    *r = t;\n",
         "        carry = p / BASE;\n        t.n = i + 1;\n    }\n    t.n = FIXL;\n    *r = t;\n"),
        ("    t.n = a->n;\n    while (t.n > 1 && t.d[t.n - 1] == 0) t.n--;\n    *r = t;\n",
         "    t.n = FIXL;\n    *r = t;\n"),
    ])


def medir_e1():
    src = src_original("grok")
    res = {"original": {}, "FIXL3": {}, "FIXL6": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for nome, texto in (("original", src), ("FIXL3", grok_fixl(src, 3)), ("FIXL6", grok_fixl(src, 6))):
            wd = td / nome
            wd.mkdir()
            exe = compilar(texto, FLAGS_GCOV, wd)
            for alg in GROK_ARCTAN:
                res[nome][alg] = {str(d): gcov_medir(exe, wd, alg, d) for d in range(1, 19)}
            print("E1", nome, "ok", flush=True)
    return res


# ------------------------------------------------------------------ E2a: Claude além de d = 18
def claude_copia(src, fr, nl, dmax):
    return aplicar(src, [
        ("#define NL 12 ", f"#define NL {nl} "),
        ("#define FR 5 ", f"#define FR {fr} "),
        ("    if (digits < 1 || digits > 18) {", f"    if (digits < 1 || digits > {dmax}) {{"),
    ])


def medir_e2a():
    src = src_original("claude")
    res = {"A": {}, "B": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "A").mkdir(); (td / "B").mkdir()
        # A: só remove a verificação de faixa; escala interna original de 45 casas
        exeA = compilar(aplicar(src, [("    if (digits < 1 || digits > 18) {", "    if (digits < 1 || digits > 44) {")]),
                        FLAGS_RODADA, td / "A")
        # B: escala ampliada (90 casas); NL = 2*FR + 2 para a divisão longa de big_div_fixed
        exeB = compilar(claude_copia(src, 10, 22, 80), FLAGS_RODADA, td / "B")
        for alg in IMPLS["claude"]:
            res["A"][alg] = {}
            for d in [18] + list(range(19, 45)):
                r = rodar(exeA, alg, d, td / "A")
                r["correto"] = correto(r["value"], d)
                res["A"][alg][str(d)] = r
            res["B"][alg] = {}
            for d in (1, 18, 44, 80):
                r = rodar(exeB, alg, d, td / "B")
                r["correto"] = correto(r["value"], d)
                res["B"][alg][str(d)] = r
            print("E2a", alg, "ok", flush=True)
    return res


# ------------------------------------------------------------------ E2b: Grok além de d = 18
def grok_alem(src, dmax):
    return aplicar(src, [
        ("d < 1 || d > 18)", f"d < 1 || d > {dmax})"),
        ("    char digs[64];\n", "    char digs[128];\n"),
        ("        if (nd >= 60) break;\n", "        if (nd >= 120) break;\n"),
        ("    char out[40];\n", "    char out[128];\n"),
        ("    char frac[20];\n", "    char frac[128];\n"),
        ("    char value[64];\n", "    char value[128];\n"),
    ])


def medir_e2b(dmax=50):
    src = src_original("grok")
    res = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        exe = compilar(grok_alem(src, dmax), FLAGS_GCOV, td)
        for alg in GROK_ARCTAN:
            res[alg] = {}
            for d in range(1, dmax + 1):
                m = gcov_medir(exe, td, alg, d)
                if m is not None:
                    m["correto"] = correto(m["value"], d)
                res[alg][str(d)] = m
            print("E2b", alg, "ok", flush=True)
    return res


# ------------------------------------------------------------------ E3: instruções com -O2 (callgrind)
def callgrind_ir(exe, alg, d, wd):
    out = wd / "cg.out"
    cmd = ["valgrind", "--tool=callgrind", f"--callgrind-out-file={out}", str(exe)]
    if alg is not None:
        cmd += ["--algorithm", alg, "--digits", str(d)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, cwd=wd)
    m = re.search(r"Collected\s*:\s*(\d+)", p.stderr)
    if not m:
        return None
    it = None
    try:
        it = json.loads(p.stdout.strip().splitlines()[-1])["iterations"]
    except Exception:
        pass
    return {"Ir": int(m.group(1)), "iterations": it, "rc": p.returncode}


def medir_e3():
    res = {"vazio": None, "medidas": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        wd = td / "vazio"; wd.mkdir()
        exe = compilar("int main(void){return 0;}\n", FLAGS_RODADA, wd, "v")
        res["vazio"] = callgrind_ir(exe, None, 0, wd)
        for origem, algs in IMPLS.items():
            wd = td / origem; wd.mkdir()
            exe = compilar(src_original(origem), FLAGS_RODADA, wd, "o")
            for alg in algs:
                if (origem, alg) == ("chatgpt", "euler"):
                    continue                      # aborta em todo d (D2): sem medida
                res["medidas"][f"{origem}/{alg}"] = {str(d): callgrind_ir(exe, alg, d, wd) for d in range(1, 19)}
                print("E3", origem, alg, "ok", flush=True)
    return res


# ------------------------------------------------------------------ análise dos critérios
def razao_kappa(Hn, d_a, d_b):
    return Hn[d_b] / Hn[d_a]


def analisar(M):
    V, mac = {}, {}
    # ---- E1
    if "E1" in M:
        E = M["E1"]
        c1 = True
        kap = {}
        hn18 = {}
        for nome in ("FIXL3", "FIXL6"):
            for alg in GROK_ARCTAN:
                hn = {}
                for d in range(1, 19):
                    o, c = E["original"][alg][str(d)], E[nome][alg][str(d)]
                    if c is None or o is None or c["value"] != o["value"] or c["iterations"] != o["iterations"]:
                        c1 = False
                    if c is not None:
                        hn[d] = c["H"] / c["iterations"]
                if len(hn) == 18:
                    kap[f"{nome}/{alg}"] = hn[18] / hn[5]
                    hn18[f"{nome}/{alg}"] = hn[18]
        orig_kap = {alg: (E["original"][alg]["18"]["H"] / E["original"][alg]["18"]["iterations"]) /
                         (E["original"][alg]["5"]["H"] / E["original"][alg]["5"]["iterations"]) for alg in GROK_ARCTAN}
        c2 = bool(kap) and all(v <= LIM_KAPPA for v in kap.values())
        c3 = all(hn18[f"FIXL6/{a}"] > hn18[f"FIXL3/{a}"] for a in GROK_ARCTAN if f"FIXL6/{a}" in hn18)
        V["E1"] = {"c1_resultado_preservado": c1, "c2_causa_sustentada": c2, "c3_dose_resposta": c3,
                   "kappa_original": orig_kap, "kappa_fixl": kap, "HN18": hn18}
        mac.update({"EUmKappaFixMax": FMT(max(kap.values()), 2), "EUmKappaFixMin": FMT(min(kap.values()), 2),
                    "EUmKappaOrigMin": FMT(min(orig_kap.values()), 2), "EUmKappaOrigMax": FMT(max(orig_kap.values()), 2),
                    "EUmFixTresMin": FMT(min(hn18[f"FIXL3/{a}"] for a in GROK_ARCTAN), 1),
                    "EUmFixTresMax": FMT(max(hn18[f"FIXL3/{a}"] for a in GROK_ARCTAN), 1),
                    "EUmFixSeisMin": FMT(min(hn18[f"FIXL6/{a}"] for a in GROK_ARCTAN), 1),
                    "EUmFixSeisMax": FMT(max(hn18[f"FIXL6/{a}"] for a in GROK_ARCTAN), 1)})
    # ---- E2a
    if "E2a" in M:
        A, B = M["E2a"]["A"], M["E2a"]["B"]
        out = {}
        a1 = a2 = True
        a3_refutado, a3_testavel = False, []
        for alg in IMPLS["claude"]:
            cod = COD[("claude", alg)]
            delta = SERIES[cod][0]
            n18 = A[alg]["18"]["iterations"]
            ds = sorted(int(k) for k in A[alg])
            if any(A[alg][str(d)]["iterations"] != n18 for d in ds):
                a1 = False
            nB = B[alg]["18"]["iterations"]
            if not (nB is not None and n18 is not None and nB > n18):
                a2 = False
            # a faixa 1..18 já é toda correta no Claude (QP1); conta-se o prefixo contíguo correto a partir dela
            dmaxA = 18 if A[alg]["18"]["correto"] else 0
            for d in range(19, 45):
                if dmaxA == d - 1 and A[alg][str(d)]["correto"]:
                    dmaxA = d
            dsupA = n18 * delta
            for d in ds:
                if d > dsupA:
                    a3_testavel.append(f"{alg}@{d}")
                    if A[alg][str(d)]["correto"]:
                        a3_refutado = True
            dmaxB = max((int(k) for k, r in B[alg].items() if r["correto"]), default=0)
            out[alg] = {"N_A18": n18, "N_B18": nB, "N_B80": B[alg]["80"]["iterations"], "dmax_A": dmaxA,
                        "dsup_A": dsupA, "dsup_B": (nB * delta if nB else None), "dmax_B_testado": dmaxB,
                        "B_corretos": {k: r["correto"] for k, r in B[alg].items()}}
        V["E2a"] = {"a1_N_constante_na_escala": a1, "a2_escala_maior_mais_termos": a2,
                    "a3_limite_refutado": a3_refutado, "a3_pontos_testaveis": a3_testavel, "por_impl": out}
        mac["EDnAmin"] = FMT(min(o["N_A18"] for o in out.values()), 0)
        mac["EDnAmax"] = FMT(max(o["N_A18"] for o in out.values()), 0)
        mac["EDrazaoNmin"] = FMT(min(o["N_B18"] / o["N_A18"] for o in out.values()), 2)
        mac["EDrazaoNmax"] = FMT(max(o["N_B18"] / o["N_A18"] for o in out.values()), 2)
        mac["EDmaxAMin"] = FMT(min(o["dmax_A"] for o in out.values()), 0)
        mac["EDmaxAMax"] = FMT(max(o["dmax_A"] for o in out.values()), 0)
    # ---- E2b
    if "E2b" in M:
        G = M["E2b"]
        out = {}
        b1 = b2 = b3 = True
        for alg in GROK_ARCTAN:
            cod = COD[("grok", alg)]
            s = SERIES[cod]
            ds = [d for d in range(1, 51) if G[alg][str(d)] is not None]
            N = np.array([G[alg][str(d)]["iterations"] for d in ds], float)
            slope = stats.linregress(np.array(ds, float), N).slope
            b1t, bs = 1 / s[0], sum(1 / x for x in s)
            desv = 0.0 if b1t <= slope <= bs else ((b1t - slope) / b1t if slope < b1t else (slope - bs) / bs)
            if abs(desv) > 0.10:
                b1 = False
            erros = [d for d in ds if not G[alg][str(d)]["correto"]]
            if erros:
                b2 = False
            hn = {d: G[alg][str(d)]["H"] / G[alg][str(d)]["iterations"] for d in ds}
            k50 = hn[50] / hn[18]
            if not k50 > LIM_KAPPA:
                b3 = False
            out[alg] = {"slope": slope, "b1": b1t, "bsoma": bs, "desvio": desv, "incorretos": erros,
                        "kappa_50_18": k50, "N18": G[alg]["18"]["iterations"], "N50": G[alg]["50"]["iterations"]}
        V["E2b"] = {"b1_inclinacao_na_faixa": b1, "b2_correto_em_todos_os_d": b2,
                    "b3_custo_por_termo_continua_crescendo": b3, "por_alg": out}
        mac.update({"EGkappaMin": FMT(min(o["kappa_50_18"] for o in out.values()), 2),
                    "EGkappaMax": FMT(max(o["kappa_50_18"] for o in out.values()), 2),
                    "EGdesvioMax": FMT(max(abs(o["desvio"]) for o in out.values()) * 100, 1)})
    # ---- E3
    if "E3" in M:
        E3 = M["E3"]
        vazio = E3["vazio"]["Ir"]
        qa = json.load(open(repo / "results/complementar/qp4_analise.json"))
        out = {}
        for chave, medidas in E3["medidas"].items():
            origem, alg = chave.split("/")
            ds = [str(d) for d in range(1, 19)]
            if any(medidas[d] is None or medidas[d]["Ir"] is None for d in ds):
                out[chave] = {"erro": "sem medida"}
                continue
            ir = np.array([medidas[d]["Ir"] - vazio for d in ds], float)
            N = np.array([medidas[d]["iterations"] for d in ds], float)
            var = (ir.max() - ir.min()) / ir.min()
            kap = (ir[17] / N[17]) / (ir[4] / N[4])
            classeN = selecionar(N)
            est = ESTATICA[origem]
            if alg == "nilakantha":
                est = "\\Theta(10^{d/3})"
            if est == "\\Theta(1)":
                ok = var <= 0.05
            elif est == "\\Theta(d)":
                ok = classeN == "linear" and var > 0.05 and kap <= LIM_KAPPA
            else:
                ok = classeN == "exponencial" and kap <= LIM_KAPPA
            ok_gcov = qa[chave]["concorda"]
            out[chave] = {"cod": COD[(origem, alg)], "var_Ir": var, "kappa_Ir": kap, "classeN": classeN,
                          "concorda_Ir": bool(ok), "concorda_H": bool(ok_gcov), "igual": bool(ok) == bool(ok_gcov),
                          "Ir18": float(ir[17]), "Ir_por_iter_18": float(ir[17] / N[17])}
        validos = {k: v for k, v in out.items() if "erro" not in v}
        V["E3"] = {"Ir_vazio": vazio, "n": len(validos), "n_concorda_Ir": sum(v["concorda_Ir"] for v in validos.values()),
                   "n_veredito_igual": sum(v["igual"] for v in validos.values()),
                   "divergentes": [k for k, v in validos.items() if not v["igual"]], "por_impl": out}
        # ANÁLISE EXPLORATÓRIA (não prevista no protocolo): custo marginal por iteração,
        # inclinação de Ir_liq em N em d = 1..9 e d = 10..18. Separa o custo fixo (conversão, escala)
        # do custo por termo, que a razão Ir_liq/N do critério pré-fixado mistura.
        marg = {}
        for chave, medidas in E3["medidas"].items():
            if chave not in validos or validos[chave]["classeN"] == "constante":
                continue
            ir = np.array([medidas[str(d)]["Ir"] - vazio for d in range(1, 19)], float)
            N = np.array([medidas[str(d)]["iterations"] for d in range(1, 19)], float)
            if len(set(N[:9])) < 3 or len(set(N[9:])) < 3:
                continue
            a, b = np.polyfit(N[:9], ir[:9], 1)[0], np.polyfit(N[9:], ir[9:], 1)[0]
            marg[chave] = {"inclinacao_d1_9": float(a), "inclinacao_d10_18": float(b), "razao": float(b / a)}
        V["E3"]["exploratorio_marginal"] = marg
        gk = [v["razao"] for k, v in marg.items() if k.startswith("grok/")]
        ot = [v["razao"] for k, v in marg.items() if not k.startswith("grok/") and k != "gemini/nilakantha"]
        mac.update({"EOmargGrokMin": FMT(min(gk), 2), "EOmargGrokMax": FMT(max(gk), 2),
                    "EOmargOutrosMax": FMT(max(ot), 2)})
        mac["EOkappaGrokMax"] = FMT(max(v["kappa_Ir"] for k, v in validos.items()
                                        if k.startswith("grok/") and k != "grok/nilakantha"), 2)
        mac.update({"EOn": len(validos), "EOconcIr": V["E3"]["n_concorda_Ir"], "EOigual": V["E3"]["n_veredito_igual"],
                    "EOvarMax": FMT(max(v["var_Ir"] for k, v in validos.items() if v["classeN"] == "constante" and
                                        k.split("/")[0] in ("chatgpt", "claude")) * 100, 1)})
    return V, mac



# ------------------------------------------------------------------ tabelas LaTeX do apêndice
def tabelas_tex(M, V):
    """Tabelas E1, E2 e E3 para o apêndice do artigo."""
    sim = lambda b: "sim" if b else "\\textbf{não}"
    out = []
    # E1
    e1 = V["E1"]
    lin = []
    for alg in GROK_ARCTAN:
        cod = COD[("grok", alg)]
        lin.append(f"{cod} & {FMT(e1['kappa_original'][alg], 2)} & {FMT(e1['kappa_fixl']['FIXL3/' + alg], 2)} & "
                   f"{FMT(e1['kappa_fixl']['FIXL6/' + alg], 2)} & {FMT(e1['HN18']['FIXL3/' + alg], 1)} & "
                   f"{FMT(e1['HN18']['FIXL6/' + alg], 1)}\\\\")
    out.append(r"""\begin{table}[htbp]
\centering
\caption{Intervenção no Grok (E1): razão $(H/N)_{d=18}/(H/N)_{d=5}$ no original e com $n=3$ e $n=6$ limbs fixos, e $H/N$ em $d=18$. Valor e iterações idênticos ao original em todos os casos.}
\label{tab:e1}
\small
\begin{tabular}{@{}l r r r r r@{}}
\toprule
Cód. & Original & $n=3$ & $n=6$ & $H/N$ ($n=3$) & $H/N$ ($n=6$)\\
\midrule
""" + "\n".join(lin) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
    # E2a
    e2 = V["E2a"]["por_impl"]
    lin = []
    for alg in IMPLS["claude"]:
        o = e2[alg]
        lin.append(f"{COD[('claude', alg)]} & {o['N_A18']} & {o['N_B18']} & {o['dmax_A']} & {FMT(o['dsup_A'], 1)}\\\\")
    out.append(r"""\begin{table}[htbp]
\centering
\caption{Claude além de $d=18$ (E2a). $N$: iterações informadas com a escala interna original (45 casas) e ampliada (90 casas); $N$ não muda com $d$ em nenhuma das duas. $d_{\max}$: maior $d$ correto (escala de 45 casas, $d\le44$). $N\delta$: casas que os $N$ termos servem, pela teoria.}
\label{tab:e2a}
\small
\begin{tabular}{@{}l r r r r@{}}
\toprule
Cód. & $N$ (45) & $N$ (90) & $d_{\max}$ (45) & $N\delta$ (45)\\
\midrule
""" + "\n".join(lin) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
    # E2b
    e2b = V["E2b"]["por_alg"]
    lin = []
    for alg in GROK_ARCTAN:
        o = e2b[alg]
        lin.append(f"{COD[('grok', alg)]} & {FMT(o['slope'], 2)} & {FMT(o['b1'], 2)}--{FMT(o['bsoma'], 2)} & "
                   f"{o['N18']} $\\to$ {o['N50']} & {FMT(o['kappa_50_18'], 2)}\\\\")
    out.append(r"""\begin{table}[htbp]
\centering
\caption{Grok além de $d=18$ (E2b), $d=1..50$, saída correta em todos os $d$. $\hat b$: inclinação de $N$ em $d$ e faixa teórica; $N$ em $d=18\to50$; razão $(H/N)_{d=50}/(H/N)_{d=18}$.}
\label{tab:e2b}
\small
\begin{tabular}{@{}l r r r r@{}}
\toprule
Cód. & $\hat b$ & Teoria & $N$ & $(H/N)$ 50/18\\
\midrule
""" + "\n".join(lin) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
    # E3
    e3 = V["E3"]["por_impl"]
    marg = V["E3"].get("exploratorio_marginal", {})
    lin = []
    for origem in ("chatgpt", "claude", "gemini", "grok"):
        for alg in IMPLS[origem]:
            k = f"{origem}/{alg}"
            if k not in e3 or "erro" in e3[k]:
                continue
            o = e3[k]
            mg = FMT(marg[k]["razao"], 2) if k in marg else "---"
            lin.append(f"{ORIG[origem]} & {o['cod']} & {FMT(o['var_Ir'] * 100, 1)} & {FMT(o['kappa_Ir'], 2)} & "
                       f"{sim(o['concorda_H'])} & {sim(o['concorda_Ir'])} & {mg}\\\\")
        lin.append("\\midrule")
    lin = lin[:-1]
    out.append(r"""\begin{table}[htbp]
\centering
\caption{Instruções com \texttt{-O2} (E3). $\Delta Ir$: variação de $Ir_{liq}$ entre $d=1$ e $d=18$ (\%). $\kappa$: razão $(Ir_{liq}/N)_{d=18}/(Ir_{liq}/N)_{d=5}$. \emph{Concorda ($H$)}: veredito com \texttt{gcov} em \texttt{-O0}; \emph{Concorda ($Ir$)}: veredito com instruções em \texttt{-O2}, pelo critério fixado antes da medição. \emph{Marg.}: razão entre o custo marginal por iteração em $d=10..18$ e em $d=1..9$ (exploratório, fora do protocolo). ChatGPT/EU aborta e não tem medida.}
\label{tab:e3}
\scriptsize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}l l r r c c r@{}}
\toprule
Origem & Cód. & $\Delta Ir$ & $\kappa$ & Concorda ($H$) & Concorda ($Ir$) & Marg.\\
\midrule
""" + "\n".join(lin) + r"""
\bottomrule
\end{tabular}
\end{table}
""")
    return "% Gerado por tools/qp4_extensoes.py\n" + "\n".join(out)

# ------------------------------------------------------------------ principal
if __name__ == "__main__":
    hash_crit = hashlib.sha256(CRITERIOS.read_bytes()).hexdigest()
    if REANALISAR:
        M = json.load(open(SAIDA))["medidas"]
    else:
        M = json.load(open(SAIDA))["medidas"] if SAIDA.exists() and set(SO) != {"E1", "E2", "E3"} else {}
        if "E1" in SO:
            M["E1"] = medir_e1()
        if "E2" in SO:
            M["E2a"] = medir_e2a()
            M["E2b"] = medir_e2b()
        if "E3" in SO:
            M["E3"] = medir_e3()
    V, mac = analisar(M)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({"criterios_sha256": hash_crit, "criterios": "protocolo/qp4_extensoes_criterios.md",
                                 "medidas": M, "vereditos": V, "macros": mac}, indent=1, default=float))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("por_impl", "por_alg")} for k, v in V.items()},
                     indent=1, default=float))
    if art is not None:
        (art / "tabelas/benchmark").mkdir(parents=True, exist_ok=True)
        (art / "tabelas/benchmark/qp4_ext_macros.tex").write_text(
            "% Gerado por tools/qp4_extensoes.py a partir de results/complementar/qp4_extensoes.json\n" +
            "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in mac.items()))
        (art / "tabelas/benchmark/qp4_ext_tabelas.tex").write_text(tabelas_tex(M, V))
        print("macros e tabelas escritas em", art)
