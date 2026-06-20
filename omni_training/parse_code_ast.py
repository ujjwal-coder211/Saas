"""Offline job: enrich code rows with lightweight AST summaries (Python)."""

from __future__ import annotations

import ast
import re

from omni_training.vault import CURATED_PATH, vault_read_all, vault_rewrite


def summarize_python(code: str) -> dict:
    try:
        tree = ast.parse(code)
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        imports = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports.extend(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                imports.append(n.module)
        return {
            "language": "python",
            "functions": funcs[:20],
            "classes": classes[:20],
            "imports": imports[:30],
            "line_count": len(code.splitlines()),
        }
    except SyntaxError:
        return {"language": "python", "parse_error": True}


def enrich_curated() -> dict:
    rows = vault_read_all(CURATED_PATH)
    if not rows:
        return {"updated": 0}

    updated = 0
    for row in rows:
        ast_meta = row.get("code_ast")
        if ast_meta and ast_meta.get("needs_full_ast_parse"):
            response = row.get("model_response", "")
            blocks = re.findall(r"```python\n(.*?)```", response, re.DOTALL | re.I)
            if blocks:
                summaries = [summarize_python(b) for b in blocks[:3]]
                row["code_ast"] = {
                    **ast_meta,
                    "ast_summaries": summaries,
                    "needs_full_ast_parse": False,
                }
                updated += 1

    vault_rewrite(CURATED_PATH, rows)
    return {"updated": updated}


if __name__ == "__main__":
    print(enrich_curated())
