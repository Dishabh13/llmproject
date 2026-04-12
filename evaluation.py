from __future__ import annotations

import os
import time
from flask import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# -------------------------------
# LOAD CONFIG
# -------------------------------
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)


config = load_config()


# -------------------------------
# LOAD WEIGHTS (RUBRIC)
# -------------------------------
def get_weights():
    weights = config.get("weights", {})

    defaults = {
        "accuracy": 25,
        "relevance": 15,
        "completeness": 25,
        "consistency": 10,
        "usefulness": 15
    }

    for k, v in defaults.items():
        weights.setdefault(k, v)

    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


# -------------------------------
# LOAD MODEL
# -------------------------------
try:
    model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as e:
    print(f"[MODEL LOAD ERROR]: {e}")
    model = None


# -------------------------------
# SAFE ENCODE
# -------------------------------
def safe_encode(text):
    try:
        if model is None:
            return None

        if text is None:
            return None

        if not isinstance(text, str):
            text = str(text)

        text = text.strip()
        if len(text) == 0:
            return None

        return model.encode(text)

    except Exception as e:
        print(f"[safe_encode ERROR]: {e}")
        return None


# -------------------------------
# SAFE SIMILARITY
# -------------------------------
def safe_similarity(vec1, vec2):
    try:
        if vec1 is None or vec2 is None:
            return 0.0

        sim = cosine_similarity([vec1], [vec2])[0][0]

        if np.isnan(sim):
            return 0.0

        return float(sim)

    except Exception as e:
        print(f"[similarity ERROR]: {e}")
        return 0.0


# -------------------------------
# METRICS (IMPROVED VERSION)
# -------------------------------
def compute_metrics(prompt, output, reference):

    print("\n⚠️ Running NEW reference-free evaluation")

    # -------------------------
    # STRUCTURE SCORE
    # -------------------------
    if isinstance(output, str) and output.strip().startswith("{"):
        structure = 1.0   # strict JSON
    else:
        structure = 0.5   # loose text

    # -------------------------
    # RELEVANCE (BOOSTED)
    # -------------------------
    emb_prompt = safe_encode(prompt)
    emb_output = safe_encode(output)

    raw_rel = safe_similarity(emb_prompt, emb_output)

    # Boost relevance
    relevance = min(1.0, 0.5 * raw_rel + 0.5)

    # -------------------------
    # CONSISTENCY
    # -------------------------
    try:
        sentences = [s.strip() for s in str(output).split('.') if s.strip()]
        if len(sentences) > 1 and model is not None:
            sent_emb = model.encode(sentences)
            sim_matrix = cosine_similarity(sent_emb)
            consistency = float(np.mean(sim_matrix))
        else:
            consistency = relevance
    except:
        consistency = relevance

    # -------------------------
    # COMPLETENESS (IMPROVED)
    # -------------------------
    word_count = len(str(output).split())

    if word_count > 120:
        completeness = 1.0
    elif word_count > 60:
        completeness = 0.8
    elif word_count > 20:
        completeness = 0.6
    else:
        completeness = 0.4

    # -------------------------
    # ACCURACY (NEW LOGIC)
    # -------------------------
    accuracy = (relevance + structure) / 2

    # -------------------------
    # USEFULNESS (STRONGER)
    # -------------------------
    values = [accuracy, relevance, completeness, consistency, structure]
    usefulness = float(np.mean(values))

    return {
        "accuracy": accuracy,
        "relevance": relevance,
        "completeness": completeness,
        "consistency": consistency,
        "usefulness": usefulness
    }


# -------------------------------
# FINAL SCORE
# -------------------------------
def compute_final_score(metrics, weights):

    relevant_keys = ["accuracy", "relevance", "completeness", "consistency", "usefulness"]

    score = 0.0
    weight_sum = 0.0

    for key in relevant_keys:
        value = metrics.get(key)

        if value is not None and key in weights:
            score += value * weights[key]
            weight_sum += weights[key]

    if weight_sum == 0:
        return None

    return score / weight_sum


# -------------------------------
# MAIN PIPELINE
# -------------------------------
def run_evaluation():

    weights = get_weights()

    with open("processed_results.json", "r") as f:
        data = json.load(f)

    results_list = data if isinstance(data, list) else data.get("results", [])

    final_report = []

    print("\n🔄 Running evaluation...\n")

    for i, entry in enumerate(results_list):

        print(f"[{i+1}/{len(results_list)}] Evaluating...")

        prompt_text = str(entry.get("prompt", ""))

        output_data = entry.get("final_output", "")
        output_text = json.dumps(output_data) if isinstance(output_data, dict) else str(output_data)

        reference = entry.get("expected_output", "")

        print("\n--- DEBUG ENTRY ---")
        print("PROMPT:", prompt_text)
        print("OUTPUT:", output_text[:200])
        print("REFERENCE:", reference)

        metrics = compute_metrics(prompt_text, output_text, reference)

        final_score = compute_final_score(metrics, weights)

        final_report.append({
            "input_id": entry.get("input_id"),
            "prompt": prompt_text,
            "final_score": final_score,
            "metrics": metrics,
            "final_output": entry.get("final_output", {})
        })

        time.sleep(0.05)

    with open("scored_results.json", "w") as f:
        json.dump(final_report, f, indent=2)

    print("\n✅ Evaluation complete!")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    run_evaluation()