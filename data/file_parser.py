"""
file_parser.py
==============
Converts uploaded files (DOCX, PDF, TXT, JSON) into the standardised
internal JSON format used throughout the evaluation pipeline:

{
    "input_id": "case_001",
    "source_file": "meeting.pdf",
    "text": "Extracted text content ...",
    "metadata": {}
}
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any


# ── helpers ──────────────────────────────────────────────────────────────────

def _slug(filename: str) -> str:
    """Return a safe base-name without extension."""
    return re.sub(r"[^\w]", "_", Path(filename).stem)[:40]


def _make_record(input_id: str, source_file: str, text: str,
                 metadata: dict | None = None) -> dict:
    return {
        "input_id": input_id,
        "source_file": source_file,
        "text": text.strip(),
        "metadata": metadata or {},
    }


# ── format parsers ───────────────────────────────────────────────────────────

def _parse_txt(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _parse_json(path: str | Path) -> str:
    """
    Accepts:
      - a plain string  → returned as-is
      - a list of dicts → each item's text/content/body field is joined
      - a dict          → looks for 'text', 'content', 'body', 'transcript'
                          keys; falls back to pretty-printed JSON
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)

    if isinstance(data, str):
        return data

    TEXT_KEYS = ("text", "content", "body", "transcript", "message", "input")

    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict):
                for k in TEXT_KEYS:
                    if k in item:
                        parts.append(str(item[k]))
                        break
                else:
                    parts.append(json.dumps(item))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    if isinstance(data, dict):
        for k in TEXT_KEYS:
            if k in data:
                return str(data[k])
        return json.dumps(data, indent=2)

    return str(data)


def _parse_pdf(path: str | Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages)
    except ImportError:
        pass

    # fallback: pdfminer
    try:
        from pdfminer.high_level import extract_text as _extract
        return _extract(str(path))
    except ImportError:
        pass

    raise RuntimeError(
        "No PDF library found. Install pypdf or pdfminer.six:\n"
        "  pip install pypdf   OR   pip install pdfminer.six"
    )


def _parse_docx(path: str | Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        pass

    # fallback: pandoc CLI
    import subprocess
    result = subprocess.run(
        ["pandoc", str(path), "-t", "plain"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        return result.stdout

    raise RuntimeError(
        "python-docx not installed and pandoc not available.\n"
        "  pip install python-docx"
    )


# ── public API ────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx", ".json"}


def parse_file(path: str | Path) -> dict:
    """
    Parse a single file and return a standardised record dict.
    Raises ValueError for unsupported file types.
    """
    path = Path(path)
    ext = path.suffix.lower()
    filename = path.name

    if ext == ".txt":
        text = _parse_txt(path)
    elif ext == ".json":
        text = _parse_json(path)
    elif ext == ".pdf":
        text = _parse_pdf(path)
    elif ext in (".doc", ".docx"):
        text = _parse_docx(path)
    else:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    input_id = f"file_{_slug(filename)}_{uuid.uuid4().hex[:6]}"
    metadata = {
        "source_type": "file_upload",
        "original_extension": ext,
        "char_count": len(text),
        "word_count": len(text.split()),
    }

    return _make_record(input_id, filename, text, metadata)


def parse_file_to_inputs(path: str | Path) -> list[dict]:
    """
    Parse a file and return it as a list of input dicts
    compatible with the existing pipeline format used by main.py.

    Each dict has: input_id, text, source_file, metadata
    """
    record = parse_file(path)
    return [record]


def parse_bytes(file_bytes: bytes, filename: str) -> dict:
    """
    Parse raw bytes (e.g. from a FastAPI UploadFile) and return
    a standardised record dict.  Writes to a temp file then parses.
    """
    import tempfile

    ext = Path(filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        record = parse_file(tmp_path)
        record["source_file"] = filename          # restore real name
    finally:
        os.unlink(tmp_path)

    return record
