"""Análise teórica dos métodos de cálculo de pi observados no benchmark.

As expressões retornadas descrevem a fórmula e o código observado. Elas não substituem
as métricas empíricas, porque duas plataformas podem implementar a mesma fórmula de
maneiras diferentes.
"""

from __future__ import annotations

import math
import statistics


_ANALISES = {
    "chudnovsky": {
        "familia": "série hipergeométrica",
        "convergencia": "geométrica extremamente rápida; aproximadamente 14 casas decimais por termo",
        "estabilidade": "boa quando a soma alternada e a divisão final usam precisão maior que a meta; sensível a cancelamento e à implementação de fatoriais",
        "complexidade_temporal": "O(d^2) com aritmética inteira de precisão d e operações por termo lineares no número de dígitos",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "A fórmula calcula 1/pi e exige soma de termos grandes e uma divisão final.",
    },
    "ramanujan": {
        "familia": "série hipergeométrica para 1/pi",
        "convergencia": "geométrica extremamente rápida; aproximadamente 8 casas decimais por termo",
        "estabilidade": "boa em aritmética de alta precisão; o recíproco final exige guarda de dígitos",
        "complexidade_temporal": "O(d^2) com as operações de inteiros usadas nas submissões",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "A soma é positiva e os termos diminuem rapidamente.",
    },
    "machin": {
        "familia": "identidade de Machin e séries de arco-tangente",
        "convergencia": "geométrica; dominada pelo termo arctan(1/5), com N(d)=Theta(d)",
        "estabilidade": "boa, mas a subtração entre parcelas exige guarda de dígitos",
        "complexidade_temporal": "O(d^2) com divisão por constantes e inteiros de precisão d",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "O identificador pode representar a mesma identidade em escala para pi ou pi/4.",
    },
    "machin7": {
        "familia": "identidade alternativa do tipo Machin",
        "convergencia": "geométrica; dominada por arctan(1/7), com N(d)=Theta(d)",
        "estabilidade": "boa em precisão suficiente; a soma de parcelas deve preservar dígitos de guarda",
        "complexidade_temporal": "O(d^2) no código de precisão inteira observado",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "O sufixo 7 é um rótulo local, não uma denominação universal.",
    },
    "gauss": {
        "familia": "identidade de Gauss baseada em arco-tangente",
        "convergencia": "geométrica; o termo mais lento usa arctan(1/18), com N(d)=Theta(d)",
        "estabilidade": "boa, com possível perda por cancelamento na parcela subtraída",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "Várias séries são somadas, mas todas têm argumentos pequenos.",
    },
    "takano": {
        "familia": "identidade de arco-tangente com quatro parcelas",
        "convergencia": "geométrica; o termo dominante usa arctan(1/49), com N(d)=Theta(d)",
        "estabilidade": "boa em alta precisão; requer controle do cancelamento entre parcelas",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "O denominador 110443 produz uma parcela muito rápida, mas não elimina o custo das demais.",
    },
    "hutton": {
        "familia": "identidade curta de arco-tangente",
        "convergencia": "geométrica; dominada por arctan(1/3), com N(d)=Theta(d)",
        "estabilidade": "boa para precisão fixa, desde que as duas parcelas sejam acumuladas com guarda",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "A fórmula é simples, mas converge mais lentamente que as que usam denominadores maiores.",
    },
    "twinarctan": {
        "familia": "soma de duas séries de arco-tangente",
        "convergencia": "geométrica; dominada por arctan(1/2), com N(d)=Theta(d)",
        "estabilidade": "boa, sem subtração entre parcelas, mas com maior número de termos",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "É uma descrição de implementação, não o nome de uma família única.",
    },
    "atan23": {
        "familia": "soma de duas séries de arco-tangente",
        "convergencia": "geométrica; dominada por arctan(1/2), com N(d)=Theta(d)",
        "estabilidade": "boa em precisão suficiente; a soma não tem cancelamento de sinais",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "É matematicamente a mesma identidade registrada como twinarctan.",
    },
    "euler": {
        "familia": "série positiva de Euler",
        "convergencia": "geométrica moderada; a razão assintótica dos termos tende a 1/2",
        "estabilidade": "boa por não alternar sinais nessa forma, mas exige muitos termos",
        "complexidade_temporal": "O(d^2) se o limite de termos crescer linearmente com d",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "Implementações com limite fixo de termos deixam de ser assintoticamente válidas para d arbitrário.",
    },
    "newton": {
        "familia": "série de Newton baseada em arco-seno",
        "convergencia": "geométrica moderada; a razão assintótica dos termos é aproximadamente 1/4",
        "estabilidade": "boa para a recorrência positiva; a precisão da divisão ainda limita o resultado",
        "complexidade_temporal": "O(d^2)",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(d)",
        "observacao": "A recorrência evita recalcular fatoriais a cada termo.",
    },
    "nilakantha": {
        "familia": "série alternada racional de Nilakantha",
        "convergencia": "algébrica, com termo de ordem Theta(k^-3); para d casas, N(d)=Theta(10^(d/3))",
        "estabilidade": "moderada: a alternância e a acumulação de muitos termos podem amplificar arredondamentos",
        "complexidade_temporal": "O(10^(d/3) d) com operações de precisão d; exponencial em d",
        "complexidade_espacial": "O(d)",
        "termos_necessarios": "N(d)=Theta(10^(d/3))",
        "observacao": "É excelente como linha de base simples, mas inadequada para alta precisão sem aceleração.",
    },
}


def analise_do_algoritmo(nome: str) -> dict:
    """Retorna a análise teórica de um algoritmo ou um registro explícito de desconhecido."""
    chave = str(nome).lower()
    if chave in _ANALISES:
        return {"algoritmo": chave, **_ANALISES[chave]}
    return {
        "algoritmo": chave,
        "familia": "não documentada",
        "convergencia": "não determinada",
        "estabilidade": "não determinada",
        "complexidade_temporal": "não determinada",
        "complexidade_espacial": "não determinada",
        "termos_necessarios": "não determinado",
        "observacao": "O método não possui descrição teórica cadastrada.",
    }


def analises_de_algoritmos(nomes):
    """Retorna análises em ordem determinística para os nomes recebidos."""
    return {str(nome): analise_do_algoritmo(nome) for nome in sorted(set(nomes))}


def _ajuste_linear(pontos):
    """Ajusta y=a+b*x e retorna inclinação, intercepto e R²."""
    if len(pontos) < 3:
        return None
    xs = [float(x) for x, _ in pontos]
    ys = [float(y) for _, y in pontos]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    soma_xx = sum((x - mx) ** 2 for x in xs)
    if soma_xx == 0:
        return None
    inclinacao = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / soma_xx
    intercepto = my - inclinacao * mx
    pred = [intercepto + inclinacao * x for x in xs]
    soma_res = sum((y - yp) ** 2 for y, yp in zip(ys, pred))
    soma_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 if soma_tot == 0 else max(0.0, 1.0 - soma_res / soma_tot)
    return {"inclinacao": inclinacao, "intercepto": intercepto, "r2": r2}


def _resumo_ajuste(ajuste, tipo):
    'Converte um ajuste linear em uma representação de relatório legível.'
    if not ajuste:
        return {"modelo": "não estimável", "r2": None}
    if tipo == "potencia":
        return {
            "modelo": "t(d)=C*d^alpha",
            "expoente_alpha": ajuste["inclinacao"],
            "intercepto_logaritmico": ajuste["intercepto"],
            "r2": ajuste["r2"],
        }
    return {
        "modelo": "t(d)=C*exp(beta*d)",
        "taxa_beta": ajuste["inclinacao"],
        "intercepto_logaritmico": ajuste["intercepto"],
        "r2": ajuste["r2"],
    }


def analise_custo_empirica(registros):
    """Ajusta tempos por par implementação--algoritmo usando um ponto mediano por precisão."""
    unidades=sorted({(str(r.get("llm_id", "desconhecida")),str(r.get("algorithm")))
                     for r in registros if r.get("algorithm") and r.get("case_type")=="decimal"})
    saida={}
    for implementacao,nome in unidades:
        validos=[r for r in registros
                 if str(r.get("llm_id", "desconhecida"))==implementacao
                 and str(r.get("algorithm"))==nome
                 and r.get("case_type")=="decimal" and r.get("status")=="ok"
                 and isinstance(r.get("digits"),(int,float))
                 and isinstance(r.get("time_seconds"),(int,float)) and r.get("time_seconds")>0]
        por_digitos={}; memoria_por_digitos={}
        for r in validos:
            d=int(r["digits"]); por_digitos.setdefault(d,[]).append(float(r["time_seconds"]))
            memoria=r.get("peak_rss_kb")
            if isinstance(memoria,(int,float)) and memoria>0:
                memoria_por_digitos.setdefault(d,[]).append(float(memoria))
        tempos=sorted((d,statistics.median(v)) for d,v in por_digitos.items())
        memoria=sorted((d,statistics.median(v)) for d,v in memoria_por_digitos.items())
        pontos_log=[(math.log(d),math.log(t)) for d,t in tempos if d>0 and t>0]
        pontos_semi=[(float(d),math.log(t)) for d,t in tempos if d>0 and t>0]
        ajuste_potencia=_ajuste_linear(pontos_log); ajuste_exponencial=_ajuste_linear(pontos_semi)
        melhor=None
        if ajuste_potencia and ajuste_exponencial:
            melhor="potência" if ajuste_potencia["r2"]>=ajuste_exponencial["r2"] else "exponencial"
        saida[f"{implementacao}/{nome}"]={
            "llm_id":implementacao,"algorithm":nome,
            "observacao":"estimativa da implementação identificada; um ponto por precisão, calculado pela mediana das medições temporais repetidas; não é prova assintótica",
            "pontos_temporais":[{"digitos":d,"mediana_segundos":t,"medicoes_tempo":len(por_digitos[d])} for d,t in tempos],
            "ajuste_potencia":_resumo_ajuste(ajuste_potencia,"potencia"),
            "ajuste_exponencial":_resumo_ajuste(ajuste_exponencial,"exponencial"),
            "modelo_temporal_preferido":melhor or "não estimável",
            "pontos_memoria":[{"digitos":d,"mediana_kb":m} for d,m in memoria],
            "ajuste_memoria":_resumo_ajuste(_ajuste_linear([(math.log(d),math.log(m)) for d,m in memoria if d>0 and m>0]),"potencia"),
            "quantidade_de_niveis_temporais":len(tempos),"quantidade_de_niveis_memoria":len(memoria),
            "quantidade_total_medicoes_temporais":sum(len(v) for v in por_digitos.values()),
        }
    return saida
