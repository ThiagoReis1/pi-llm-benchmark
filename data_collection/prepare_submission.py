#!/usr/bin/env python3
"""Prepare one collected LLM response for the benchmark.

The raw response is preserved byte-for-byte in response_original.txt.
Only a single outer Markdown fence is removed for submission.c.
Multiple fenced blocks are rejected to avoid silently changing the answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

FENCE_RE = re.compile(r"(?ms)^\s*```(?:c|c11)?\s*\r?\n(.*?)^\s*```\s*$")


def sha256_bytes(data: bytes) -> str:
    'Calcula o hash SHA-256 de uma sequência de bytes.'
    return hashlib.sha256(data).hexdigest()


def extract_code(raw: str) -> tuple[str, str]:
    'Extrai o único bloco C permitido da resposta original da plataforma.'
    matches = list(FENCE_RE.finditer(raw))
    if not matches:
        # Sem cerca Markdown (ex.: o botão "copiar código" da interface já a removeu). Só é
        # aceito se o texto parecer um arquivo C puro; uma página inteira colada (menus,
        # eco do prompt, rodapé da interface) é rejeitada em vez de ser salva como código.
        first_line = next((line.strip() for line in raw.lstrip("\ufeff").splitlines() if line.strip()), "")
        if not first_line.startswith(("/*", "//", "#")):
            raise ValueError(
                "a resposta não tem bloco ```c e não começa como um arquivo C "
                "(provável colagem da página inteira); copie apenas o bloco de código"
            )
        return raw, "raw_response"
    if len(matches) != 1:
        raise ValueError(
            f"resposta contém {len(matches)} blocos Markdown; revisão manual necessária"
        )
    match = matches[0]
    before = raw[: match.start()].strip()
    after = raw[match.end() :].strip()
    if before or after:
        raise ValueError(
            "a resposta contém texto fora do único bloco Markdown; revisão manual necessária"
        )
    return match.group(1), "removed_markdown_fence"


def main() -> int:
    'Executa o fluxo principal do módulo ou da ferramenta de coleta.'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--llm-id", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--attempt", required=True, type=int)
    args = parser.parse_args()

    raw_bytes = args.response.read_bytes()
    raw = raw_bytes.decode("utf-8")
    code, extraction_mode = extract_code(raw)
    code_bytes = code.encode("utf-8")
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "benchmark_prompt.txt"
    prompt_hash = sha256_bytes(prompt_path.read_bytes())

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "response_original.txt").write_bytes(raw_bytes)
    (args.output_dir / "submission.c").write_bytes(code_bytes)
    metadata = {
        "llm_id": args.llm_id,
        "platform": args.platform,
        "prompt_id": "benchmark_prompt_c_single_markdown_block",
        "prompt_sha256": prompt_hash,
        "attempt": args.attempt,
        "extraction_mode": extraction_mode,
        "manual_logic_changes": False,
        "response_file": "response_original.txt",
        "response_original_sha256": sha256_bytes(raw_bytes),
        "submission_sha256": sha256_bytes(code_bytes),
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output_dir": str(args.output_dir), "extraction_mode": extraction_mode}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
