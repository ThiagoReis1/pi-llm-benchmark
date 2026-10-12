#!/usr/bin/env python3
"""Gera figuras editoriais a partir das recomendações e do benchmark arquivado."""
from __future__ import annotations

import json
import re
import statistics
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
PRESENTATION = RESULTS / "presentation"
FIGURES = PRESENTATION / "figures"
SOURCE_SHORT = {"chatgpt": "CG", "claude": "CL", "gemini": "GM", "grok": "GX"}
SOURCE_NAMES = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "grok": "Grok"}


def _load(name: str):
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _group_outcome(rows: list[dict]) -> str:
    """Classifica uma configuração única pelas repetições preservadas."""
    if not rows:
        return "missing"
    values = [r.get("correct") is True for r in rows if r.get("status") == "ok" and "correct" in r]
    if not values:
        return "no_json"
    if len(set(values)) > 1:
        return "inconsistent"
    return "correct" if values[0] else "incorrect"


def _is_compile_failure(row: dict) -> bool:
    text = " ".join(str(row.get(k, "")) for k in ("status", "failure_class", "error_type", "diagnosis")).lower()
    return "compile" in text or "compila" in text


def _groups(records: list[dict]) -> tuple[dict, set[str]]:
    failed = {str(r.get("llm_id")) for r in records if _is_compile_failure(r)}
    groups = defaultdict(list)
    for row in records:
        if row.get("case_type") == "decimal" and str(row.get("llm_id")) not in failed:
            groups[(str(row.get("llm_id")), str(row.get("algorithm")), int(row.get("digits")))].append(row)
    return groups, failed


def _style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.edgecolor": "#38434d",
        "axes.linewidth": 0.75,
        "text.color": "#17212b",
        "axes.labelcolor": "#17212b",
        "xtick.color": "#26323d",
        "ytick.color": "#26323d",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
    })


def _save_figure(fig, stem: str, dpi: int = 320) -> None:
    """Salva PDF vetorial como saída principal e PNG apenas para inspeção rápida."""
    fig.savefig(FIGURES / f"{stem}.pdf", format="pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(FIGURES / f"{stem}.png", format="png", dpi=dpi, bbox_inches="tight", facecolor="white")


def _algorithm_taxonomy() -> None:
    """Renderiza a taxonomia como diagrama vetorial usando somente Matplotlib."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    output = FIGURES / "algorithm_taxonomy.png"
    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.03)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")

    nodes = {
        "root": (0.55, 2.85, 3.15, 0.8, "Métodos de séries\npara calcular π"),
        "atan": (5.9, 5.85, 3.3, 0.62, "Séries de arco-tangente"),
        "hyper": (5.35, 4.55, 4.0, 0.62, "Séries fatoriais /\nhipergeométricas"),
        "euler": (5.0, 3.15, 4.75, 0.62, "Variantes sob o rótulo\nEuler"),
        "asin": (5.9, 1.75, 3.3, 0.62, "Série de arco-seno"),
        "nil": (5.95, 0.45, 3.2, 0.62, "Série de Nilakantha"),
    }
    edge_targets = ["atan", "hyper", "euler", "asin", "nil"]
    for target in edge_targets:
        x, y, w, h, _ = nodes[target]
        rx, ry, rw, rh, _ = nodes["root"]
        start_xy = (rx + rw, ry + rh / 2)
        end_xy = (x, y + h / 2)
        ax.add_patch(FancyArrowPatch(start_xy, end_xy, arrowstyle="-|>",
                                     mutation_scale=16, linewidth=1.3,
                                     color="#4B5563", connectionstyle="arc3,rad=0.05"))
    for key, (x, y, w, h, label) in nodes.items():
        face = "#EEF3F8" if key == "root" else "#FFFFFF"
        edge = "#1769AA" if key == "root" else "#8B6FC7"
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.08",
                                    facecolor=face, edgecolor=edge, linewidth=1.2))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=10.5 if key == "root" else 9.6,
                fontweight="bold" if key == "root" else "normal", color="#26323D")
    _save_figure(fig, "algorithm_taxonomy", dpi=320)
    plt.close(fig)

def _series_metadata() -> dict[tuple[str, str], dict]:
    rows = _load("presentation/recommendation_claims.json")
    return {(row["source"], row["algorithm"]): row for row in rows}


def _recommendation_matrix() -> None:
    """Renderiza a ordem declarada em uma matriz compacta e acessível."""
    from matplotlib.patches import Rectangle

    recommendations = _load("presentation/recommendation_claims.json")
    sources = ["chatgpt", "claude", "gemini", "grok"]
    by_source = defaultdict(dict)
    for item in recommendations:
        by_source[item["source"]][int(item["rank"])] = item

    # Okabe--Ito: cores distinguíveis e não dependentes apenas de vermelho/verde.
    source_colors = {
        "chatgpt": "#0072B2",
        "claude": "#E69F00",
        "gemini": "#009E73",
        "grok": "#CC79A7",
    }
    source_names = {
        "chatgpt": "ChatGPT",
        "claude": "Claude",
        "gemini": "Gemini",
        "grok": "Grok",
    }
    type_lines = {
        "AT": "arco-tangente",
        "HG": "hipergeométrica",
        "FD": "fatorial /\nduplo-fatorial",
        "TG": "transformação de Euler\n(Gregory–Leibniz)",
        "AS": "potência do\narco-seno",
        "NAK": "alternada algébrica\n(Nilakantha)",
    }

    fig, ax = plt.subplots(figsize=(7.35, 3.95))
    fig.subplots_adjust(left=0.085, right=0.985, top=0.92, bottom=0.08)
    ax.set_xlim(-0.70, 4.0)
    ax.set_ylim(0.0, 6.0)
    ax.axis("off")

    # A legenda é textual: a cor reforça a origem, mas nunca é a única codificação.
    ax.text(-0.31, 5.62, "Prioridade", ha="center", va="center",
            fontsize=9.4, fontweight="bold", color="#172B3A")
    for col, source in enumerate(sources):
        x0 = col
        color = source_colors[source]
        ax.add_patch(Rectangle((x0 + 0.015, 5.24), 0.97, 0.08,
                               facecolor=color, edgecolor="none", clip_on=False))
        ax.text(x0 + 0.5, 5.62, source_names[source], ha="center", va="center",
                fontsize=10.2, fontweight="bold", color="#172B3A")

    # Linhas finas e fundo branco reduzem chartjunk e preservam a leitura em escala menor.
    for rank in range(1, 6):
        y = 4.95 - (rank - 1)
        ax.hlines(y + 0.45, -0.62, 4, color="#C8D0D8", linewidth=0.65)
        ax.add_patch(Rectangle((-0.62, y - 0.45), 0.62, 0.90,
                               facecolor="#F3F5F7", edgecolor="none"))
        ax.text(-0.31, y, f"{rank}º", ha="center", va="center",
                fontsize=10.2, fontweight="bold", color="#374151")
        for col, source in enumerate(sources):
            item = by_source[source][rank]
            ax.text(col + 0.5, y + 0.13, item["algorithm"], ha="center", va="center",
                    fontsize=9.1, fontweight="bold", color="#17324D",
                    family="DejaVu Sans Mono")
            ax.text(col + 0.5, y - 0.19, type_lines[item["series_code"]],
                    ha="center", va="center", fontsize=7.2, linespacing=0.93,
                    color="#4B5563")
    ax.hlines(0.45, -0.62, 4, color="#C8D0D8", linewidth=0.65)
    for boundary in range(1, 4):
        ax.vlines(boundary, 0.45, 5.32, color="#E3E8ED", linewidth=0.55)

    _save_figure(fig, "recommendation_order_by_source", dpi=360)
    plt.close(fig)


def _recommendation_table() -> None:
    """Gera a matriz de recomendações como tabela LaTeX copiável."""
    recommendations = _load("presentation/recommendation_claims.json")
    sources = ["chatgpt", "claude", "gemini", "grok"]
    source_names = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "grok": "Grok"}
    by_source = defaultdict(dict)
    for item in recommendations:
        by_source[item["source"]][int(item["rank"])] = item
    lines = [
        r"% Arquivo gerado automaticamente por generate_presentation.py; não editar manualmente.",
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Ordem de recomendação declarada por fonte.}",
        r"\label{tab:recommendation-order}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabularx}{\linewidth}{r *{4}{>{\centering\arraybackslash}X}}",
        r"\toprule",
        "Prioridade & " + " & ".join(source_names[source] for source in sources) + r"\\",
        r"\midrule",
    ]
    for rank in range(1, 6):
        cells = []
        for source in sources:
            item = by_source[source][rank]
            algorithm = _latex_text(str(item["algorithm"]))
            series = _latex_text(str(item["series_code"]))
            cells.append(rf"\shortstack{{\texttt{{{algorithm}}}\\[-1pt]\scriptsize {series}}}")
        lines.append(f"{rank}º & " + " & ".join(cells) + r"\\")
    lines.extend([
        r"\bottomrule",
        r"\end{tabularx}",
        r"\end{table}",
        r"\par\smallskip\footnotesize Códigos: AT = arco-tangente; HG = hipergeométrica; FD = razão fatorial/duplo-fatorial; TG = transformação de Euler; AS = arco-seno; NAK = Nilakantha.\normalsize",
        "",
    ])
    (PRESENTATION / "tables" / "recommendation_order_by_source.tex").write_text("\n".join(lines), encoding="utf-8")

def _precision_frontier(records: list[dict], groups: dict, failed: set[str]) -> dict:
    pairs = sorted({(p, a) for p, a, _ in groups}, key=lambda x: (x[1].lower(), x[0].lower()))
    summary = {}
    for source, algorithm in pairs:
        outcomes = [_group_outcome(groups.get((source, algorithm, d), [])) for d in range(1, 19)]
        frontier = 0
        for result in outcomes:
            if result == "correct":
                frontier += 1
            else:
                break
        first_failure = outcomes[frontier] if frontier < 18 else "none"
        summary[(source, algorithm)] = {"frontier": frontier, "first_failure": first_failure, "outcomes": outcomes}

    order = sorted(summary, key=lambda x: (x[1].lower(), x[0].lower()))
    type_rows = _series_metadata()
    labels = [f"{algorithm} [{type_rows[(source, algorithm)]['series_code']}]  ·  {SOURCE_SHORT.get(source, source[:2].upper())}"
              for source, algorithm in order]
    ys = np.arange(len(order))
    fig_h = max(7.2, 0.29 * len(order) + 1.6)
    fig, ax = plt.subplots(figsize=(7.0, fig_h))
    fig.subplots_adjust(left=0.36, right=0.985, top=0.87, bottom=0.23)
    fig.suptitle("Precisão validada por implementação", y=0.965, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.925,
             "Maior sequência inicial de casas corretamente arredondadas; cada precisão conta uma vez, não por repetição.",
             ha="center", va="center", fontsize=9, color="#52606d")

    success_color = "#21618c"
    incorrect_color = "#c66a16"
    nojson_color = "#8f3345"
    for y, key in zip(ys, order):
        source, algorithm = key
        item = summary[key]
        frontier = item["frontier"]
        failure = item["first_failure"]
        ax.plot([0, frontier], [y, y], color="#ccd4db", lw=2, solid_capstyle="round", zorder=1)
        if frontier == 18:
            ax.scatter([frontier], [y], s=48, marker="o", color=success_color, zorder=3)
            status = "18/18"
            color = success_color
        elif failure == "no_json":
            ax.scatter([max(0.16, frontier)], [y], s=52, marker="X", color=nojson_color, zorder=3)
            status = f"{frontier}/18"
            color = nojson_color
        else:
            ax.scatter([max(0.16, frontier)], [y], s=48, marker="D", color=incorrect_color, zorder=3)
            status = f"{frontier}/18"
            color = incorrect_color
        ax.text(18.28 if frontier == 18 else max(0.52, frontier + 0.28), y, status,
                ha="left", va="center", fontsize=7.3, color=color)

    ax.set_yticks(ys, labels, fontsize=7.7)
    ax.invert_yaxis()
    ax.set_xlim(0, 20.2)
    ax.set_xticks(range(0, 19, 2))
    ax.set_xlabel("Casas decimais consecutivas confirmadas (máximo = 18)")
    ax.grid(axis="x", color="#e1e6ea", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    from matplotlib.lines import Line2D
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=success_color, markeredgecolor=success_color,
               label="18/18 corretas", markersize=6),
        Line2D([0], [0], marker="D", color="none", markerfacecolor=incorrect_color, markeredgecolor=incorrect_color,
               label="resposta numérica incorreta", markersize=6),
        Line2D([0], [0], marker="X", color="none", markerfacecolor=nojson_color, markeredgecolor=nojson_color,
               label="sem JSON válido", markersize=6),
    ]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.66, 0.135),
               frameon=False, fontsize=7.2, ncol=3)
    fig.text(0.36, 0.105,
             "CG = ChatGPT; CL = Claude; GM = Gemini; GX = Grok",
             ha="left", va="center", fontsize=7.2, color="#38434d")
    fig.text(0.36, 0.078,
             "Tipo da série: AT arco-tangente; HG hipergeométrica; FD razão fatorial; "
             "TG transformação Euler/Gregory; AS arco-seno; NAK Nilakantha.",
             ha="left", va="center", fontsize=6.7, color="#38434d")
    _save_figure(fig, "validated_precision_by_implementation", dpi=320)
    plt.close(fig)
    return summary


def _nilakantha_case_study(records: list[dict], groups: dict, summary: dict) -> None:
    sources = ["gemini", "grok"]
    styles = {
        "gemini": {"color": "#21618c", "marker": "o", "linestyle": "-", "label": "Gemini: 18/18 casas corretas"},
        "grok": {"color": "#c66a16", "marker": "s", "linestyle": "--", "label": "Grok: 8/18 casas corretas"},
    }
    fig, ax = plt.subplots(figsize=(7.0, 4.55))
    fig.subplots_adjust(left=0.15, right=0.98, top=0.80, bottom=0.22)
    fig.suptitle("Nilakantha: precisão e custo da implementação", y=0.965, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.90,
             "Tipo: série alternada algébrica de Nilakantha (termo da ordem de k⁻³). A linha marca a fronteira Grok de 8 casas.",
             ha="center", va="center", fontsize=8.7, color="#52606d")
    for source in sources:
        xs, ys = [], []
        for d in range(1, 19):
            rows = groups.get((source, "nilakantha", d), [])
            times = [float(r["time_seconds"]) for r in rows
                     if r.get("status") == "ok" and isinstance(r.get("time_seconds"), (int, float))
                     and r["time_seconds"] > 0]
            if times:
                xs.append(d)
                ys.append(statistics.median(times) * 1000)
        ax.plot(xs, ys, **styles[source], linewidth=1.8, markersize=4.2)

    ax.axvline(8.5, color="#737f89", linewidth=0.9, linestyle=":")
    ax.set_yscale("log")
    ax.set_xlim(1, 18.5)
    ax.set_xticks([1, 3, 5, 7, 9, 11, 13, 15, 17, 18])
    ax.set_xlabel("Casas decimais solicitadas")
    ax.set_ylabel("Tempo mediano por execução (ms; escala log)")
    ax.grid(which="both", color="#e1e6ea", linewidth=0.65)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=8.2)
    gem_rows = groups.get(("gemini", "nilakantha", 18), [])
    grok_rows = groups.get(("grok", "nilakantha", 18), [])
    gem_iters = next((r.get("iterations") for r in gem_rows if r.get("iterations") is not None), None)
    grok_iters = next((r.get("iterations") for r in grok_rows if r.get("iterations") is not None), None)
    note = (f"Em d=18: Gemini informa {gem_iters:,} iterações e acerta; "
            f"Grok informa {grok_iters:,} e erra (3.141592653124563412, referência 3.141592653589793238).")
    fig.text(0.13, 0.075, note, ha="left", va="center", fontsize=7.7, color="#38434d")
    fig.text(0.13, 0.04,
             "Mediana de cinco repetições; o tempo inclui execução do processo, não compilação. Saída JSON válida pode conter valor incorreto.",
             ha="left", va="center", fontsize=7.2, color="#52606d")
    _save_figure(fig, "nilakantha_accuracy_runtime_case_study", dpi=320)
    plt.close(fig)


FORMULA_SPECS = {
    ("chatgpt", "machin7"): (r"\pi=20\arctan(1/7)+8\arctan(3/79)", "algorithm_machin7", True, "identidade válida"),
    ("chatgpt", "gauss"): (r"\pi=48\arctan(1/18)+32\arctan(1/57)-20\arctan(1/239)", "algorithm_gauss", True, "identidade válida"),
    ("chatgpt", "machin"): (r"4\pi=64\arctan(1/5)-16\arctan(1/239)", "algorithm_machin", False, "coeficientes do código implicam quatro vezes pi"),
    ("chatgpt", "atan23"): (r"\pi=4\left[\arctan(1/2)+\arctan(1/3)\right]", "algorithm_atan23", True, "identidade válida"),
    ("chatgpt", "euler"): (r"\pi=4\sum_{k=0}^{\infty}\frac{1}{2^{k+1}}\sum_{j=0}^{k}\frac{(-1)^j\binom{k}{j}}{2j+1}", "algorithm_euler", True, "Euler aplicada a Gregory--Leibniz"),
    ("claude", "chudnovsky"): (r"\pi=\frac{426880\sqrt{10005}}{\sum_{k=0}^{\infty}(-1)^k\frac{(6k)!(13591409+545140134k)}{(3k)!(k!)^3 640320^{3k}}}", "alg_chudnovsky", True, "identidade válida"),
    ("claude", "ramanujan"): (r"\pi=\frac{9801}{2\sqrt{2}\sum_{k=0}^{\infty}\frac{(4k)!(1103+26390k)}{(k!)^4 396^{4k}}}", "alg_ramanujan", True, "identidade válida"),
    ("claude", "takano"): (r"\pi=48\arctan(1/49)+128\arctan(1/57)-20\arctan(1/239)+48\arctan(1/110443)", "alg_takano", True, "identidade válida"),
    ("claude", "machin"): (r"\pi=16\arctan(1/5)-4\arctan(1/239)", "alg_machin", True, "identidade válida"),
    ("claude", "euler"): (r"\pi=2\sum_{k=0}^{\infty}\frac{k!}{(2k+1)!!}", "alg_euler", True, "série de Euler"),
    ("gemini", "machin"): (r"\pi=16\arctan(1/5)-4\arctan(1/239)", "run_machin", True, "identidade válida"),
    ("gemini", "euler"): (r"\pi=2\sum_{k=0}^{\infty}\frac{k!}{(2k+1)!!}", "run_euler", True, "série de Euler"),
    ("gemini", "newton"): (r"\pi=3\sum_{k=0}^{\infty}\frac{(2k)!}{16^k(k!)^2(2k+1)}", "run_newton", True, "série de arco-seno"),
    ("gemini", "nilakantha"): (r"\pi=3+4\sum_{k=1}^{\infty}\frac{(-1)^{k+1}}{2k(2k+1)(2k+2)}", "run_nilakantha", True, "série alternada de Nilakantha"),
    ("gemini", "ramanujan"): (r"\pi=\frac{9801}{2\sqrt{2}\sum_{k=0}^{\infty}\frac{(4k)!(1103+26390k)}{(k!)^4 396^{4k}}}", "run_ramanujan", True, "identidade válida"),
    ("grok", "nilakantha"): (r"\pi=3+4\sum_{k=1}^{\infty}\frac{(-1)^{k+1}}{2k(2k+1)(2k+2)}", "nilakantha", True, "série alternada de Nilakantha"),
    ("grok", "machin"): (r"\pi=16\arctan(1/5)-4\arctan(1/239)", "compute_pi → arctan_inv", True, "código aplica quatro vezes a forma reduzida"),
    ("grok", "gauss"): (r"\pi=4\left[12\arctan(1/18)+8\arctan(1/57)-5\arctan(1/239)\right]", "compute_pi → arctan_inv", True, "identidade válida"),
    ("grok", "hutton"): (r"\pi=4\left[2\arctan(1/3)+\arctan(1/7)\right]", "compute_pi → arctan_inv", True, "identidade válida"),
    ("grok", "twinarctan"): (r"\pi=4\left[\arctan(1/2)+\arctan(1/3)\right]", "compute_pi → arctan_inv", True, "identidade válida"),
}

def _series_evaluation(source: str, algorithm: str) -> str:
    """Retorna a soma finita realmente avaliada para d casas e g dígitos-guarda."""
    arctan = {
        ("chatgpt", "machin7"): r"20\left(\sum_{k=0}^{N_7(d,g)}\frac{(-1)^k}{(2k+1)7^{2k+1}}\right)+8\left(\sum_{k=0}^{N_{79}(d,g)}\frac{(-1)^k3^{2k+1}}{(2k+1)79^{2k+1}}\right)",
        ("chatgpt", "gauss"): r"48\sum_{k=0}^{N_{18}(d,g)}\frac{(-1)^k}{(2k+1)18^{2k+1}}+32\sum_{k=0}^{N_{57}(d,g)}\frac{(-1)^k}{(2k+1)57^{2k+1}}-20\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}",
        ("chatgpt", "machin"): r"64\sum_{k=0}^{N_5(d,g)}\frac{(-1)^k}{(2k+1)5^{2k+1}}-16\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}",
        ("chatgpt", "atan23"): r"4\sum_{k=0}^{N_2(d,g)}\frac{(-1)^k}{(2k+1)2^{2k+1}}+4\sum_{k=0}^{N_3(d,g)}\frac{(-1)^k}{(2k+1)3^{2k+1}}",
        ("claude", "takano"): r"48\sum_{k=0}^{N_{49}(d,g)}\frac{(-1)^k}{(2k+1)49^{2k+1}}+128\sum_{k=0}^{N_{57}(d,g)}\frac{(-1)^k}{(2k+1)57^{2k+1}}-20\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}+48\sum_{k=0}^{N_{110443}(d,g)}\frac{(-1)^k}{(2k+1)110443^{2k+1}}",
        ("claude", "machin"): r"16\sum_{k=0}^{N_5(d,g)}\frac{(-1)^k}{(2k+1)5^{2k+1}}-4\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}",
        ("gemini", "machin"): r"16\sum_{k=0}^{N_5(d,g)}\frac{(-1)^k}{(2k+1)5^{2k+1}}-4\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}",
        ("grok", "machin"): r"16\sum_{k=0}^{N_5(d,g)}\frac{(-1)^k}{(2k+1)5^{2k+1}}-4\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}",
        ("grok", "gauss"): r"4\left[12\sum_{k=0}^{N_{18}(d,g)}\frac{(-1)^k}{(2k+1)18^{2k+1}}+8\sum_{k=0}^{N_{57}(d,g)}\frac{(-1)^k}{(2k+1)57^{2k+1}}-5\sum_{k=0}^{N_{239}(d,g)}\frac{(-1)^k}{(2k+1)239^{2k+1}}\right]",
        ("grok", "hutton"): r"4\left[2\sum_{k=0}^{N_3(d,g)}\frac{(-1)^k}{(2k+1)3^{2k+1}}+\sum_{k=0}^{N_7(d,g)}\frac{(-1)^k}{(2k+1)7^{2k+1}}\right]",
        ("grok", "twinarctan"): r"4\left[\sum_{k=0}^{N_2(d,g)}\frac{(-1)^k}{(2k+1)2^{2k+1}}+\sum_{k=0}^{N_3(d,g)}\frac{(-1)^k}{(2k+1)3^{2k+1}}\right]",
    }
    if (source, algorithm) in arctan:
        return arctan[(source, algorithm)]
    finite = {
        ("chatgpt", "euler"): r"4\sum_{k=0}^{K(d,g)}\frac{1}{2^{k+1}}\sum_{j=0}^{k}\frac{(-1)^j\binom{k}{j}}{2j+1}",
        ("claude", "chudnovsky"): r"\frac{426880\sqrt{10005}}{\sum_{k=0}^{K(d,g)}(-1)^k\frac{(6k)!(13591409+545140134k)}{(3k)!(k!)^3 640320^{3k}}}",
        ("claude", "ramanujan"): r"\frac{9801}{2\sqrt{2}\sum_{k=0}^{K(d,g)}\frac{(4k)!(1103+26390k)}{(k!)^4 396^{4k}}}",
        ("claude", "euler"): r"2\sum_{k=0}^{K(d,g)}\frac{k!}{(2k+1)!!}",
        ("gemini", "euler"): r"2\sum_{k=0}^{K(d,g)}\frac{k!}{(2k+1)!!}",
        ("gemini", "newton"): r"3\sum_{k=0}^{K(d,g)}\frac{(2k)!}{16^k(k!)^2(2k+1)}",
        ("gemini", "nilakantha"): r"3+4\sum_{k=1}^{K(d,g)}\frac{(-1)^{k+1}}{2k(2k+1)(2k+2)}",
        ("gemini", "ramanujan"): r"\frac{9801}{2\sqrt{2}\sum_{k=0}^{K(d,g)}\frac{(4k)!(1103+26390k)}{(k!)^4 396^{4k}}}",
        ("grok", "nilakantha"): r"3+4\sum_{k=1}^{K(d,g)}\frac{(-1)^{k+1}}{2k(2k+1)(2k+2)}",
    }
    return finite[(source, algorithm)]

def _general_series_latex(series_latex: str) -> str:
    """Converte a representação de avaliação em sua forma analítica infinita."""
    return re.sub(r"N_(?:\{[^}]+\}|[0-9]+)\(d,g\)|K\(d,g\)", r"\\infty", series_latex)


def _formula_catalog() -> list[dict]:
    """Extrai os métodos e registra a identidade, o código e a expansão em série."""
    claims = _load("presentation/recommendation_claims.json")
    rows = []
    for source in ("chatgpt", "claude", "gemini", "grok"):
        source_path = ROOT / "submissions" / source / "attempt_01" / "submission.c"
        code = source_path.read_text(encoding="utf-8", errors="replace")
        for claim in sorted((x for x in claims if x["source"] == source), key=lambda x: int(x["rank"])):
            algorithm = claim["algorithm"]
            formula, function_name, identity_valid, audit_note = FORMULA_SPECS[(source, algorithm)]
            series_evaluation = _series_evaluation(source, algorithm)
            series_general = _general_series_latex(series_evaluation)
            # A fórmula só entra se o método está realmente presente no C correspondente.
            token = function_name.split(" → ")[0]
            detected = bool(re.search(r"\b" + re.escape(token) + r"\b", code))
            if not detected:
                raise RuntimeError(f"Função não localizada para {source}/{algorithm}: {token}")
            rows.append({"source": source, "algorithm": algorithm, "rank": int(claim["rank"]),
                         "function": function_name, "formula_latex": formula,
                         "series_evaluation_latex": series_evaluation,
                         "series_general_latex": series_general,
                         "identity_valid": identity_valid, "audit_note": audit_note,
                         "detected_in_source": detected})
    (PRESENTATION / "formula_catalog.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


def _latex_text(value: str) -> str:
    """Escapa texto comum para uso seguro dentro de uma célula LaTeX."""
    replacements = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_"}
    return "".join(replacements.get(char, char) for char in value)


FORMULA_FONT = r"\footnotesize"
TAKANO_SERIES_SCALE = "0.95"


def _single_line_formula_latex(source: str, algorithm: str, expression: str, *, series: bool = False) -> str:
    """Renderiza uma expressão indivisível, abaixo do algoritmo e sem ampliá-la."""
    # ``\mbox`` impede que TeX quebre a identidade ou o somatório dentro da
    # expressão. A fonte é fixa e moderada: fórmulas curtas não são ampliadas.
    # Somente o somatório excepcionalmente longo de Takano recebe redução fixa.
    math_box = rf"\mbox{{{FORMULA_FONT} $\displaystyle {expression}$}}"
    if source == "claude" and algorithm == "takano" and series:
        return rf"\scalebox{{{TAKANO_SERIES_SCALE}}}{{{math_box}}}"
    return math_box


def _formula_tables(rows: list[dict]) -> None:
    """Gera uma tabela LaTeX copiável para cada origem do catálogo de fórmulas."""
    tables = PRESENTATION / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    names = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "grok": "Grok"}
    for source, source_name in names.items():
        items = [row for row in rows if row["source"] == source]
        lines = [
            r"% Gerado por generate_scientific_figures.py: cada fórmula aparece abaixo do algoritmo.",
            r"% Matemática em \footnotesize, sem ampliação; somente o somatório de Takano usa escala 0.95.",
            r"\begingroup",
            r"\small",
            r"\setlength{\tabcolsep}{4pt}",
            r"\setlength{\LTcapwidth}{\linewidth}",
            r"\setlength{\LTpre}{\smallskipamount}",
            r"\setlength{\LTpost}{\smallskipamount}",
            r"\renewcommand{\arraystretch}{1.10}",
            r"\begin{longtable}{@{}>{\raggedleft\arraybackslash}p{1.8cm} p{\dimexpr\linewidth-1.8cm-2\tabcolsep\relax}@{}}",
            rf"\caption[Catálogo de fórmulas analíticas — {source_name}. As expansões de arco-tangente são exibidas explicitamente em forma de somatório.]{{\footnotesize\sffamily\bfseries Catálogo de fórmulas analíticas — {source_name}. As expansões de arco-tangente são exibidas explicitamente em forma de somatório.}}\label{{tab:formula-catalog-{source}}}\\",
            r"\toprule",
            r"Prioridade & Método e fórmula (a expressão fica abaixo do nome)\\",
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            r"Prioridade & Método e fórmula (a expressão fica abaixo do nome)\\",
            r"\midrule",
            r"\endhead",
            r"\midrule",
            r"\multicolumn{2}{r}{\footnotesize Continua na próxima página.}\\",
            r"\endfoot",
            r"\bottomrule",
            r"\endlastfoot",
        ]
        for item in items:
            algorithm = _latex_text(str(item["algorithm"]))
            formula = item["formula_latex"]
            series = item["series_general_latex"]
            formula_cell = _single_line_formula_latex(source, str(item["algorithm"]), formula)
            # Nome, identidade e expansão permanecem juntos na mesma página.
            # As fórmulas abrangem as duas colunas para manter a fonte moderada.
            formula_row = r"\multicolumn{2}{@{}>{\centering\arraybackslash}p{\linewidth}@{}}"
            lines.append(rf"{item['rank']} & \texttt{{{algorithm}}}" + r"\\*[2pt]")
            if r"\arctan" in formula:
                series_cell = _single_line_formula_latex(source, str(item["algorithm"]), series, series=True)
                lines.append(formula_row + "{" + formula_cell + "}" + r"\\*[3pt]")
                lines.append(formula_row + "{" + series_cell + "}" + r"\\[5pt]")
            else:
                lines.append(formula_row + "{" + formula_cell + "}" + r"\\[5pt]")
        lines.extend([r"\end{longtable}", r"\endgroup", ""])
        (tables / f"formula_catalog_{source}.tex").write_text("\n".join(lines), encoding="utf-8")

def _formula_figure() -> None:
    """Renderiza um catálogo vetorial legível, com uma página dedicada por origem."""
    rows = _formula_catalog()
    colors = {"chatgpt": "#0072B2", "claude": "#E69F00", "gemini": "#009E73", "grok": "#CC79A7"}
    names = {"chatgpt": "ChatGPT", "claude": "Claude", "gemini": "Gemini", "grok": "Grok"}
    source_pages = []

    def render_page(source: str):
        fig, ax = plt.subplots(figsize=(11.69, 8.27))
        ax.axis("off")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.add_patch(plt.Rectangle((0.045, 0.895), 0.91, 0.006, color=colors[source], transform=ax.transAxes, clip_on=False))
        ax.text(0.05, 0.965, f"{names[source]} — fórmulas analíticas", fontsize=18,
                color="#172B3A", va="top", fontweight="bold", transform=ax.transAxes)
        items = [r for r in rows if r["source"] == source]
        y = 0.88
        for item in items:
            ax.add_patch(plt.Rectangle((0.05, y - 0.125), 0.90, 0.145, facecolor="#f7f9fb",
                                       edgecolor="#d9e0e6", linewidth=0.7, transform=ax.transAxes))
            ax.text(0.065, y, f"{item['rank']}   {item['algorithm']}", fontsize=10.5, fontweight="bold",
                    color="#17324D", va="top", transform=ax.transAxes)
            ax.text(0.23, y - 0.003, rf"${item['formula_latex']}$", fontsize=8.2, color="#26323D",
                    va="top", transform=ax.transAxes)
            # Para métodos já definidos por uma série (Chudnovsky, Ramanujan,
            # Euler, Newton e Nilakantha), a identidade e a expansão geral são
            # a mesma expressão: não repetir a fórmula no cartão.
            if r"\arctan" in item["formula_latex"]:
                ax.text(0.23, y - 0.070, rf"${item['series_general_latex']}$", fontsize=6.6, color="#3f4d58",
                        va="top", transform=ax.transAxes)
            y -= 0.15
        return fig

    pdf_path = FIGURES / "formula_catalog.pdf"
    (FIGURES / "formula_catalog.png").unlink(missing_ok=True)
    with PdfPages(pdf_path) as pdf:
        for source in names:
            fig = render_page(source)
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
            fig.savefig(FIGURES / f"formula_catalog_{source}.png", dpi=320, bbox_inches="tight", facecolor="white")
            source_pages.append(fig)
            plt.close(fig)

def generate_scientific_figures(records: list[dict], individual: dict | None = None) -> dict:
    """Gera as figuras principais e retorna os metadados de validação."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    _style()
    formula_rows = _formula_catalog()
    _formula_tables(formula_rows)
    _recommendation_table()
    groups, failed = _groups(records)
    precision = _precision_frontier(records, groups, failed)
    _nilakantha_case_study(records, groups, precision)
    return {
        "figures": [
            "validated_precision_by_implementation.pdf",
            "nilakantha_accuracy_runtime_case_study.pdf",
        ],
        "formula_tables": [f"formula_catalog_{source}.tex" for source in ("chatgpt", "claude", "gemini", "grok")],
        "supporting_diagrams": [],
        "compiled_source_gate_failures": sorted(failed),
        "evaluated_implementations": len(precision),
        "implementations_correct_at_all_18_digits": sum(v["frontier"] == 18 for v in precision.values()),
        "precision_frontier_rule": "Número de níveis d=1,2,... corretamente arredondados antes da primeira falha; monotonicidade verificada na rodada.",
    }
