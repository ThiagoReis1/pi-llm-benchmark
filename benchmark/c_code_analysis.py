"""Análise estática heurística da implementação C de cada plataforma.

O módulo não promete uma prova formal para C arbitrário. Ele extrai evidências
reprodutíveis do código recebido: limites constantes, uso de ``digits``/``prec``,
quantidade fixa de limbs e a família matemática declarada. O resultado é
específico por arquivo C e mantém separado o custo observado do custo de uma
versão de precisão arbitrária.
"""
from __future__ import annotations
import re
from pathlib import Path


def _defines(source):
    'Extrai macros numéricas simples definidas no código C.'
    out = {}
    for name, value in re.findall(r"(?m)^\s*#define\s+([A-Za-z_]\w*)\s+([0-9]+)", source):
        out[name] = int(value)
    return out


def _limb_info(source, defines):
    'Infere a capacidade e o crescimento da representação por limbs.'
    preferred = [(k, v) for k, v in defines.items()
                 if k.upper() in {"NL", "NUM_LIMBS", "MAX_LIMBS", "BIG_CAP", "LIMB_CAP"}
                 or k.upper().endswith("_LIMBS")]
    candidates = preferred or [(k, v) for k, v in defines.items()
                               if any(x in k.upper() for x in ("LIMB", "CAP"))]
    arrays = re.findall(r"(?:uint\w+|int\w+)\s+\w+\s*\[\s*([A-Za-z_]\w*|[0-9]+)\s*\]", source)
    fixed = []
    for token in arrays:
        if token.isdigit():
            fixed.append(int(token))
        elif token in defines:
            fixed.append(defines[token])
    if preferred:
        value = max(v for _, v in preferred)
    elif fixed:
        value = max(fixed)
    elif candidates:
        value = max(v for _, v in candidates)
    else:
        value = None
    return {"limbs_fixos": value, "representacao_cresce_com_d": bool(re.search(r"malloc|realloc|digits.*limb|limb.*digits|prec.*limb", source, re.I))}


def _body_for(source, name):
    'Localiza o corpo de uma função C pelo nome e pelo balanceamento de chaves.'
    patterns = [rf"(?:static\s+)?(?:\w+[\s*]+)+{re.escape(name)}\s*\([^{{;]*\)\s*\{{",
                rf"\b{re.escape(name)}\s*\([^{{;]*\)\s*\{{"]
    for pattern in patterns:
        m = re.search(pattern, source)
        if not m:
            continue
        start, depth, i = m.start(), 0, m.end() - 1
        for j in range(i, len(source)):
            if source[j] == "{": depth += 1
            elif source[j] == "}":
                depth -= 1
                if depth == 0:
                    return source[start:j + 1]
    return ""


def _function_name(algorithm):
    'Retorna os nomes prováveis da função que implementa um algoritmo.'
    key = algorithm.lower().replace("-", "_")
    return {
        "machin7": ("algorithm_machin7", "machin7"),
        "gauss": ("algorithm_gauss", "gauss"),
        "machin": ("algorithm_machin", "alg_machin", "run_machin", "machin"),
        "atan23": ("algorithm_atan23", "atan23"),
        "euler": ("algorithm_euler", "alg_euler", "run_euler", "euler"),
        "chudnovsky": ("alg_chudnovsky", "run_chudnovsky", "chudnovsky"),
        "ramanujan": ("alg_ramanujan", "run_ramanujan", "ramanujan"),
        "nilakantha": ("run_nilakantha", "nilakantha"),
        "twinarctan": ("twinarctan",),
    }.get(key, (key,))


def _has_digit_control(body):
    'Verifica se o corpo do algoritmo controla precisão ou iterações por dígitos.'
    return bool(re.search(r"\b(?:digits|prec|requested_digits)\b", body))


def analisar_codigo_c(path: str | Path, algorithms):
    'Analisa individualmente um arquivo C com regras heurísticas reproduzíveis.'
    path = Path(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    compile_text = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    defines = _defines(compile_text)
    limb = _limb_info(compile_text, defines)
    resultados = {}
    for algorithm in algorithms:
        nome = str(algorithm).lower()
        bodies = [_body_for(compile_text, n) for n in _function_name(nome)]
        body = "\n".join(b for b in bodies if b)
        if not body:
            body = _body_for(compile_text, "compute_pi") or _body_for(compile_text, "pi_series")
        digit_control = _has_digit_control(body)
        threshold_loop = bool(re.search(r"threshold|prec\s*=\s*digits|digits\s*\+\s*GUARD|arctan_inv\s*\([^)]*prec", compile_text, re.I))
        fixed_loop = bool(re.search(r"for\s*\([^;]*;[^;]*(?:MAX\w+|\d{2,}|1000|120)[^;]*;", body))
        fixed_arctan = "MAX_ARCTAN_TERMS" in compile_text or ("atan_inv" in compile_text and "MAXITER" in compile_text)
        fixed_euler = "MAX_EULER_TERMS" in compile_text or bool(re.search(r"alg_euler[\s\S]{0,1800}MAXITER", compile_text))
        fixed_hyper = bool(re.search(r"for[^\n]*k\s*<\s*(?:4|6|1000)", body)) or bool(re.search(r"alg_(?:chudnovsky|ramanujan)[\s\S]{0,1800}k\s*<\s*1000", compile_text)) or (nome in {"chudnovsky", "ramanujan"} and bool(re.search(r"for\s*\([^;]*k\s*<\s*(?:4|6)", compile_text)))
        fixed_precision = bool(re.search(r"1e-30|1E-30|MAXITER|MAX_ARCTAN_TERMS|MAX_EULER_TERMS", compile_text)) and not bool(re.search(r"bignum_set_pow10_neg\s*\([^;]*digits|prec\s*=\s*digits", compile_text))
        if nome in {"machin", "machin7", "gauss", "atan23", "takano", "hutton", "twinarctan"} and fixed_arctan:
            fixed_loop = True
        if nome == "euler" and fixed_euler:
            fixed_loop = True
        if nome in {"chudnovsky", "ramanujan"} and fixed_hyper:
            fixed_loop = True
        if fixed_precision:
            fixed_loop = True
            threshold_loop = False
        if nome == "nilakantha":
            termos = "O(1) no limite fixo do código" if fixed_loop else "Theta(10^(d/3))"
            temporal_arbitrario = "O(d * 10^(d/3))"
            temporal_atual = "Theta(1)" if fixed_loop else ("Theta(10^(d/3))" if limb["limbs_fixos"] else temporal_arbitrario)
            motivo = "limiar fixo independente de digits" if fixed_loop else "termo racional de ordem k^-3; o laço continua até o termo atingir o limiar"
        else:
            termos = "Theta(d)" if digit_control or threshold_loop else "O(1) no limite fixo do código"
            if fixed_loop and not digit_control:
                temporal_atual = "Theta(1)"
                temporal_arbitrario = "O(d^2) se o limite de termos e os limbs crescerem com d"
                motivo = "laço com limite constante e/ou quantidade de termos fixa"
            elif digit_control or threshold_loop:
                temporal_atual = "Theta(d)" if limb["limbs_fixos"] else "O(d^2)"
                temporal_arbitrario = "O(d^2)"
                motivo = "o limiar, a precisão ou o número de termos depende de digits/prec"
            else:
                temporal_atual = "não determinado automaticamente"
                temporal_arbitrario = "não determinado"
                motivo = "não foi identificado um controlador de laço suficiente"
        if nome == "euler" and "differences" in compile_text and re.search(r"for\s*\([^;]*;[^;]*;[^)]*\)\s*\{[\s\S]{0,800}for\s*\(", compile_text):
            temporal_arbitrario = "O(d^3) se o número de diferenças, os termos e os limbs crescerem com d"
            motivo = "transformação de Euler com atualização em laços aninhados; o núcleo generalizado tem O(d^3)"
        memoria_atual = "Theta(1)" if limb["limbs_fixos"] and not limb["representacao_cresce_com_d"] else "cresce com d"
        if temporal_atual == "Theta(1)":
            temporal_total = "Theta(d) incluindo a formatação da saída"
        else:
            temporal_total = temporal_atual
        resultados[nome] = {
            "metodo": "análise estática do código C por regras de evidência",
            "arquivo": str(path),
            "algoritmo": nome,
            "complexidade_temporal_codigo_atual": temporal_atual,
            "complexidade_temporal_programa_com_saida": temporal_total,
            "complexidade_temporal_precisao_arbitraria": temporal_arbitrario,
            "complexidade_espacial_codigo_atual": memoria_atual,
            "termos_necessarios_inferidos": termos,
            "limbs_fixos_detectados": limb["limbs_fixos"],
            "controlador_depende_de_digits_ou_prec": digit_control or threshold_loop,
            "limite_de_laco_constante_detectado": fixed_loop,
            "evidencia": motivo,
            "status": "analisado_automaticamente_com_heuristicas_reprodutiveis",
        }
    return resultados
