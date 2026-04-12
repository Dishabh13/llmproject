"""
processing/stats.py
===================
Aggregate quality metrics across a processed batch.

Produces per-prompt and per-model summaries consumed by the
comparison dashboard (next team member's work).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from processing.normalizer import ProcessedResult, OutputType


def compute_summary(results: list[ProcessedResult]) -> dict[str, Any]:
    """Return a summary dict keyed by 'by_prompt', 'by_model', 'overall'."""
    if not results:
        return {}

    by_prompt: dict[str, list[ProcessedResult]] = defaultdict(list)
    by_model:  dict[str, list[ProcessedResult]] = defaultdict(list)
    for r in results:
        by_prompt[r.prompt].append(r)
        by_model[r.model].append(r)

    return {
        "total_records": len(results),
        "by_prompt":     {p: _stats(g) for p, g in by_prompt.items()},
        "by_model":      {m: _stats(g) for m, g in by_model.items()},
        "overall":       _stats(results),
    }


def _stats(group: list[ProcessedResult]) -> dict[str, Any]:
    n = len(group)
    structured   = sum(1 for r in group if r.output_type == OutputType.STRUCTURED)
    avg_quality  = sum(r.quality_score for r in group) / n

    # Field coverage rates
    field_total: dict[str, int] = defaultdict(int)
    field_hit:   dict[str, int] = defaultdict(int)
    for r in group:
        for k, v in r.field_coverage.items():
            field_total[k] += 1
            if v:
                field_hit[k] += 1
    field_rates = {
        k: round(field_hit[k] / field_total[k], 3)
        for k in field_total
    }

    # Average items extracted (structured records only)
    item_counts = [
        len(v)
        for r in group
        if isinstance(r.final_output, dict)
        for v in r.final_output.values()
        if isinstance(v, list)
    ]
    avg_items = round(sum(item_counts) / len(item_counts), 2) if item_counts else 0

    return {
        "count":                n,
        "structured_rate":      round(structured / n, 3),
        "avg_quality_score":    round(avg_quality, 4),
        "avg_items_extracted":  avg_items,
        "field_coverage_rates": field_rates,
    }
