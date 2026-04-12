"""
process_outputs.py
==================
Output + Metadata Processing (entry point)

Run AFTER main.py has produced results.json.

Usage
-----
    python process_outputs.py                          # defaults
    python process_outputs.py --input results.json --output processed_results.json
    python process_outputs.py --validate               # also run schema validation

What it does
------------
    1. Load  results.json           (raw output)
    2. Normalise every record       → detect type, parse JSON, clean text
    3. (Optional) Schema validate   → check field completeness
    4. Compute aggregate stats      → structured_rate, quality, coverage
    5. Write processed_results.json → atomically, never corrupted
    6. Print a readable summary     → for demo / presentation
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from processing.normalizer import normalize_batch
from processing.validator  import validate_output
from processing.stats      import compute_summary
from processing.writer     import write_json, load_json
import json
import re


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("process_outputs")

VERSION = "1.0.0"

def extract_json(text):
    try:
        # remove markdown
        text = re.sub(r"```json|```", "", text).strip()

        # find first JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())

        return {}

    except Exception as e:
        print("JSON Parse Error:", e)
        return {}
# ── CLI ───────────────────────────────────────────────────────────────────────

def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Normalise and enrich LLM evaluation results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input",    "-i", default="results.json",           help="Path to results.json")
    p.add_argument("--output",   "-o", default="processed_results.json", help="Output path")
    p.add_argument("--validate", "-v", action="store_true",              help="Run JSON schema validation")
    return p.parse_args()


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(input_path: Path, output_path: Path, validate: bool) -> dict:
    # 1. Load
    logger.info("Loading: %s", input_path)
    raw = load_json(input_path)
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in {input_path}")
    logger.info("Loaded %d records", len(raw))

    # 2. Normalise
    logger.info("Normalising …")
    processed = normalize_batch(raw)

    # 3. Validate (optional)
    if validate:
        logger.info("Running schema validation …")
        for r in processed:
            if isinstance(r.final_output, dict):
                errs = validate_output(r.final_output, r.prompt)
                r.metadata["schema_valid"]      = len(errs) == 0
                r.metadata["validation_errors"] = errs
                if errs:
                    logger.warning("input=%s prompt=%s → %d error(s)", r.input_id, r.prompt, len(errs))
            else:
                r.metadata["schema_valid"] = None  # N/A for unstructured

    # 4. Stats
    logger.info("Computing statistics …")
    summary = compute_summary(processed)

    # 5. Assemble
    payload = {
        "metadata": {
            "generated_at":          datetime.now(timezone.utc).isoformat(),
            "input_file":            str(input_path),
            "output_file":           str(output_path),
            "record_count":          len(processed),
            "schema_validation_run": validate,
            "processor_version":     VERSION,
            "branch":                "Apheksha",
        },
        "summary": summary,
        "results": [r.to_dict() for r in processed],
    }

    # 6. Write
    write_json(payload, output_path)
    logger.info("Written → %s", output_path)
    return payload


# ── Pretty summary ────────────────────────────────────────────────────────────

def _print(payload: dict) -> None:
    meta    = payload["metadata"]
    summary = payload["summary"]
    overall = summary.get("overall", {})
    sep     = "─" * 62

    print(f"\n{sep}")
    print("  LLM EVALUATION — OUTPUT PROCESSING COMPLETE")
    print(sep)
    print(f"  Records     : {meta['record_count']}")
    print(f"  Generated   : {meta['generated_at']}")
    print(f"  Output file : {meta['output_file']}")
    print(f"  Validation  : {'yes' if meta['schema_validation_run'] else 'no'}")
    print(sep)
    print("  OVERALL")
    print(f"  Structured rate  : {overall.get('structured_rate', 0):.0%}")
    print(f"  Avg quality      : {overall.get('avg_quality_score', 0):.3f} / 1.000")
    print(f"  Avg items/record : {overall.get('avg_items_extracted', 0):.1f}")

    by_prompt = summary.get("by_prompt", {})
    if by_prompt:
        print(f"\n  {'PROMPT':<32}  {'STRUCT':>6}  {'QUALITY':>8}")
        print(f"  {'─'*32}  {'─'*6}  {'─'*8}")
        for prompt, s in by_prompt.items():
            print(f"  {prompt:<32}  {s['structured_rate']:>5.0%}  {s['avg_quality_score']:>8.3f}")

    by_model = summary.get("by_model", {})
    if by_model:
        print(f"\n  {'MODEL':<20}  {'STRUCT':>6}  {'QUALITY':>8}")
        print(f"  {'─'*20}  {'─'*6}  {'─'*8}")
        for model, s in by_model.items():
            print(f"  {model:<20}  {s['structured_rate']:>5.0%}  {s['avg_quality_score']:>8.3f}")

    print(f"{sep}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = _args()
    inp  = Path(args.input)
    out  = Path(args.output)

    if not inp.exists():
        logger.error(
            "results.json not found at '%s'.\n"
            "  Run pipeline first:  python main.py",
            inp,
        )
        return 1

    try:
        payload = run(inp, out, args.validate)
    except (ValueError, OSError) as e:
        logger.error("Failed: %s", e)
        return 1

    _print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
