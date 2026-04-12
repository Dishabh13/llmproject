import json
import os
import time
import re
import sys

# Fix the Python path to allow imports from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from groq import Groq
from security_helper import get_api_key, load_config

# -------------------------------
# LOAD API KEY
# -------------------------------

GROQ_API_KEY = get_api_key("groq")

if not GROQ_API_KEY:
    print("ERROR: GROQ_API_KEY not set!")
    exit()

groq_client = Groq(api_key=GROQ_API_KEY)

# -------------------------------
# LOAD WEIGHTS
# -------------------------------
def get_weights():
    config = load_config() # Use the imported load_config
    weights = config.get("weights", {})

    normalized = {k: v / 100 for k, v in weights.items()}

    defaults = {
        "accuracy": 0.2,
        "relevance": 0.1,
        "completeness": 0.2,
        "consistency": 0.1,
        "usefulness": 0.1,
        "structure": 0.1,
        "conciseness": 0.1,
        "latency": 0.05,
        "cost": 0.05
    }

    for k, v in defaults.items():
        normalized.setdefault(k, v)

    return normalized

# -------------------------------
# LLM AS JUDGE
# -------------------------------
def get_groq_scores(prompt, output):
    try:
        eval_prompt = f"""
You are an evaluator. Score the output from 1-10 for:

1. Accuracy (correctness of information)
2. Relevance (answers the question properly)
3. Completeness (covers all important points)
4. Consistency (no contradictions)
5. Usefulness (practical and usable output)

Return ONLY JSON:
{{
  "accuracy": number,
  "relevance": number,
  "completeness": number,
  "consistency": number,
  "usefulness": number
}}

Prompt:
{prompt}

Output:
{output}
"""

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Correct, active model from the definitive list.
            messages=[
                {"role": "system", "content": "You are a strict evaluator."},
                {"role": "user", "content": eval_prompt}
            ],
            temperature=0
        )

        text = response.choices[0].message.content.strip()
        text = re.sub(r"```json|```", "", text).strip()

        try:
            scores = json.loads(text)

            scores.setdefault("accuracy", 5)
            scores.setdefault("relevance", 5)
            scores.setdefault("completeness", 5)
            scores.setdefault("consistency", 5)
            scores.setdefault("usefulness", 5)

        except:
            print("WARNING: Invalid JSON from Groq, using fallback scores")
            scores = {
                "accuracy": 5,
                "relevance": 5,
                "completeness": 5,
                "consistency": 5,
                "usefulness": 5
            }

        estimated_cost = len(prompt.split()) + len(output.split())
        estimated_cost = estimated_cost / 100000

        return scores, estimated_cost

    except Exception as e:
        print(f"WARNING: Groq API failed: {e}")
        return {
            "accuracy": 5,
            "relevance": 5,
            "completeness": 5,
            "consistency": 5,
            "usefulness": 5
        }, 0.0


# -------------------------------
# HEURISTICS
# -------------------------------
def calculate_heuristics(entry, output_text):

    if entry.get("output_type") == "structured":
        structure_score = 10
    else:
        structure_score = 3

    latency = entry.get("metadata", {}).get("latency_ms", 3000)

    if latency < 800:
        latency_score = 10
    elif latency < 1500:
        latency_score = 7
    else:
        latency_score = 4

    word_count = len(output_text.split())

    if word_count < 100:
        conciseness_score = 10
    elif word_count < 300:
        conciseness_score = 7
    else:
        conciseness_score = 4

    return structure_score, latency_score, conciseness_score


# -------------------------------
# MAIN PIPELINE
# -------------------------------
def run_evaluation():

    weights = get_weights()

    try:
        with open("processed_results.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("ERROR: processed_results.json not found!")
        return

    results_list = data if isinstance(data, list) else data.get("results", [])

    final_report = []
    total_spend = 0.0

    print("\nRunning evaluation...\n")

    for i, entry in enumerate(results_list):

        print(f"[{i+1}/{len(results_list)}] Evaluating...")

        prompt_text = entry.get("prompt", "")
        input_id = entry.get("input_id", "unknown")

        output_data = entry.get("final_output", "")
        if isinstance(output_data, dict):
            output_text = json.dumps(output_data)
        else:
            output_text = str(output_data)

        content_scores, call_cost = get_groq_scores(prompt_text, output_text)
        total_spend += call_cost

        structure_score, latency_score, conciseness_score = calculate_heuristics(entry, output_text)

        if call_cost < 0.0005:
            cost_score = 10
        elif call_cost < 0.002:
            cost_score = 7
        else:
            cost_score = 4

        final_score = (
            content_scores.get("accuracy", 5) * weights["accuracy"] +
            content_scores.get("relevance", 5) * weights["relevance"] +
            content_scores.get("completeness", 5) * weights["completeness"] +
            content_scores.get("consistency", 5) * weights["consistency"] +
            content_scores.get("usefulness", 5) * weights["usefulness"] +
            structure_score * weights["structure"] +
            conciseness_score * weights["conciseness"] +
            latency_score * weights["latency"] +
            cost_score * weights["cost"]
        )

        final_report.append({
            "input_id": input_id,
            "prompt": prompt_text,
            "final_score": round(final_score, 2),
            "metrics": {
                **content_scores,
                "structure": structure_score,
                "conciseness": conciseness_score,
                "latency_score": latency_score,
                "cost_score": cost_score,
                "eval_cost_usd": round(call_cost, 6)
            }
        })

        time.sleep(1)

    with open("scored_results.json", "w") as f:
        json.dump(final_report, f, indent=2)

    print("\nEvaluation complete!")
    print(f"Total Estimated Cost: ${round(total_spend, 6)}")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_evaluation()