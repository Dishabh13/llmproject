"""
processing/validator.py
=======================
JSON schema validation for structured outputs.

Validates against the three prompt families defined in the project:
  action_items | decisions | concerns

Uses jsonschema if installed; falls back to manual checks otherwise.
Returns a list of error strings (empty = valid).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMAS: dict[str, dict] = {
    "action_items": {
        "type": "object",
        "required": ["action_items"],
        "properties": {
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["action"],
                    "properties": {
                        "action":         {"type": "string", "minLength": 1},
                        "owner":          {"type": "string"},
                        "due_date":       {"type": "string"},
                        "evidence_quote": {"type": "string"},
                    },
                },
            }
        },
    },
    "decisions": {
        "type": "object",
        "required": ["decisions"],
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["decision"],
                    "properties": {
                        "decision":       {"type": "string", "minLength": 1},
                        "context":        {"type": "string"},
                        "evidence_quote": {"type": "string"},
                    },
                },
            }
        },
    },
    "concerns": {
        "type": "object",
        "required": ["concerns"],
        "properties": {
            "concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["issue"],
                    "properties": {
                        "issue":          {"type": "string", "minLength": 1},
                        "evidence_quote": {"type": "string"},
                    },
                },
            }
        },
    },
}


def _family(prompt_name: str) -> str | None:
    for f in _SCHEMAS:
        if f in prompt_name:
            return f
    return None


def validate_output(output: Any, prompt_name: str) -> list[str]:
    """
    Validate `output` against the schema for `prompt_name`.
    Returns [] if valid, or a list of human-readable error strings.
    """
    fam = _family(prompt_name)
    if not fam:
        return []  # no schema for this prompt family — skip

    schema = _SCHEMAS[fam]

    try:
        import jsonschema
        validator = jsonschema.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(output)]
    except ImportError:
        return _manual(output, fam)


def _manual(output: Any, family: str) -> list[str]:
    """Fallback validation without jsonschema."""
    if not isinstance(output, dict):
        return [f"Expected a JSON object, got {type(output).__name__}"]
    if family not in output:
        return [f"Missing required top-level key '{family}'"]
    items = output[family]
    if not isinstance(items, list):
        return [f"'{family}' must be an array"]
    required = _SCHEMAS[family]["properties"][family]["items"].get("required", [])
    errors: list[str] = []
    for i, item in enumerate(items):
        for key in required:
            if not str(item.get(key, "")).strip():
                errors.append(f"Item[{i}] missing or empty required field '{key}'")
    return errors
