import json
import os
import time
from google import genai
from google.genai import types

# -------------------------------
# CONFIG
# -------------------------------
PRICE_INPUT_1M = 0.10
PRICE_OUTPUT_1M = 0.40
MODEL_ID = "gemini-2.5-flash"

# API_KEY = os.environ.get("GOOGLE_API_KEY")
API_KEY = "AIzaSyAosG_f2QwGk21Nf7W4NR19hjrj5LtnsHc"
if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY not set!")
    exit()

client = genai.Client(api_key=API_KEY)

# -------------------------------
# USER WEIGHTS
# -------------------------------
def get_user_weights():
    metrics = ["accuracy", "relevance", "completeness", "consistency", "latency", "cost"]
    
    print("\n--- Configure Evaluation Weights (Total must = 1.0) ---")
    
    while True:
        weights = {}
        total = 0.0

        try:
            for m in metrics:
                val = float(input(f"Weight for {m.capitalize()}: "))
                weights[m] = val
                total += val

            if abs(total - 1.0) < 0.001:
                return weights
            else:
                print(f"❌ Total is {total}. Must be 1.0. Try again.\n")

        except:
            print("❌ Invalid input. Enter numeric values.\n")

# -------------------------------
# LLM AS JUDGE
# -------------------------------
def get_gemini_scores(prompt_text, model_output):
    
    eval_prompt = f"""
    Evaluate the following AI output.

    Give scores from 1 to 10 for:
    - accuracy
    - relevance
    - completeness
    - consistency

    Prompt:
    {prompt_text}

    Output:
    {model_output}

    Return ONLY valid JSON like:
    {{
      "accuracy": 8,
      "relevance": 7,
      "completeness": 9,
      "consistency": 8
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=eval_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        usage = response.usage_metadata

        cost = (
            (usage.prompt_token_count / 1_000_000) * PRICE_INPUT_1M +
            (usage.candidates_token_count / 1_000_000) * PRICE_OUTPUT_1M
        )

        # SAFE JSON PARSE
        try:
            parsed = json.loads(response.text)
        except:
            print("⚠️ Invalid JSON from Gemini → using default scores")
            parsed = {
                "accuracy": 5,
                "relevance": 5,
                "completeness": 5,
                "consistency": 5
            }

        return parsed, cost

    except Exception as e:
        print(f"⚠️ Gemini API failed: {e}")

        # fallback scores
        return {
            "accuracy": 5,
            "relevance": 5,
            "completeness": 5,
            "consistency": 5
        }, 0.0

# -------------------------------
# HEURISTIC SCORES
# -------------------------------
def calculate_heuristics(entry):

    # Structure
    if entry.get("output_type") == "structured":
        structure_score = 10
    else:
        structure_score = 2

    # Latency
    latency = entry.get("metadata", {}).get("latency_ms", 3000)

    if latency < 800:
        latency_score = 10
    elif latency < 1500:
        latency_score = 7
    else:
        latency_score = 3

    return structure_score, latency_score

# -------------------------------
# MAIN PIPELINE
# -------------------------------
def run_evaluation():

    weights = get_user_weights()

    # Load file
    try:
        with open("processed_results.json", "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ processed_results.json not found!")
        return

    # Handle both formats (list OR dict)
    results_list = data if isinstance(data, list) else data.get("results", [])

    final_report = []
    total_spend = 0.0

    print(f"\n🔄 Running evaluation using {MODEL_ID}...\n")

    for i, entry in enumerate(results_list):

        print(f"[{i+1}/{len(results_list)}] Evaluating...")

        prompt_text = entry.get("prompt", "")
        input_id = entry.get("input_id", "unknown")

        # Convert output to string safely
        output_data = entry.get("final_output", "")
        if isinstance(output_data, dict):
            output_text = json.dumps(output_data)
        else:
            output_text = str(output_data)

        # LLM scoring
        content_scores, call_cost = get_gemini_scores(prompt_text, output_text)
        total_spend += call_cost

        # Heuristic scoring
        structure_score, latency_score = calculate_heuristics(entry)

        # Cost scoring
        if call_cost < 0.0001:
            cost_score = 10
        elif call_cost < 0.001:
            cost_score = 7
        else:
            cost_score = 3

        # FINAL WEIGHTED SCORE
        final_score = (
            content_scores.get("accuracy", 5) * weights["accuracy"] +
            content_scores.get("relevance", 5) * weights["relevance"] +
            content_scores.get("completeness", 5) * weights["completeness"] +
            content_scores.get("consistency", 5) * weights["consistency"] +
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
                "latency_score": latency_score,
                "cost_score": cost_score,
                "eval_cost_usd": round(call_cost, 6)
            }
        })

        # Avoid rate limits
        if i < len(results_list) - 1:
            time.sleep(25)

    # Save results
    with open("scored_results.json", "w") as f:
        json.dump(final_report, f, indent=2)

    print("\n✅ Evaluation complete!")
    print(f"💰 Total API Cost: ${round(total_spend, 6)}")
    print("📁 Output saved to scored_results.json")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_evaluation()