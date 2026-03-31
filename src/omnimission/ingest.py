from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from omnimission.chroma_store import ChromaStore
from omnimission.embeddings import embed_texts


def _chunk_id(title: str, body: str) -> str:
    """Stable id from title + body so identical chunks dedupe across URLs/publishers."""
    raw = f"{title.strip().lower()}\n\n{body.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_frontmatter(blob: str) -> tuple[dict[str, Any], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", blob, re.DOTALL)
    if not m:
        return {}, blob
    body = blob[m.end() :]
    meta: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip().lower()] = v.strip()
    return meta, body


def chunk_markdown_skill_like(url: str, content: str, publisher: str) -> list[dict[str, Any]]:
    """Split markdown-ish text into pseudo-skill records."""
    meta, rest = _parse_frontmatter(content)
    sections = re.split(r"(?m)^##\s+", rest)
    out: list[dict[str, Any]] = []
    if len(sections) <= 1 and not meta:
        title = meta.get("name") or meta.get("title") or f"page:{url}"
        text = rest.strip() or content.strip()
        if len(text) < 48:
            return []
        out.append(
            {
                "title": str(title)[:256],
                "body": text[:12000],
                "source_url": url,
                "publisher": publisher,
            }
        )
        return out

    first = sections[0].strip()
    if first and len(first) > 80:
        title = meta.get("name") or meta.get("title") or "intro"
        out.append(
            {
                "title": str(title)[:256],
                "body": first[:12000],
                "source_url": url,
                "publisher": publisher,
            }
        )

    for sec in sections[1:]:
        lines = sec.splitlines()
        title = (lines[0] if lines else "section").strip()[:256]
        body = "\n".join(lines[1:]).strip()[:12000]
        if len(body) < 24:
            continue
        out.append(
            {
                "title": title,
                "body": body,
                "source_url": url,
                "publisher": publisher,
            }
        )
    return out


def build_metadata(record: dict[str, Any]) -> dict[str, Any]:
    title = record["title"]
    publisher = record["publisher"]
    source_url = record["source_url"]
    quality = float(record.get("quality_score", 72.0))
    safety = float(record.get("safety_score", 78.0))
    x402 = float(record.get("x402_price_usd", 0.0))
    installs = record.get("install_commands") or []
    if isinstance(installs, str):
        installs = [installs]
    return {
        "title": title[:512],
        "publisher": publisher[:256],
        "source_url": source_url[:1024],
        "quality_score": quality,
        "safety_score": safety,
        "x402_price_usd": x402,
        "install_commands_json": json.dumps(installs),
        "indexed_at": datetime.now(UTC).isoformat(),
        "content_sha256": _chunk_id(str(record["title"]), str(record.get("body") or "")),
    }


def ingest_records(
    store: ChromaStore,
    model_name: str,
    records: list[dict[str, Any]],
) -> int:
    if not records:
        return 0
    texts = [f"{r['title']}\n\n{r['body']}" for r in records]
    embeddings = embed_texts(model_name, texts)
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    for i, r in enumerate(records):
        meta = build_metadata(r)
        sid = _chunk_id(str(r["title"]), str(r.get("body") or ""))
        ids.append(sid)
        docs.append(texts[i])
        metas.append(meta)
    store.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=docs,
        metadatas=metas,
    )
    return len(ids)
