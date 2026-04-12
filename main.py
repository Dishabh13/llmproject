from data.inputs import inputs
from prompts.prompts import prompts
from models.model_router import run_model
from security_helper import load_config
import json

print("Total inputs loaded:", len(inputs))


def run_experiment():
    results = []

    config = load_config()
    model_name = config["selected_model"]

    for inp in inputs:
        for prmpt in prompts:

            final_prompt = prmpt["template"].replace("{{text}}", inp["text"])

            print(f"Running: Input {inp['input_id']} | Prompt {prmpt['name']} | Model {model_name}")

            try:
                output = run_model(final_prompt, inp["text"])

            except Exception as e:
                output = f"ERROR: {str(e)}"

            result = {
                "model": model_name,
                "prompt": prmpt["name"],
                "input_id": inp["input_id"],
                "raw_output": output,
                "parsed_output": safe_parse(output)
            }

            results.append(result)

    return results


def safe_parse(text):
    if not text:
        return {"error": "No output returned from model"}
    try:
        return json.loads(text)
    except Exception:
        lines = str(text).split("\n")
        cleaned = [line.strip() for line in lines if line.strip() and line[0].isdigit()]
        return {
            "parsed_loose_output": cleaned
        }


if __name__ == "__main__":
    print("Running experiment...")

    results = run_experiment()

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n--- RESULTS ---\n")
    for r in results:
        print(r)