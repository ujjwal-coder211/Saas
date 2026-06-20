"""
Codebase index scaffold — keyword search MVP.

Structure supports future Qdrant vector backend (see IndexConfig.use_vectors).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IndexConfig:
    chunk_size: int = 800
    chunk_overlap: int = 100
    use_vectors: bool = False
    qdrant_url: str = ""


@dataclass
class IndexChunk:
    id: str
    path: str
    start_line: int
    end_line: int
    text: str
    keywords: list[str] = field(default_factory=list)


class CodebaseIndex:
    def __init__(self, config: IndexConfig | None = None) -> None:
        self.config = config or IndexConfig()
        self._chunks: list[IndexChunk] = []

    def clear(self) -> None:
        self._chunks.clear()

    def index_directory(self, root: Path, *, globs: list[str] | None = None) -> int:
        self.clear()
        patterns = globs or ["**/*.py", "**/*.js", "**/*.ts", "**/*.html", "**/*.md", "**/*.json"]
        root = root.resolve()
        seen: set[Path] = set()
        for pattern in patterns:
            for fp in root.glob(pattern):
                if not fp.is_file() or fp in seen:
                    continue
                if any(part.startswith(".") for part in fp.parts):
                    continue
                seen.add(fp)
                self._index_file(fp, root)
        return len(self._chunks)

    def _index_file(self, fp: Path, root: Path) -> None:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        rel = str(fp.relative_to(root))
        lines = text.splitlines()
        size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        start = 0
        chunk_idx = 0
        while start < len(lines):
            end = min(len(lines), start + max(1, size // 40))
            chunk_text = "\n".join(lines[start:end])
            keywords = _extract_keywords(chunk_text)
            self._chunks.append(
                IndexChunk(
                    id=f"{rel}:{chunk_idx}",
                    path=rel,
                    start_line=start + 1,
                    end_line=end,
                    text=chunk_text,
                    keywords=keywords,
                )
            )
            chunk_idx += 1
            if end >= len(lines):
                break
            start = max(0, end - overlap // 40)

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        q_tokens = set(_extract_keywords(query))
        if not q_tokens:
            return []
        scored: list[tuple[float, IndexChunk]] = []
        for ch in self._chunks:
            overlap = q_tokens.intersection(set(ch.keywords))
            if not overlap:
                if query.lower() not in ch.text.lower():
                    continue
                score = 0.5
            else:
                score = len(overlap) / max(len(q_tokens), 1)
            scored.append((score, ch))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, ch in scored[:limit]:
            out.append(
                {
                    "score": round(score, 3),
                    "path": ch.path,
                    "lines": [ch.start_line, ch.end_line],
                    "preview": ch.text[:400],
                }
            )
        return out

    def to_json(self) -> str:
        return json.dumps(
            [
                {
                    "id": c.id,
                    "path": c.path,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "text": c.text,
                    "keywords": c.keywords,
                }
                for c in self._chunks
            ],
            ensure_ascii=False,
        )


def _extract_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
    stop = {"the", "and", "for", "with", "from", "this", "that", "return", "import"}
    return [t for t in tokens if t not in stop][:40]
