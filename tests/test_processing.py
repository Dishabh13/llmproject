"""
tests/test_processing.py
========================
Unit tests for processing layer.

Run:
    pytest tests/ -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from processing.normalizer import (
    OutputType, ProcessingStatus,
    normalize_result, normalize_batch,
)
from processing.validator import validate_output
from processing.stats     import compute_summary
from processing.writer    import write_json, load_json


# ── Fixtures ──────────────────────────────────────────────────────────────────

STRUCTURED = {
    "model": "groq", "prompt": "action_items_strict", "input_id": "1",
    "raw_output": json.dumps({
        "action_items": [{
            "action": "Prepare budget report",
            "owner": "John",
            "due_date": "Friday",
            "evidence_quote": "John will prepare the budget report by Friday",
        }]
    }),
    "parsed_output": {}, "latency_ms": 1200,
}

UNSTRUCTURED = {
    "model": "groq", "prompt": "action_items_loose", "input_id": "2",
    "raw_output": "1. Prepare the budget\n2. Fix the bug",
    "parsed_output": {"parsed_loose_output": ["1. Prepare the budget"]},
}

FENCED = {
    "model": "groq", "prompt": "decisions_strict", "input_id": "1",
    "raw_output": "```json\n" + json.dumps({
        "decisions": [{
            "decision": "Launch postponed",
            "context": "Resource constraints",
            "evidence_quote": "launch will be postponed",
        }]
    }) + "\n```",
    "parsed_output": {},
}

PROSE_PREFIX = {
    "model": "groq", "prompt": "action_items_strict", "input_id": "3",
    "raw_output": 'Here are the action items:\n' + json.dumps({
        "action_items": [{"action": "Send report", "owner": "Alice", "due_date": "", "evidence_quote": "Alice will send"}]
    }),
    "parsed_output": {},
}


# ── normalizer ────────────────────────────────────────────────────────────────

class TestNormalizeResult:

    def test_structured_output_detected(self):
        r = normalize_result(STRUCTURED)
        assert r.output_type == OutputType.STRUCTURED
        assert isinstance(r.final_output, dict)
        assert "action_items" in r.final_output

    def test_unstructured_output_detected(self):
        r = normalize_result(UNSTRUCTURED)
        assert r.output_type == OutputType.UNSTRUCTURED
        assert isinstance(r.final_output, str)

    def test_code_fence_stripped(self):
        r = normalize_result(FENCED)
        assert r.output_type == OutputType.STRUCTURED
        assert "decisions" in r.final_output

    def test_prose_prefix_handled(self):
        r = normalize_result(PROSE_PREFIX)
        assert r.output_type == OutputType.STRUCTURED

    def test_raw_output_always_preserved(self):
        r = normalize_result(STRUCTURED)
        assert r.raw_output == STRUCTURED["raw_output"]

    def test_latency_in_metadata(self):
        r = normalize_result(STRUCTURED)
        assert r.metadata["latency_ms"] == 1200

    def test_quality_score_bounded(self):
        for rec in [STRUCTURED, UNSTRUCTURED, FENCED]:
            r = normalize_result(rec)
            assert 0.0 <= r.quality_score <= 1.0

    def test_structured_quality_above_half(self):
        r = normalize_result(STRUCTURED)
        assert r.quality_score > 0.5

    def test_unstructured_quality_low(self):
        r = normalize_result(UNSTRUCTURED)
        assert r.quality_score < 0.5

    def test_missing_keys_graceful(self):
        r = normalize_result({})
        assert r.model    == "unknown"
        assert r.prompt   == "unknown"
        assert r.input_id == "unknown"

    def test_error_string_unstructured(self):
        r = normalize_result({"model": "groq", "prompt": "p", "input_id": "e",
                              "raw_output": "ERROR: timeout", "parsed_output": {}})
        assert r.output_type == OutputType.UNSTRUCTURED
        assert "ERROR" in r.final_output

    def test_field_coverage_populated(self):
        r = normalize_result(STRUCTURED)
        assert "action" in r.field_coverage


class TestNormalizeBatch:

    def test_all_records_processed(self):
        assert len(normalize_batch([STRUCTURED, UNSTRUCTURED, FENCED])) == 3

    def test_none_record_does_not_crash_batch(self):
        results = normalize_batch([STRUCTURED, None, UNSTRUCTURED])  # type: ignore
        assert len(results) == 3
        assert results[1].metadata["processing_status"] == ProcessingStatus.ERROR.value

    def test_empty_list(self):
        assert normalize_batch([]) == []


# ── validator ─────────────────────────────────────────────────────────────────

class TestValidator:

    def test_valid_action_items(self):
        data = {"action_items": [{"action": "Do X", "owner": "Y", "due_date": "Z", "evidence_quote": "W"}]}
        assert validate_output(data, "action_items_strict") == []

    def test_missing_action_field(self):
        data = {"action_items": [{"owner": "John"}]}
        assert len(validate_output(data, "action_items_strict")) > 0

    def test_empty_action_invalid(self):
        data = {"action_items": [{"action": ""}]}
        assert len(validate_output(data, "action_items_strict")) > 0

    def test_valid_decisions(self):
        data = {"decisions": [{"decision": "Launch postponed", "context": "x", "evidence_quote": "y"}]}
        assert validate_output(data, "decisions_strict") == []

    def test_unknown_prompt_skipped(self):
        assert validate_output({"foo": "bar"}, "unknown_xyz") == []

    def test_missing_top_level_key(self):
        assert len(validate_output({}, "action_items_strict")) > 0


# ── stats ─────────────────────────────────────────────────────────────────────

class TestStats:

    def test_empty_list(self):
        assert compute_summary([]) == {}

    def test_structured_rate_50_percent(self):
        results = normalize_batch([STRUCTURED, UNSTRUCTURED])
        s = compute_summary(results)
        assert s["overall"]["structured_rate"] == pytest.approx(0.5, abs=0.01)

    def test_keys_present(self):
        results = normalize_batch([STRUCTURED, UNSTRUCTURED])
        s = compute_summary(results)
        assert {"by_prompt", "by_model", "overall"} <= s.keys()

    def test_by_prompt_contains_prompt_names(self):
        results = normalize_batch([STRUCTURED, UNSTRUCTURED])
        s = compute_summary(results)
        assert "action_items_strict" in s["by_prompt"]
        assert "action_items_loose"  in s["by_prompt"]


# ── writer ────────────────────────────────────────────────────────────────────

class TestWriter:

    def test_round_trip(self, tmp_path):
        data = {"hello": "world", "nums": [1, 2, 3]}
        p    = tmp_path / "out.json"
        write_json(data, p)
        assert load_json(p) == data

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "out.json"
        write_json({"ok": True}, p)
        assert p.exists()

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_json(tmp_path / "nope.json")

    def test_utf8_roundtrip(self, tmp_path):
        data = {"emoji": "🎉", "jp": "日本語"}
        p    = tmp_path / "utf8.json"
        write_json(data, p)
        assert load_json(p) == data

    def test_atomic_write_overwrites_safely(self, tmp_path):
        """Second write should fully replace the first — no partial state."""
        p = tmp_path / "safe.json"
        write_json({"v": 1}, p)
        write_json({"v": 2}, p)
        assert load_json(p) == {"v": 2}
