#!/usr/bin/env python3
"""QP4 -- análise: seleção de modelo (BIC), comparação com a teoria e validade da constância.

Uso: python tools/qp4_analise.py . [DIR_ARTIGO]
Lê results/complementar/qp4_gcov.json (gerado por tools/qp4_medicao_independente.py) e
escreve results/complementar/qp4_analise.json. Com DIR_ARTIGO, escreve também
tabelas/benchmark/qp4_validacao.tex, tabelas/benchmark/qp4_macros.tex e
figuras/benchmark/qp4_validacao.{pdf,png}.
"""
import json, math, sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy import stats

repo = Path(sys.argv[1]).resolve()
art = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
D = np.arange(1, 19, dtype=float)
FMT = lambda x, n=2: f"{x:.{n}f}".replace(".", "{,}")

COD = {("chatgpt","machin7"):"E7",("chatgpt","gauss"):"GA",("chatgpt","machin"):"M1",
       ("chatgpt","atan23"):"A23",("claude","chudnovsky"):"CH",("claude","ramanujan"):"RA",
       ("claude","takano"):"TA",("claude","machin"):"M2",("claude","euler"):"EU",
       ("gemini","machin"):"M2",("gemini","euler"):"EU",("gemini","newton"):"NE",
       ("gemini","nilakantha"):"NI",("gemini","ramanujan"):"RA",("grok","nilakantha"):"NI",
       ("grok","machin"):"M2",("grok","gauss"):"GA",("grok","hutton"):"HU",("grok","twinarctan"):"A23"}
ORIG = {"chatgpt":"ChatGPT","claude":"Claude","gemini":"Gemini","grok":"Grok"}
ORDEM = ["chatgpt","claude","gemini","grok"]
dl = lambda q: 2*math.log10(q)                       # dígitos por termo de arctan(1/q)
SERIES = {"A23":[dl(2),dl(3)],"E7":[dl(7),dl(79/3)],"GA":[dl(18),dl(57),dl(239)],
          "HU":[dl(3),dl(7)],"M1":[dl(5),dl(239)],"M2":[dl(5),dl(239)],
          "TA":[dl(49),dl(57),dl(239),dl(110443)],"CH":[14.18],"RA":[7.98],
          "EU":[math.log10(2)],"NE":[math.log10(4)]}        # razões 1/2 e 1/4
ESTATICA = {"chatgpt":"\\Theta(1)","claude":"\\Theta(1)","gemini":"\\Theta(d)","grok":"\\Theta(d)"}
LIM_KAPPA = 1.10    # crescimento de H/N entre d=5 e d=18 considerado "custo por termo crescente"

def selecionar(y):
    """BIC com resíduos relativos entre constante, linear e exponencial (parcimônia: dBIC<=2)."""
    y = np.asarray(y, float); n = len(y); w = 1/y; r = {}
    a = np.sum(w*w*y)/np.sum(w*w); r["constante"] = (float(np.sum((w*(a-y))**2)), 1)
    X = np.c_[np.ones(n), D]; b = np.linalg.lstsq(X*w[:, None], y*w, rcond=None)[0]
    r["linear"] = (float(np.sum((w*(X@b-y))**2)), 2)
    c0 = (math.log10(y[-1])-math.log10(y[0]))/17
    s = least_squares(lambda p: w*(p[0]*10**(p[1]*D)-y), [y[0]/10**c0, c0], method="lm", max_nfev=20000)
    r["exponencial"] = (float(np.sum(s.fun**2)), 2)
    bic = {k: n*math.log(max(v[0]/n, 1e-30))+v[1]*math.log(n) for k, v in r.items()}
    best = min(bic.values())
    return next(k for k in ["constante","linear","exponencial"] if bic[k] <= best+2)

def regra_antiga(N):
    N = np.asarray(N, float)
    if np.all(N == N[0]): return "constante"
    if np.all(N[1:] == N[1]): return "constante"      # "saturada" do artigo
    sl = np.polyfit(D, np.log10(N), 1)[0]
    return "exponencial" if 0.30 <= sl <= 0.37 else "linear"

def ic(y, log=False):
    yy = np.log10(y) if log else np.asarray(y, float)
    res = stats.linregress(D, yy); t = stats.t.ppf(0.975, len(D)-2)
    return res.slope, res.slope-t*res.stderr, res.slope+t*res.stderr

G = json.load(open(repo/"results/complementar/qp4_gcov.json"))["medidas"]
R = {}
for chave, v in G.items():
    origem, alg = chave.split("/")
    if v["1"] is None: continue
    N = [v[str(d)]["iterations_informadas"] for d in range(1, 19)]
    H = [v[str(d)]["H"] for d in range(1, 19)]
    L = [v[str(d)]["L"] for d in range(1, 19)]
    cod = COD[(origem, alg)]
    kap = [h/n for h, n in zip(H, N)]
    r = dict(origem=origem, alg=alg, cod=cod, N=N, H=H, L=L, kappa=kap,
             classeN=selecionar(N), classeN_antiga=regra_antiga(N),
             varH=(max(H)-min(H))/min(H), varL=(max(L)-min(L))/min(L),
             kappa_cresc=kap[-1]/kap[4])
    if cod in SERIES:
        s = SERIES[cod]; r.update(b1=1/s[0], bsoma=sum(1/x for x in s), dsup=N[-1]*s[0])
    if r["classeN"] == "linear": r["slope"] = ic(N)
    if r["classeN"] == "exponencial": r["expc"] = ic(N, log=True)
    # concordância entre a classe estática e o custo medido de forma independente (H)
    est = ESTATICA.get(origem)
    if alg == "nilakantha": est = "\\Theta(10^{d/3})"
    if est == "\\Theta(1)":
        ok = r["varH"] == 0
    elif est == "\\Theta(d)":
        ok = r["classeN"] == "linear" and r["varH"] > 0 and r["kappa_cresc"] <= LIM_KAPPA
    else:
        ok = r["classeN"] == "exponencial" and r["kappa_cresc"] <= LIM_KAPPA
    r["estatica"] = est; r["concorda"] = bool(ok)
    if not ok:
        r["motivo"] = ("custo fixo domina" if r["varH"] == 0 else
                       "N satura" if r["classeN"] == "constante" else "custo por termo cresce")
    R[chave] = r

# --- métricas de síntese ---
validas = [r for r in R.values() if r["cod"] != "EU" or r["origem"] != "chatgpt"]
n_val = len(validas)
conc = sum(r["concorda"] for r in validas)
conc_regra = sum(r["classeN"] == r["classeN_antiga"] for r in validas)
const = [r for r in validas if r["classeN"] == "constante" and r["origem"] in ("claude",)]
dsup = {r["cod"]+r["origem"][:2]: r["dsup"] for r in const}
kg = [r["kappa_cresc"] for r in validas if r["origem"] == "grok"]
kn = [r["kappa_cresc"] for r in validas if r["origem"] != "grok" and r["varH"] > 0]
slopes = {k: r for k, r in R.items() if "slope" in r}
dev = []
for k, r in slopes.items():
    b = r["slope"][0]
    d = (b - r["b1"])/r["b1"] if b < r["b1"] else (b - r["bsoma"])/r["bsoma"] if b > r["bsoma"] else 0.0
    r["desvio"] = d; dev.append(abs(d))
niG = R["gemini/nilakantha"]
Path(repo/"results/complementar/qp4_analise.json").write_text(json.dumps(R, indent=1))

print(f"classe de N por BIC = regra antiga em {conc_regra}/{n_val}; concordância estática x custo medido {conc}/{n_val}")
for k, r in R.items():
    print(f"{k:20s} N:{r['classeN']:11s} varH={r['varH']:.3f} kappa18/5={r['kappa_cresc']:.2f} conc={r['concorda']} {r.get('motivo','')}"
          + (f" b={r['slope'][0]:.3f} teo[{r['b1']:.3f},{r['bsoma']:.3f}] desv={r['desvio']*100:.1f}%" if "slope" in r else "")
          + (f" c={r['expc'][0]:.4f}[{r['expc'][1]:.4f},{r['expc'][2]:.4f}]" if "expc" in r else "")
          + (f" dsup={r['dsup']:.1f}" if r['classeN']=='constante' and 'dsup' in r else ""))
print("dsup Claude:", {k: round(v,1) for k, v in dsup.items()})
print("kappa Grok:", [round(x,2) for x in kg], " kappa outros:", [round(x,2) for x in kn])
print("max desvio slope:", max(dev))

if art is None: sys.exit()

# ---------------- macros ----------------
(art/"tabelas/benchmark").mkdir(parents=True, exist_ok=True)
cl = [r for r in validas if r["origem"] == "claude"]
mac = {
 "QPnValidas": n_val, "QPconcRegra": conc_regra, "QPconc": conc, "QPdiscordantes": n_val-conc,
 "QPdsupMin": FMT(min(r["dsup"] for r in cl), 0), "QPdsupMax": FMT(max(r["dsup"] for r in cl), 0),
 "QPmargemMin": FMT(min(r["dsup"] for r in cl)/18, 1), "QPmargemMax": FMT(max(r["dsup"] for r in cl)/18, 1),
 "QPkappaGrokMin": FMT(min(kg), 2), "QPkappaGrokMax": FMT(max(kg), 2),
 "QPkappaGrokNMax": FMT(max(r["kappa_cresc"] for r in validas if r["origem"]=="grok" and r["alg"]!="nilakantha"), 2),
 "QPkappaOutrosMax": FMT(max(kn), 2),
 "QPdesvioMax": FMT(max(dev)*100, 1),
 "QPniC": FMT(niG["expc"][0], 4), "QPniCLo": FMT(niG["expc"][1], 4), "QPniCHi": FMT(niG["expc"][2], 4),
 "QPniH": FMT(niG["H"][-1]/niG["N"][-1], 1),
 "QPvarLChatgptMax": FMT(max(r["varL"] for r in validas if r["origem"]=="chatgpt")*100, 1),
 "QPvarLClaudeMax": FMT(max(r["varL"] for r in validas if r["origem"]=="claude")*100, 2),
 "QPgrokNI": FMT(R["grok/nilakantha"]["N"][-1], 0),
}
(art/"tabelas/benchmark/qp4_macros.tex").write_text(
    "% Gerado por tools/qp4_analise.py a partir de results/complementar/qp4_gcov.json\n" +
    "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in mac.items()))

# ---------------- tabela ----------------
linhas = []
for o in ORDEM:
    for r in [x for x in validas if x["origem"] == o]:
        if r["classeN"] == "constante" and r["alg"] != "nilakantha":
            teo = f"$N\\delta\\approx{FMT(r['dsup'],0)}$ casas" if "dsup" in r else "---"
            if r["origem"] == "chatgpt": teo = "---"
        elif "slope" in r:
            ref = FMT(r['b1'],2) if abs(r['bsoma']-r['b1']) < 1e-9 else f"{FMT(r['b1'],2)}--{FMT(r['bsoma'],2)}"
            teo = f"$\\hat b={FMT(r['slope'][0],2)}$; teoria ${ref}$"
        elif "expc" in r:
            teo = f"$\\hat c={FMT(r['expc'][0],4)}$; teoria $0{{,}}3333$"
        else:
            teo = f"$N\\approx{FMT(r['N'][-1],0)}\\ll 7{{,}}9\\!\\times\\!10^{{6}}$"
        kk = r["kappa"]; kap = f"{FMT(kk[0],1)} $\\to$ {FMT(kk[-1],1)}"
        cls = {"constante":"constante","linear":"linear","exponencial":"exponencial"}[r["classeN"]]
        if r["alg"] == "nilakantha" and r["origem"] == "grok": cls = "saturada"
        conc_txt = "sim" if r["concorda"] else "\\textbf{não}: " + r["motivo"]
        linhas.append(f"{ORIG[r['origem']]} & {r['cod']} & ${r['estatica']}$ & {cls} & {kap} & {conc_txt} & {teo}\\\\")
    linhas.append("\\midrule")
linhas = linhas[:-1]
tab = r"""\begin{table}[!htbp]
\centering
\caption{Validação independente do custo (QP4). \emph{Estática}: classe do núcleo literal. \emph{Classe de $N$}: seleção de modelo por BIC sobre o contador informado. $H/N$: maior contagem de execução de uma linha (\texttt{gcov}) por iteração informada, em $d=1\to18$. \emph{Concorda}: a classe estática coincide com o custo medido, sem usar o contador. \emph{Teoria}: $N\delta$ é o $d$ máximo que $N$ termos fixos poderiam servir; $\hat b$ é a inclinação de $N$ em $d$ (termos por casa) frente ao intervalo teórico $[1/\delta_{\min},\sum 1/\delta_i]$; $\hat c$ é a taxa de $\log_{10}N$ por casa.}
\label{tab:qp4}
\scriptsize
\setlength{\tabcolsep}{2.5pt}
\renewcommand{\arraystretch}{1.1}
\begin{tabularx}{\linewidth}{@{}l l c l r >{\raggedright\arraybackslash}p{2.9cm} >{\raggedright\arraybackslash}X@{}}
\toprule
Origem & Cód. & Estática & Classe de $N$ & $H/N$ & Concorda & Teoria\\
\midrule
""" + "\n".join(linhas) + r"""
\bottomrule
\end{tabularx}
\end{table}
"""
(art/"tabelas/benchmark/qp4_validacao.tex").write_text(tab)

# ---------------- figura ----------------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
COR = {"chatgpt":"#a4303f","claude":"#2e7d5b","gemini":"#1f5f8b","grok":"#cc7014"}
fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.6))
rot = {}
for r in validas:
    if r["origem"] in ("chatgpt", "claude"): continue          # H constante: sem curva a mostrar
    k = np.array(r["kappa"]); ax[0].plot(D, k/k[4], color=COR[r["origem"]], lw=1.6 if r["origem"]=="grok" else 1.0,
        alpha=.9, label=None)
    rot.setdefault((r["origem"], round((k/k[4])[-1], 2)), []).append(r["cod"])
for (o, y), cods in rot.items():
    ax[0].text(18.2, y, ",".join(cods), color=COR[o], fontsize=6.5, va="center")
ax[0].axhline(1, color="#888", lw=.7, ls="--"); ax[0].set_xlim(1, 20.4); ax[0].set_xticks([1, 5, 10, 15, 18])
ax[0].set_xlabel("casas decimais solicitadas ($d$)"); ax[0].set_ylabel("custo por termo $(H/N)$ relativo a $d=5$")
ax[0].set_title("(a) custo por termo", fontsize=9)
for o in ORDEM[2:]:
    ax[0].plot([], [], color=COR[o], label=ORIG[o])
ax[0].legend(frameon=False, fontsize=7, loc="upper left")
ys = []; rot = []
for r in validas:
    if "slope" in r: ys.append(r)
ys = sorted(ys, key=lambda r: (ORDEM.index(r["origem"]), r["b1"]))
for i, r in enumerate(ys):
    ax[1].plot([r["b1"], r["bsoma"]], [i, i], color="#bbbbbb", lw=5, solid_capstyle="round", zorder=1)
    ax[1].plot([r["b1"], r["bsoma"]], [i, i], "|", color="#555555", ms=9, zorder=1)
    ax[1].plot([r["slope"][1], r["slope"][2]], [i, i], color=COR[r["origem"]], lw=1.2, zorder=2)
    ax[1].plot(r["slope"][0], i, "o", color=COR[r["origem"]], ms=4.5, zorder=3)
ax[1].set_yticks(range(len(ys))); ax[1].set_yticklabels([f"{ORIG[r['origem']]} {r['cod']}" for r in ys], fontsize=7)
ax[1].set_xscale("log"); ax[1].set_xlabel("termos por casa decimal adicional ($\\hat b$)")
ax[1].set_title("(b) inclinação de $N$ vs. faixa teórica (cinza)", fontsize=9)
for a in ax:
    for s in ("top", "right"): a.spines[s].set_visible(False)
fig.tight_layout(); (art/"figuras/benchmark").mkdir(parents=True, exist_ok=True)
fig.savefig(art/"figuras/benchmark/qp4_validacao.pdf"); fig.savefig(art/"figuras/benchmark/qp4_validacao.png", dpi=200)
print("artefatos escritos em", art)
