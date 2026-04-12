from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────

class OutputType(str, Enum):
    STRUCTURED   = "structured"
    UNSTRUCTURED = "unstructured"
    PARTIAL      = "partial"


class ProcessingStatus(str, Enum):
    PARSED  = "parsed"
    CLEANED = "cleaned"
    RAW     = "raw"
    ERROR   = "error"


# ── Expected fields per prompt family ────────────────────────────────────────

_EXPECTED_KEYS: dict[str, list[str]] = {
    "action_items": ["action", "owner", "due_date", "evidence_quote"],
    "decisions":    ["decision", "context", "evidence_quote"],
    "concerns":     ["issue", "evidence_quote"],
}

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


# ── Data class ───────────────────────────────────────────────────────────────

@dataclass
class ProcessedResult:
    model:          str
    prompt:         str
    input_id:       str
    output_type:    OutputType
    final_output:   Any
    raw_output:     str
    metadata:       dict[str, Any] = field(default_factory=dict)
    quality_score:  float = 0.0
    field_coverage: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model":          self.model,
            "prompt":         self.prompt,
            "input_id":       self.input_id,
            "output_type":    self.output_type.value,
            "final_output":   self.final_output,
            "raw_output":     self.raw_output,
            "metadata":       self.metadata,
            "quality_score":  round(self.quality_score, 4),
            "field_coverage": self.field_coverage,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    m = _FENCE_RE.search(text)
    return m.group(1).strip() if m else text.strip()


def _try_parse_json(text: str) -> tuple[Any | None, str]:
    cleaned = _strip_fences(text)

    try:
        return json.loads(cleaned), "direct"
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group()), "extracted_object"
        except json.JSONDecodeError:
            pass

    m = re.search(r"\[[\s\S]*\]", cleaned)
    if m:
        try:
            return json.loads(m.group()), "extracted_array"
        except json.JSONDecodeError:
            pass

    return None, "failed"


def _clean_text(text: str) -> str:
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", text)
    lines = [ln.strip() for ln in text.splitlines()]

    out: list[str] = []
    blanks = 0
    for ln in lines:
        if ln == "":
            blanks += 1
            if blanks <= 2:
                out.append(ln)
        else:
            blanks = 0
            out.append(ln)

    return "\n".join(out).strip()


def _prompt_family(prompt_name: str) -> str | None:
    for family in _EXPECTED_KEYS:
        if family in prompt_name:
            return family
    return None


# ✅ FIXED QUALITY FUNCTION (handles list + dict)
def _quality(parsed: Any, prompt_name: str, otype: OutputType) -> tuple[float, dict[str, bool]]:
    if otype == OutputType.UNSTRUCTURED:
        return 0.1, {}

    family = _prompt_family(prompt_name)

    # ✅ FIX: handle list input
    if isinstance(parsed, list) and family:
        parsed = {family: parsed}

    if not family or not isinstance(parsed, dict):
        return 0.5, {}

    expected = _EXPECTED_KEYS[family]
    items: list[dict] = parsed.get(family, [])

    if not items:
        return 0.3, {k: False for k in expected}

    total_possible = len(expected) * len(items)
    total_filled   = 0
    coverage: dict[str, bool] = {}

    for key in expected:
        filled = sum(
            1 for item in items
            if isinstance(item, dict) and str(item.get(key, "")).strip()
        )
        coverage[key]  = filled == len(items)
        total_filled  += filled

    ratio = total_filled / total_possible if total_possible else 0.0
    return 0.5 + ratio * 0.5, coverage


# ── Main Normalization ────────────────────────────────────────────────────────

def normalize_result(raw: dict) -> ProcessedResult:
    model      = raw.get("model",      "unknown")
    prompt     = raw.get("prompt",     "unknown")
    input_id   = raw.get("input_id",   "unknown")
    raw_output = raw.get("raw_output", "")

    notes: list[str] = []

    parsed_obj, method = _try_parse_json(raw_output)

    if parsed_obj is not None:
        family = _prompt_family(prompt)

        # ✅ CRITICAL FIX: wrap list into expected structure
        if isinstance(parsed_obj, list) and family:
            parsed_obj = {family: parsed_obj}

        output_type  = OutputType.STRUCTURED
        final_output = parsed_obj
        status       = ProcessingStatus.PARSED
        notes.append(f"JSON parsed (method={method})")

    else:
        existing = raw.get("parsed_output")

        if (
            isinstance(existing, dict)
            and "parsed_loose_output" not in existing
            and existing
        ):
            output_type  = OutputType.PARTIAL
            final_output = existing
            status       = ProcessingStatus.PARSED
            method       = "upstream_safe_parse"
            notes.append("Used upstream parsed_output; original JSON unrecoverable")

        else:
            cleaned      = _clean_text(raw_output)
            output_type  = OutputType.UNSTRUCTURED
            final_output = cleaned
            status       = ProcessingStatus.CLEANED if cleaned != raw_output else ProcessingStatus.RAW
            method       = "none"
            notes.append("Unstructured text; light cleanup applied")

    quality_score, field_coverage = _quality(final_output, prompt, output_type)

    metadata: dict[str, Any] = {
        "processing_status": status.value,
        "parse_method":      method,
        "notes":             "; ".join(notes),
    }

    for opt in ("latency_ms", "token_usage", "estimated_cost_usd"):
        if opt in raw:
            metadata[opt] = raw[opt]

    return ProcessedResult(
        model=model,
        prompt=prompt,
        input_id=input_id,
        output_type=output_type,
        final_output=final_output,
        raw_output=raw_output,
        metadata=metadata,
        quality_score=quality_score,
        field_coverage=field_coverage,
    )


def normalize_batch(records: list[dict]) -> list[ProcessedResult]:
    results: list[ProcessedResult] = []

    for i, rec in enumerate(records):
        try:
            if not isinstance(rec, dict):
                raise TypeError(f"Expected dict, got {type(rec).__name__}")

            results.append(normalize_result(rec))

        except Exception as exc:
            logger.error("Record %d failed normalisation: %s", i, exc)

            safe = rec if isinstance(rec, dict) else {}

            results.append(ProcessedResult(
                model=safe.get("model", "unknown"),
                prompt=safe.get("prompt", "unknown"),
                input_id=safe.get("input_id", "unknown"),
                output_type=OutputType.UNSTRUCTURED,
                final_output=str(safe.get("raw_output", "")),
                raw_output=str(safe.get("raw_output", "")),
                metadata={
                    "processing_status": ProcessingStatus.ERROR.value,
                    "parse_method": "none",
                    "notes": f"Normalisation error: {exc}",
                },
            ))

    return results