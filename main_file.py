"""
main_file.py
============
Runs the model pipeline on file_inputs.json (created by config_panel.py
when the user uploads a document).  Produces results.json in the same
format as main.py so process_outputs.py and evaluation_grok.py work
unchanged.
"""
import json
import sys

from prompts.prompts import prompts
from models.model_router import run_model
from security_helper import load_config


def safe_parse(text: str) -> dict | list:
    try:
        return json.loads(text)
    except Exception:
        lines = text.split("\n")
        cleaned = [
            line.strip()
            for line in lines
            if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith("-"))
        ]
        return {"parsed_loose_output": cleaned}


def run_file_experiment() -> list:
    config = load_config()
    model_name = config["selected_model"]

    try:
        with open("file_inputs.json", "r") as f:
            inputs = json.load(f)
    except FileNotFoundError:
        print("ERROR: file_inputs.json not found. Upload a document first.")
        sys.exit(1)

    results = []

    for inp in inputs:
        for prmpt in prompts:
            final_prompt = prmpt["template"].replace("{{text}}", inp["text"])

            print(
                f"Running: Input {inp['input_id']} | "
                f"Prompt {prmpt['name']} | Model {model_name}"
            )

            try:
                output = run_model(final_prompt, inp["text"])
            except Exception as e:
                output = f"ERROR: {e}"

            results.append({
                "model":         model_name,
                "prompt":        prmpt["name"],
                "input_id":      inp["input_id"],
                "source_file":   inp.get("source_file", ""),
                "raw_output":    output,
                "parsed_output": safe_parse(output),
            })

    return results


if __name__ == "__main__":
    print("Running file-based experiment...")

    results = run_file_experiment()

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Done -- {len(results)} result(s) written to results.json")