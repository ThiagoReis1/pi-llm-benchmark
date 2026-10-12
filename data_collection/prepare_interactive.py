#!/usr/bin/env python3
"""Prepare a benchmark response using direct paste and one confirmation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

try:
    from .prepare_submission import extract_code, sha256_bytes
except ImportError:  # execução direta: python data_collection/prepare_interactive.py
    from prepare_submission import extract_code, sha256_bytes

PLATFORMS = {
    "1": ("ChatGPT", "chatgpt"),
    "2": ("Claude", "claude"),
    "3": ("Gemini", "gemini"),
    "5": ("Grok", "grok"),
}
IDLE_SECONDS = 0.8


def ask(label: str, default: str = "") -> str:
    'Solicita uma resposta ao operador, aplicando um valor padrão quando informado.'
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def read_pasted_response() -> str:
    'Lê a resposta completa colada pelo operador em Linux, macOS ou Windows.'
    print("\nCopie a resposta COMPLETA da IA para a área de transferência.")
    print("No Windows: selecione e copie a resposta com Ctrl+C no navegador e volte para cá.")
    print("No Linux/macOS: cole diretamente nesta tela; o fim será detectado automaticamente.\n")

    if not sys.stdin.isatty():
        return sys.stdin.read()

    if os.name == "nt":
        input("Pressione Enter para ler a resposta copiada da área de transferência...")
        commands = ["powershell.exe", "powershell"]
        for command in commands:
            try:
                result = subprocess.run(
                    [command, "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        raise ValueError("não foi possível ler a área de transferência do Windows")

    import termios
    import tty
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    chars: list[str] = []
    try:
        tty.setcbreak(fd)
        first, _, _ = select.select([sys.stdin], [], [], 30)
        if not first:
            raise ValueError("tempo esgotado aguardando a colagem")
        while True:
            data = os.read(fd, 4096)
            if data:
                chars.append(data.decode("utf-8", errors="replace"))
                continue
            ready, _, _ = select.select([sys.stdin], [], [], IDLE_SECONDS)
            if not ready:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    raw = "".join(chars)
    if not raw.strip():
        raise ValueError("nenhum conteúdo foi colado")
    return raw


def show_preview(raw: str, code: str, extraction_mode: str) -> None:
    'Exibe uma prévia da resposta e do código antes da confirmação.'
    def excerpt(text: str, limit: int = 12) -> list[str]:
        'Executa a operação `excerpt` no fluxo do projeto.'
        lines = text.splitlines()
        if len(lines) <= limit * 2:
            return lines
        return lines[:limit] + ["... (trecho omitido) ..."] + lines[-limit:]

    print("\n========== PRÉ-VISUALIZAÇÃO ==========")
    print(f"Resposta recebida: {len(raw.splitlines())} linhas")
    print(f"Modo de extração: {extraction_mode}")
    print("\n--- início/fim da resposta original ---")
    print("\n".join(excerpt(raw)) or "(vazio)")
    print("\n--- início/fim do código que será executado ---")
    print("\n".join(excerpt(code)) or "(vazio)")
    print("\nValidação C: será feita pelo gcc durante a execução do benchmark")
    print("========================================\n")


def main() -> int:
    'Executa o fluxo principal do módulo ou da ferramenta de coleta.'
    root = Path(__file__).resolve().parents[1]
    print("\nPreparação de resposta do benchmark\n")
    print("1) ChatGPT\n2) Claude\n3) Gemini\n4) Grok")
    choice = ask("Plataforma")
    if choice not in PLATFORMS:
        print("Opção inválida.", file=sys.stderr)
        return 2
    platform, llm_id = PLATFORMS[choice]
    attempt = ask("Número da tentativa", "1")
    if attempt != "1":
        print("Esta versão aceita somente a tentativa 1 por plataforma.", file=sys.stderr)
        return 2

    try:
        raw = read_pasted_response()
        code, extraction_mode = extract_code(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        print(f"Resposta não preparada automaticamente: {exc}", file=sys.stderr)
        print("Nada foi salvo. Verifique se a resposta possui um único bloco Markdown.", file=sys.stderr)
        return 1

    show_preview(raw, code, extraction_mode)
    print("Aceita: y, Y, s, S, sim, SIM, yes ou YES.")
    confirm = input("Confirmar e salvar esta resposta? [Y/N]: ").strip().lower()
    if confirm not in {"y", "yes", "s", "sim"}:
        print("Operação cancelada. Nada foi alterado.")
        return 0

    out_dir = root / "submissions" / llm_id / f"attempt_{int(attempt):02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_bytes = raw.encode("utf-8")
    code_bytes = code.encode("utf-8")
    (out_dir / "response_original.txt").write_bytes(raw_bytes)
    (out_dir / "submission.c").write_bytes(code_bytes)
    prompt_hash = sha256_bytes((root / "prompts" / "benchmark_prompt.txt").read_bytes())
    metadata = {
        "llm_id": llm_id,
        "platform": platform,
        "prompt_id": "benchmark_prompt_c_single_markdown_block",
        "prompt_sha256": prompt_hash,
        "attempt": int(attempt),
        "extraction_mode": extraction_mode,
        "manual_logic_changes": False,
        "response_file": "response_original.txt",
        "response_original_sha256": sha256_bytes(raw_bytes),
        "submission_sha256": sha256_bytes(code_bytes),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Salvo em: {out_dir}")
    print(f"Modo de extração: {extraction_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
