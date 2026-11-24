#!/usr/bin/env python3
"""Definições compartilhadas pelas ferramentas da QP4 (códigos de identidade, séries, BIC).

Importado por tools/qp4_analise.py e tools/qp4_extensoes.py; não é executado sozinho.
"""
import math
import numpy as np
from scipy.optimize import least_squares

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

