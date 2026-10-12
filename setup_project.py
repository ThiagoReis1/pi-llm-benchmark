#!/usr/bin/env python3
"""Inicializa, prepara e limpa o PI LLM Benchmark.

O comando padrão:
1. cria o ambiente virtual .venv, se ele não existir;
2. instala as dependências de requirements.txt dentro do .venv;
3. cria as pastas de entradas e resultados.

Uso:
    python setup_project.py
    python setup_project.py --clean-results
    python setup_project.py --reset
    python setup_project.py --remove-venv
    python setup_project.py --recreate-venv

Ao terminar, o script mostra o comando de ativação para o terminal atual.
Ele nunca abre uma nova sessão de PowerShell ou Bash.
As operações de limpeza são executadas diretamente pelo comando escolhido.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
PROVIDERS = ("chatgpt", "claude", "gemini", "grok")


def venv_python() -> Path:
    """Retorna o executável Python do venv em Windows ou POSIX."""
    relative = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return VENV / relative


def create_virtual_environment() -> Path:
    """Cria o ambiente virtual quando necessário e retorna seu Python."""
    python = venv_python()
    config = VENV / "pyvenv.cfg"
    if python.exists() and config.exists():
        print(f"Ambiente virtual existente; reutilizando: {VENV}")
    else:
        print(f"Criando ambiente virtual em: {VENV}")
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], cwd=ROOT, check=True)
    if not python.exists():
        raise RuntimeError(f"O Python do ambiente virtual não foi criado: {python}")
    activation = VENV / (Path("Scripts") / "Activate.ps1" if os.name == "nt" else Path("bin") / "activate")
    if not activation.exists():
        raise RuntimeError(f"O script de ativação não foi criado: {activation}")
    return python


def remove_virtual_environment() -> None:
    """Remove o ambiente virtual local, sem tocar no código ou nos resultados."""
    if VENV.exists():
        print(f"Removendo ambiente virtual: {VENV}")
        shutil.rmtree(VENV)
    else:
        print("Ambiente virtual não existe; nada para remover.")


def install_requirements(python: Path) -> None:
    """Instala as dependências no ambiente virtual do projeto."""
    if not REQUIREMENTS.is_file():
        raise FileNotFoundError(f"Arquivo ausente: {REQUIREMENTS}")
    print("Instalando requirements.txt no ambiente virtual...")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
        check=True,
    )


def create_structure() -> None:
    """Cria as pastas necessárias sem apagar arquivos existentes."""
    directories = [
        ROOT / "tools",
        ROOT / "results" / "logs",
        ROOT / "results" / "presentation" / "tables",
        ROOT / "results" / "presentation" / "figures",
        ROOT / "submissions",
    ]
    directories.extend(ROOT / "submissions" / provider for provider in PROVIDERS)
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    (ROOT / "results" / ".gitkeep").touch(exist_ok=True)
    for provider in PROVIDERS:
        (ROOT / "submissions" / provider / ".gitkeep").touch(exist_ok=True)


def remove_children(directory: Path, preserve_names: set[str] | None = None) -> int:
    """Remove o conteúdo direto de uma pasta, preservando nomes informados."""
    preserve_names = preserve_names or set()
    removed = 0
    if not directory.exists():
        return removed
    for child in directory.iterdir():
        if child.name in preserve_names:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    return removed


def clean_results() -> int:
    """Remove resultados, logs e apresentações gerados, preservando results/."""
    return remove_children(ROOT / "results", {".gitkeep"})


def clean_submissions() -> int:
    """Remove tentativas coletadas, preservando as pastas das plataformas."""
    removed = 0
    for provider in PROVIDERS:
        removed += remove_children(ROOT / "submissions" / provider, {".gitkeep"})
    return removed


def clean_caches() -> int:
    """Remove caches Python locais que não fazem parte do projeto."""
    removed = 0
    for directory in ROOT.rglob("__pycache__"):
        if directory.is_dir() and VENV not in directory.parents:
            shutil.rmtree(directory)
            removed += 1
    return removed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepara, inicializa ou limpa o PI LLM Benchmark.")
    parser.add_argument("--clean-results", action="store_true", help="Apaga resultados, logs, tabelas e figuras gerados.")
    parser.add_argument("--reset", action="store_true", help="Apaga resultados e submissões coletadas.")
    parser.add_argument("--remove-venv", action="store_true", help="Apaga somente o ambiente virtual .venv.")
    parser.add_argument("--recreate-venv", action="store_true", help="Apaga e recria .venv antes de instalar as dependências.")
    parser.add_argument("--no-cache-clean", action="store_true", help="Não remove caches __pycache__.")
    return parser.parse_args()


def print_usage_summary() -> None:
    """Mostra os comandos principais disponíveis após a preparação."""
    print("\nOpções do setup_project.py:")
    print("  python setup_project.py                         preparar e mostrar ativação")
    print("  python setup_project.py --clean-results   apagar resultados/logs; manter submissões")
    print("  python setup_project.py --reset            apagar resultados/logs e submissões")
    print("  python setup_project.py --remove-venv      apagar somente o .venv")
    print("  python setup_project.py --recreate-venv    recriar o .venv e instalar dependências")
    print("  python setup_project.py --help                   mostrar a ajuda completa")
    print("\nAtivação manual do ambiente:")
    print(r"  Windows PowerShell: .\.venv\Scripts\Activate.ps1")
    print("  Linux/macOS/WSL:    source .venv/bin/activate")


def main() -> int:
    args = parse_args()
    clean_results_requested = args.clean_results or args.reset
    clean_submissions_requested = args.reset
    try:
        if args.remove_venv or args.recreate_venv:
            remove_virtual_environment()
        if args.remove_venv and not args.recreate_venv:
            create_structure()
            print(f"Projeto pronto em: {ROOT}")
            print_usage_summary()
            return 0
        python = create_virtual_environment()
        install_requirements(python)
        create_structure()
        if clean_results_requested:
            print(f"Resultados removidos: {clean_results()} itens")
        if clean_submissions_requested:
            print(f"Submissões removidas: {clean_submissions()} tentativas/pastas")
        if not args.no_cache_clean:
            print(f"Caches removidos: {clean_caches()}")
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Falha na preparação: {exc}", file=sys.stderr)
        return 1

    print(f"Projeto pronto em: {ROOT}")
    print(f"Python do projeto: {venv_python()}")
    print_usage_summary()
    if os.name == "nt":
        print(r"Ative neste terminal: .\.venv\Scripts\Activate.ps1")
    else:
        print("Ative neste terminal: source .venv/bin/activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
