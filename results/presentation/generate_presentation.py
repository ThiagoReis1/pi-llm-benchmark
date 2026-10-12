#!/usr/bin/env python3
"""Gera tabelas LaTeX, figuras PNG e um índice resumido da rodada.

Os artefatos são derivados exclusivamente dos JSONs em ``results/``. O script
não altera os dados experimentais e pode ser executado novamente após cada rodada.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmark.aggregation import configuration_outcome, configuration_time_medians, group_configurations, is_compile_failure
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "presentation"
TABLES = OUTPUT / "tables"
FIGURES = OUTPUT / "figures"


def read_json(name: str):
    """Carrega um JSON de resultados usando UTF-8."""
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def tex(value) -> str:
    """Escapa texto simples para uso seguro em tabelas LaTeX."""
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#"}
    return "".join(replacements.get(char, char) for char in str(value))


def number(value, digits=3, fallback="---") -> str:
    """Formata um número ou retorna um marcador para valor ausente."""
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
        return fallback
    return f"{value:.{digits}f}"


def complexity_tex(value) -> str:
    """Formata Theta/O em matemática LaTeX e preserva o comentário heurístico."""
    text=str(value or "---")
    token=next((name for name in ("Theta(","O(") if text.startswith(name)),None)
    if token is None:
        return tex(text)
    depth=1
    end=len(token)
    for index in range(len(token),len(text)):
        if text[index]=="(": depth+=1
        elif text[index]==")":
            depth-=1
            if depth==0:
                end=index
                break
    expression=text[len(token):end].replace("*",r"\cdot ")
    operator=r"\Theta" if token.startswith("Theta") else "O"
    suffix=tex(text[end+1:].strip())
    return f"${operator}({expression})$"+(f" {suffix}" if suffix else "")


def median(values):
    """Calcula a mediana dos valores numéricos disponíveis."""
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return statistics.median(values) if values else None


def write_table(name: str, content: str) -> None:
    """Grava uma tabela LaTeX com quebra de linha final."""
    (TABLES / name).write_text(content.rstrip() + "\n", encoding="utf-8")


def load_data():
    """Carrega os resultados, rankings, análise individual e metadados."""
    results = read_json("results.json")
    return (
        results["records"],
        results.get("execution_summary", {}),
        read_json("algorithm_ranking.json").get("ranking", []),
        read_json("individual_code_analysis.json"),
        read_json("run_metadata.json"),
    )


def generate_tables(records, execution, algorithm_ranking, individual, metadata):
    """Gera tabelas prontas para inclusão com ``\\input`` no artigo."""
    TABLES.mkdir(parents=True, exist_ok=True)
    for old in TABLES.glob("*.tex"):
        old.unlink()
    failed_builds = {str(r.get("llm_id")) for r in records if is_compile_failure(r)}
    eligible_records = [r for r in records if str(r.get("llm_id")) not in failed_builds]
    decimal_groups = group_configurations(eligible_records, "decimal")
    invalid_groups = group_configurations(eligible_records, "invalid")

    config_rows = [
        ("Arquivos C de origem", len({r.get("llm_id") for r in records})),
        ("Unidade de análise", "método implementado + precisão"),
        ("Casas decimais", "1--18"),
        ("Repetições por configuração (apenas tempo)", metadata.get("repetitions", "---")),
        ("Resultados de correção", "uma vez por método implementado e precisão"),
        ("Tempo limite por processo", f"{metadata.get('timeout_seconds', '---')} s"),
        ("Limite de memória", f"{metadata.get('memory_mb', '---')} MB"),
        ("Execuções paralelas", metadata.get("workers", "---")),
        ("Compilador", metadata.get("compiler", "---")),
    ]
    config = [r"\begin{tabular}{lr}", r"\toprule", r"Parâmetro & Valor\\", r"\midrule"]
    config += [f"{tex(k)} & {tex(v)}" + r"\\" for k, v in config_rows]
    config += [r"\bottomrule", r"\end{tabular}"]
    write_table("experimental_configuration.tex", "\n".join(config))

    algorithm_rows = []
    for item in sorted(algorithm_ranking, key=lambda row: (str(row.get("algorithm", "")), str(row.get("llm_id", "")))):
        empirical = item.get("analise_custo_empirica", {})
        power = empirical.get("ajuste_potencia", {})
        alpha = power.get("expoente_alpha")
        algorithm_rows.append(
            f"{item.get('correct_cases', 0)}/{item.get('unique_configurations', item.get('cases', 0))} & {number(item.get('functional_accuracy'), 3)} & "
            f"{number(item.get('median_time_seconds'), 5)} & {tex(empirical.get('modelo_temporal_preferido', '---'))} & "
            f"{number(alpha, 2)}" + r"\\"
        )
    algorithm = [r"\begin{longtable}{p{1.8cm}p{1.5cm}rrrp{1.5cm}r}",
                 r"\caption{Métricas por método implementado: configurações corretas, tempo mediano e ajuste empírico. A origem identifica o arquivo C.}\label{tab:method-summary}\\",
                 r"\toprule", r"Método & Origem do código & Corretas/total & $A_f$ & Mediana (s) & Ajuste & $\alpha$\\", r"\midrule",
                 r"\endfirsthead",r"\toprule",r"Método & Origem do código & Corretas/total & $A_f$ & Mediana (s) & Ajuste & $\alpha$\\",r"\midrule",r"\endhead"]
    algorithm += algorithm_rows or [r"--- & --- & --- & --- & --- & --- & ---\\"]
    algorithm += [r"\bottomrule", r"\end{longtable}",r"\par\smallskip\footnotesize Cada linha corresponde a um algoritmo em um arquivo C específico; implementações do mesmo algoritmo não são combinadas. O tempo é a mediana por configuração; as cinco repetições são observações temporais.\normalsize"]
    write_table("algorithm_summary.tex", "\n".join(algorithm))

    complexity_rows = []
    for key in sorted(individual, key=lambda value: value.split("/", 1)[0]):
        item = individual[key]
        implementation = key.split("/")[0]
        implementation = {"chatgpt":"ChatGPT", "claude":"Claude", "gemini":"Gemini", "grok":"Grok"}.get(implementation, implementation.capitalize())
        for algorithm_name, analysis in sorted(item.get("algoritmos", {}).items()):
            complexity_rows.append(
                f"{tex(algorithm_name)} & {tex(implementation)} & "
                f"{complexity_tex(analysis.get('complexidade_temporal_codigo_atual', '---'))} & "
                f"{complexity_tex(analysis.get('complexidade_temporal_programa_com_saida', '---'))} & "
                f"{complexity_tex(analysis.get('complexidade_temporal_precisao_arbitraria', '---'))} & "
                f"{complexity_tex(analysis.get('complexidade_espacial_codigo_atual', '---'))}" + r"\\"
            )
    complexity_rows.sort(key=lambda row: (row.split(" & ", 1)[0].lower(), row.split(" & ", 2)[1].lower()))
    complexity = [r"\begin{longtable}{p{2.0cm}p{1.8cm}p{2.2cm}p{2.6cm}p{3.0cm}p{1.5cm}}",
                  r"\caption{Complexidade temporal e espacial por método implementado. A origem identifica o arquivo C, não uma classe de desempenho da IA.}\label{tab:complexidade}\\",
                  r"\toprule", r"Método & Origem do código & Núcleo atual & Com saída & Precisão arbitrária & Espaço\\", r"\midrule",
                  r"\endfirsthead", r"\toprule", r"Método & Origem do código & Núcleo atual & Com saída & Precisão arbitrária & Espaço\\", r"\midrule", r"\endhead"]
    complexity += complexity_rows or [r"--- & --- & --- & --- & --- & ---\\"]
    complexity += [r"\bottomrule", r"\end{longtable}",r"\noindent\footnotesize Estimativa estática; métodos de uma origem que falhou na compilação não foram executados.\normalsize"]
    write_table("individual_complexity.tex", "\n".join(complexity))

    total_impl = len({str(r.get("llm_id")) for r in records})
    compiled = len({key[0] for key in decimal_groups})
    config_outcomes = [configuration_outcome(group, "decimal") for group in decimal_groups.values()]
    outcome_counts = Counter(config_outcomes)
    invalid_outcomes = [configuration_outcome(group, "invalid") for group in invalid_groups.values()]
    invalid_rejected = sum(outcome == "rejected" for outcome in invalid_outcomes)
    timing_measurements = sum(
        bool(configuration_time_medians(group)) for group in decimal_groups.values()
    )
    stage_rows = [
        ("Arquivos C que compilaram", compiled),
        ("Falhas únicas no gate de compilação", len(failed_builds)),
        ("Arquivos C submetidos", total_impl),
        ("Configurações decimais únicas avaliadas", len(decimal_groups)),
        ("Configurações corretas", outcome_counts["correct"]),
        ("Configurações incorretas", outcome_counts["incorrect"]),
        ("Configurações sem saída JSON", outcome_counts["execution_failure"]),
        ("Configurações divergentes entre repetições", outcome_counts["inconsistent"]),
        ("Casos inválidos únicos rejeitados", invalid_rejected),
        ("Configurações com medições de tempo", timing_measurements),
    ]
    status = [r"\begin{tabular}{lr}", r"\toprule", r"Indicador & Contagem\\", r"\midrule"]
    status += [f"{tex(k)} & {v}" + r"\\" for k, v in stage_rows]
    status += [r"\bottomrule", r"\end{tabular}"]
    status += [r"\par\smallskip\footnotesize Uma configuração única é um método implementado (algoritmo + arquivo C)\,$\times$\,precisão. Repetições não multiplicam desfechos; servem para medir variação do tempo.\normalsize"]
    write_table("status_summary.tex", "\n".join(status))

    timing = defaultdict(list)
    for row in eligible_records:
        if row.get("case_type") != "decimal":
            continue
        if row.get("status") == "ok" and isinstance(row.get("time_seconds"), (int, float)) and row.get("time_seconds") > 0:
            timing[(row.get("llm_id"), row.get("algorithm"), int(row.get("digits")))].append(row["time_seconds"])
    timing_rows = []
    for (llm_id, algorithm_name, digits), values in sorted(timing.items(), key=lambda x: (str(x[0][1]), str(x[0][0]), x[0][2])):
        timing_rows.append(f"{tex(algorithm_name)} & {tex({'chatgpt':'ChatGPT','claude':'Claude','gemini':'Gemini','grok':'Grok'}.get(llm_id,llm_id))} & {digits} & {len(values)} & {number(median(values), 6)}" + r"\\")
    timing_table = [r"\begin{longtable}{llrrr}", r"\toprule", r"Método (algoritmo) & Origem do código & Dígitos & Medições de tempo & Mediana (s)\\", r"\midrule", r"\endfirsthead", r"\toprule", r"Método (algoritmo) & Origem do código & Dígitos & Medições de tempo & Mediana (s)\\", r"\midrule", r"\endhead"]
    timing_table += timing_rows or [r"--- & --- & --- & --- & ---\\"]
    timing_table += [r"\bottomrule", r"\end{longtable}"]
    timing_table += [r"\par\smallskip\footnotesize Cada linha é uma configuração de um método implementado (algoritmo declarado + arquivo de origem)\,$\times$\,precisão. Repetições aparecem apenas como medições de tempo; o valor mostrado é sua mediana.\normalsize"]
    write_table("timing_by_algorithm_and_digits.tex", "\n".join(timing_table))


def generate_figures(records, individual):
    """Gera as figuras editoriais orientadas pelas recomendações e evidência."""
    from generate_scientific_figures import generate_scientific_figures
    return generate_scientific_figures(records, individual)


def write_method_outcomes(records, individual):
    """Classifica cada método implementado separadamente, sem agregar por origem."""
    platforms=sorted({str(r.get("llm_id","desconhecida")) for r in records})
    failed_builds={str(r.get("llm_id")) for r in records if is_compile_failure(r)}
    groups=group_configurations([r for r in records if str(r.get("llm_id")) not in failed_builds],"decimal")
    method_units={(key[0],key[1]) for key in groups}
    for key,item in individual.items():
        p=str(item.get("llm_id",str(key).split("/",1)[0]))
        method_units.update((p,str(a)) for a in item.get("algoritmos",{}))
    out=[r"\scriptsize",r"\begin{tabular}{p{2.0cm}p{1.45cm}rrrrrr}",r"\toprule",
         r"Método & Origem do código & Config. avaliadas & Corretas & Incorretas & Sem JSON & Diverg. & $A_f$\\",r"\midrule"]
    for p,a in sorted(method_units,key=lambda pair:(pair[1].lower(),pair[0].lower())):
        subset={key:repetitions for key,repetitions in groups.items() if key[0]==p and key[1]==a}
        if p in failed_builds:
            cells=[tex(a),tex({"chatgpt":"ChatGPT","claude":"Claude","gemini":"Gemini","grok":"Grok"}.get(p,p.capitalize())),"0","---","---","---","---","não avaliável"]
        else:
            outcomes=[configuration_outcome(repetitions,"decimal") for repetitions in subset.values()]
            counts=Counter(outcomes)
            denom=len(subset)
            correct=counts["correct"]
            acc=f"{100*correct/denom:.1f}\\%" if denom else "---"
            cells=[tex(a),tex({"chatgpt":"ChatGPT","claude":"Claude","gemini":"Gemini","grok":"Grok"}.get(p,p.capitalize())),str(denom),str(correct),str(counts["incorrect"]),str(counts["execution_failure"]),str(counts["inconsistent"]),acc]
        out.append(" & ".join(cells)+r"\\")
    out += [r"\bottomrule",r"\end{tabular}",
            r"\par\smallskip\footnotesize Cada linha é um método implementado: algoritmo declarado no código de origem + níveis de precisão. A coluna de origem só identifica o arquivo, não é uma unidade de comparação entre IAs. $A_f$ é a fração correta entre configurações únicas avaliadas.\normalsize"]
    write_table("method_outcomes.tex","\n".join(out))


def write_recommendation_rationales():
    """Gera comparação compacta das cinco respostas e suas alegações declaradas."""
    source = json.loads((OUTPUT / "recommendation_claims.json").read_text(encoding="utf-8"))
    labels = {"chatgpt":"ChatGPT", "claude":"Claude", "gemini":"Gemini", "grok":"Grok"}
    source_order = ["chatgpt", "claude", "gemini", "grok"]
    series_labels = {
        "AT": "série de arco-tangente",
        "HG": "série hipergeométrica",
        "FD": "série de razão fatorial/duplo-fatorial",
        "TG": "transformação de Euler da Gregory--Leibniz",
        "AS": "série de potência do arco-seno",
        "NAK": "série alternada de Nilakantha",
    }
    by_source = defaultdict(list)
    for item in source:
        by_source[item["source"]].append(item)
    for rows in by_source.values():
        rows.sort(key=lambda item: int(item["rank"]))

    def ranked_lines(items, field, include_algorithm=False):
        rendered = []
        for item in items:
            rank = int(item["rank"])
            if include_algorithm:
                series = series_labels[item["series_code"]]
                value = rf"\texttt{{{tex(item['algorithm'])}}}: {series}"
            else:
                value = tex(item[field])
            rendered.append(rf"\textbf{{{rank}.}} {value}")
        return r"\\[-1pt]".join(rendered)

    lines = [
        r"\begingroup",
        r"\small",
        r"\setlength{\tabcolsep}{3pt}",
        r"\renewcommand{\arraystretch}{1.12}",
        r"\begin{longtable}{@{}p{1.45cm}p{5.15cm}p{8.15cm}@{}}",
        r"\caption{Recomendações em ordem e justificativas atribuídas às cinco respostas. A ordem é a declarada; justificativas não são resultados experimentais nem notas das ferramentas.}\label{tab:recommendations}" + chr(92) * 2,
        r"\toprule",
        r"Origem da resposta & Método: tipo de série (ordem declarada) & Justificativa correspondente" + chr(92) * 2,
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Origem da resposta & Método: tipo de série (ordem declarada) & Justificativa correspondente" + chr(92) * 2,
        r"\midrule",
        r"\endhead",
    ]
    for provider in source_order:
        items = by_source[provider]
        provider_label = tex(labels[provider])
        methods = ranked_lines(items, "algorithm", include_algorithm=True)
        rationales = ranked_lines(items, "rationale")
        row = f"\\textbf{{{provider_label}}} & {methods} & {rationales}"
        lines.append(row + chr(92) * 2)
        lines.append(r"\addlinespace[4pt]")
    lines += [
        r"\bottomrule",
        r"\end{longtable}",
        r"\endgroup",
    ]
    write_table("recommendation_rationales.tex", "\n".join(lines))


def write_algorithm_taxonomy() -> None:
    """Gera a tabela taxonômica legível em uma coluna do manuscrito."""
    taxonomy = json.loads((OUTPUT / "algorithm_taxonomy.json").read_text(encoding="utf-8"))
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Mecanismos algorítmicos observados, classificados pela operação matemática principal.}",
        r"\label{tab:taxonomy}",
        r"\footnotesize",
        r"\setlength{\tabcolsep}{3pt}",
        r"\begin{tabularx}{\linewidth}{L{2.9cm}L{4.25cm}X}",
        r"\toprule",
        r"Família operacional & Métodos recomendados & Forma de funcionamento / ressalva\\",
        r"\midrule",
    ]
    for row in taxonomy["families"]:
        family = tex(row["family"])
        examples = row["examples_latex"]
        operation = row["operation_latex"]
        lines.append(f"{family} & {examples} & {operation}" + chr(92) * 2)
    lines += [
        r"\bottomrule",
        r"\end{tabularx}",
        r"\end{table}",
    ]
    write_table("algorithm_taxonomy.tex", "\n".join(lines))


def main() -> None:
    """Gera todos os artefatos derivados da rodada atual."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records, execution, algorithm_ranking, individual, metadata = load_data()
    generate_tables(records, execution, algorithm_ranking, individual, metadata)
    write_method_outcomes(records, individual)
    write_recommendation_rationales()
    generate_figures(records, individual)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_files": ["results.json", "algorithm_ranking.json", "individual_code_analysis.json", "run_metadata.json", "presentation/recommendation_claims.json", "presentation/algorithm_taxonomy.json"],
        "unique_decimal_configurations": len(group_configurations(records, "decimal")),
        "compile_gate_failures": len({str(r.get("llm_id")) for r in records if is_compile_failure(r)}),
        "tables_directory": "results/presentation/tables",
        "figures_directory": "results/presentation/figures",
        "generated_catalogs": ["results/presentation/formula_catalog.json"],
        "formula_tables": [f"formula_catalog_{source}.tex" for source in ("chatgpt", "claude", "gemini", "grok")],
        "recommendation_tables": ["recommendation_order_by_source.tex"],
        "interpretation": "A ordem e as justificativas são transcritas descritivamente das respostas; a evidência empírica permanece por implementação concreta, sem score de IA. Repetições são usadas somente para resumir os tempos.",
        "figures": ["validated_precision_by_implementation.pdf", "nilakantha_accuracy_runtime_case_study.pdf"],
        "supplementary_diagrams": [],
    }
    (OUTPUT / "presentation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    include = r"""% Resultados por método implementado; compile o artigo a partir de artigo_sbc/.
% Arquivos gerados dos dados brutos em results/results.json.
\input{../pi-llm-benchmark/results/presentation/tables/experimental_configuration.tex}
\input{../pi-llm-benchmark/results/presentation/tables/individual_complexity.tex}
\input{../pi-llm-benchmark/results/presentation/tables/method_outcomes.tex}
\input{../pi-llm-benchmark/results/presentation/tables/algorithm_summary.tex}
\input{../pi-llm-benchmark/results/presentation/tables/recommendation_rationales.tex}
\input{../pi-llm-benchmark/results/presentation/tables/recommendation_order_by_source.tex}
\includegraphics[width=\linewidth]{../pi-llm-benchmark/results/presentation/figures/validated_precision_by_implementation.pdf}
\includegraphics[width=\linewidth]{../pi-llm-benchmark/results/presentation/figures/nilakantha_accuracy_runtime_case_study.pdf}
\input{../pi-llm-benchmark/results/presentation/tables/formula_catalog_chatgpt.tex}
\input{../pi-llm-benchmark/results/presentation/tables/formula_catalog_claude.tex}
\input{../pi-llm-benchmark/results/presentation/tables/formula_catalog_gemini.tex}
\input{../pi-llm-benchmark/results/presentation/tables/formula_catalog_grok.tex}
"""
    (OUTPUT / "article_includes.tex").write_text(include, encoding="utf-8")
    print(f"Apresentação gerada em {OUTPUT}")


if __name__ == "__main__":
    main()
