from pathlib import Path
import json
import pandas as pd
import plotly.express as px
from collections import defaultdict  

def safe_write_image(fig, png_path):
    """
    Try to export a Plotly figure as a PNG via kaleido.
    If kaleido hangs or fails (a known threading issue on some platforms),
    fall back to an interactive HTML file so the report is never blocked.
    """
    try:
        fig.write_image(png_path)
    except Exception as e:
        print(f"WARNING: PNG export failed ({e}). Saving as HTML instead.")
        html_path = str(png_path).replace(".png", ".html")
        fig.write_html(html_path)


SCORED_FILE = Path("scored_results.json")
PROCESSED_FILE = Path("processed_results.json")
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)

if not SCORED_FILE.exists():
    raise FileNotFoundError("scored_results.json not found")

if not PROCESSED_FILE.exists():
    raise FileNotFoundError("processed_results.json not found")

with open(SCORED_FILE, "r", encoding="utf-8") as f:
    scored_data = json.load(f)

with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
    processed_data = json.load(f)

scored_records = scored_data["results"] if isinstance(scored_data, dict) and "results" in scored_data else scored_data
processed_records = processed_data["results"] if isinstance(processed_data, dict) and "results" in processed_data else processed_data

score_rows = []
for r in scored_records:
    m = r.get("metrics", {}) or {}
    score_rows.append({
        "input_id": r.get("input_id", ""),
        "prompt": r.get("prompt", ""),
        "final_score": float(r.get("final_score", 0)),
        "accuracy": float(m.get("accuracy", 0)),
        "relevance": float(m.get("relevance", 0)),
        "completeness": float(m.get("completeness", 0)),
        "consistency": float(m.get("consistency", 0)),
        "usefulness": float(m.get("usefulness", 0)),
        "structure": float(m.get("structure", 0)),
        "conciseness": float(m.get("conciseness", 0)),
        "latency_score": float(m.get("latency_score", 0)),
        "cost_score": float(m.get("cost_score", 0)),
        "eval_cost_usd": float(m.get("eval_cost_usd", 0)),
    })

proc_rows = []
for r in processed_records:
    meta = r.get("metadata", {}) or {}
    proc_rows.append({
        "input_id": r.get("input_id", ""),
        "prompt": r.get("prompt", ""),
        "model": r.get("model", ""),
        "output_type": r.get("output_type", ""),
        "quality_score": float(r.get("quality_score", 0)),
        "structured": 1 if r.get("output_type") == "structured" else 0,
        "latency_ms": meta.get("latency_ms", None),
        "schema_valid": meta.get("schema_valid", None),
        "final_output": r.get("final_output", ""),
    })

df_score = pd.DataFrame(score_rows)
df_proc = pd.DataFrame(proc_rows)

agg = df_score.groupby("prompt").agg(
    runs=("input_id", "count"),
    avg_final_score=("final_score", "mean"),
    avg_accuracy=("accuracy", "mean"),
    avg_relevance=("relevance", "mean"),
    avg_completeness=("completeness", "mean"),
    avg_consistency=("consistency", "mean"),
    avg_usefulness=("usefulness", "mean"),
    avg_structure=("structure", "mean"),
    avg_conciseness=("conciseness", "mean"),
    avg_latency_score=("latency_score", "mean"),
    avg_cost_score=("cost_score", "mean"),
    avg_eval_cost_usd=("eval_cost_usd", "mean"),
    total_eval_cost_usd=("eval_cost_usd", "sum"),
).reset_index().sort_values("avg_final_score", ascending=False)

proc_agg = df_proc.groupby("prompt").agg(
    structured_rate=("structured", "mean"),
    avg_quality_score=("quality_score", "mean"),
    avg_latency_ms=("latency_ms", "mean"),
).reset_index()

report = agg.merge(proc_agg, on="prompt", how="left")
report["structured_rate"] = report["structured_rate"].fillna(0)
report["rank"] = range(1, len(report) + 1)

top_row = report.iloc[0]

weak_cols = [
    "avg_accuracy",
    "avg_relevance",
    "avg_completeness",
    "avg_consistency",
    "avg_usefulness",
    "avg_structure",
    "avg_conciseness",
    "avg_latency_score",
    "avg_cost_score",
]
weak_map = {
    "avg_accuracy": "correctness",
    "avg_relevance": "relevance",
    "avg_completeness": "completeness",
    "avg_consistency": "consistency",
    "avg_usefulness": "usefulness",
    "avg_structure": "structure",
    "avg_conciseness": "conciseness",
    "avg_latency_score": "latency",
    "avg_cost_score": "cost",
}
weak_metric = top_row[weak_cols].idxmin()

summary = {
    "top_prompt": top_row["prompt"],
    "top_score": round(float(top_row["avg_final_score"]), 3),
    "key_win_reason": f"Highest average score ({top_row['avg_final_score']:.2f}) with structured rate {top_row['structured_rate']:.0%}.",
    "biggest_weakness": f"Main weakness is {weak_map.get(weak_metric, 'quality')}.",
    "recommendation": f"Ship {top_row['prompt']} and improve {weak_map.get(weak_metric, 'quality')} next.",
}

ranked_download = report[[
    "rank",
    "prompt",
    "runs",
    "avg_final_score",
    "avg_accuracy",
    "avg_relevance",
    "avg_completeness",
    "avg_consistency",
    "avg_usefulness",
    "avg_structure",
    "avg_conciseness",
    "avg_latency_score",
    "avg_cost_score",
    "structured_rate",
    "avg_quality_score",
    "avg_eval_cost_usd",
    "total_eval_cost_usd",
    "avg_latency_ms",
]].round(4)

ranked_download.to_csv(OUT_DIR / "ranked_comparison_table.csv", index=False)

with open(OUT_DIR / "executive_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

rubric_data = pd.DataFrame([
    {"Criterion": "Correctness", "Description": "Accuracy of extracted information", "Weight": "35%"},
    {"Criterion": "Completeness", "Description": "Captured all relevant items", "Weight": "25%"},
    {"Criterion": "Structure", "Description": "Followed output format", "Weight": "20%"},
    {"Criterion": "Conciseness", "Description": "Clarity and brevity", "Weight": "10%"},
    {"Criterion": "Usefulness", "Description": "Practical usability", "Weight": "10%"},
])
rubric_data.to_csv(OUT_DIR / "scoring_rubric.csv", index=False)

examples = []
for prompt, g in df_proc.groupby("prompt"):
    g = g.copy()
    g["quality_score"] = pd.to_numeric(g["quality_score"], errors="coerce")
    g["latency_ms"] = pd.to_numeric(g["latency_ms"], errors="coerce")

    g_sorted = g.sort_values(
        by=["quality_score", "structured", "latency_ms"],
        ascending=[False, False, True]
    )

    best = g_sorted.iloc[0]
    worst = g_sorted.iloc[-1] if len(g_sorted) > 1 else best

    examples.append({
        "prompt": prompt,
        "best_input_id": best["input_id"],
        "best_quality_score": best["quality_score"],
        "best_output_type": best["output_type"],
        "best_output": str(best["final_output"])[:450],
        "worst_input_id": worst["input_id"],
        "worst_quality_score": worst["quality_score"],
        "worst_output_type": worst["output_type"],
        "worst_output": str(worst["final_output"])[:450],
    })

examples_df = pd.DataFrame(examples)
examples_df.to_csv(OUT_DIR / "example_cases.csv", index=False)

fig1 = px.bar(
    report.sort_values("avg_final_score", ascending=True),
    x="avg_final_score",
    y="prompt",
    orientation="h",
    text="avg_final_score",
    labels={"avg_final_score": "Score", "prompt": "Prompt"},
)
fig1.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
fig1.update_layout(
    title={
        "text": "Prompt ranking by overall score<br><span style='font-size: 18px; font-weight: normal;'>Source: scored_results.json | average final score per prompt</span>"
    }
)
fig1.update_xaxes(title_text="Score")
fig1.update_yaxes(title_text="Prompt")
safe_write_image(fig1, OUT_DIR / "prompt_scores.png")
with open(OUT_DIR / "prompt_scores.png.meta.json", "w", encoding="utf-8") as f:
    json.dump({
        "caption": "Prompt ranking",
        "description": "Horizontal bar chart ranking prompts by average final score."
    }, f, indent=2)

metric_long = report[[
    "prompt",
    "avg_accuracy",
    "avg_relevance",
    "avg_completeness",
    "avg_consistency",
    "avg_usefulness",
    "avg_structure",
    "avg_conciseness",
]].melt(id_vars="prompt", var_name="metric", value_name="score")

metric_long["metric"] = metric_long["metric"].replace({
    "avg_accuracy": "correctness",
    "avg_relevance": "relevance",
    "avg_completeness": "completeness",
    "avg_consistency": "consistency",
    "avg_usefulness": "usefulness",
    "avg_structure": "structure",
    "avg_conciseness": "conciseness",
})

fig2 = px.bar(
    metric_long,
    x="prompt",
    y="score",
    color="metric",
    barmode="group",
    labels={"score": "Score", "prompt": "Prompt", "metric": "Metric"},
)
fig2.update_layout(
    title={
        "text": "Metric breakdown by prompt<br><span style='font-size: 18px; font-weight: normal;'>Source: scored_results.json | average metric scores</span>"
    }
)
fig2.update_xaxes(title_text="Prompt")
fig2.update_yaxes(title_text="Score")
safe_write_image(fig2, OUT_DIR / "metric_breakdown.png")
with open(OUT_DIR / "metric_breakdown.png.meta.json", "w", encoding="utf-8") as f:
    json.dump({
        "caption": "Metric breakdown",
        "description": "Grouped bar chart showing average metric scores by prompt."
    }, f, indent=2)

fig3 = px.scatter(
    report,
    x="avg_latency_score",
    y="avg_final_score",
    size="runs",
    color="prompt",
    labels={"avg_latency_score": "Latency", "avg_final_score": "Score"},
)
fig3.update_layout(
    title={
        "text": "Quality versus latency tradeoff<br><span style='font-size: 18px; font-weight: normal;'>Source: scored_results.json | bubble size = runs</span>"
    }
)
fig3.update_xaxes(title_text="Latency")
fig3.update_yaxes(title_text="Score")
safe_write_image(fig3, OUT_DIR / "quality_latency.png")
with open(OUT_DIR / "quality_latency.png.meta.json", "w", encoding="utf-8") as f:
    json.dump({
        "caption": "Quality versus latency",
        "description": "Scatter plot showing the tradeoff between latency score and final score."
    }, f, indent=2)

small_table = report[[
    "rank",
    "prompt",
    "avg_final_score",
    "avg_accuracy",
    "avg_completeness",
    "structured_rate",
]].round(3).rename(columns={
    "rank": "Rank",
    "prompt": "Prompt",
    "avg_final_score": "Score",
    "avg_accuracy": "Correctness",
    "avg_completeness": "Completeness",
    "structured_rate": "Structured Rate",
})

small_table_html = small_table.to_html(index=False, escape=False)

example_blocks = []
for _, row in examples_df.iterrows():
    example_blocks.append(f"""
    <div class="example-box">
        <h4>{row['prompt']}</h4>
        <div class="two-col">
            <div>
                <p><b>Best</b> | {row['best_input_id']} | score {row['best_quality_score']}</p>
                <pre>{row['best_output']}</pre>
            </div>
            <div>
                <p><b>Worst</b> | {row['worst_input_id']} | score {row['worst_quality_score']}</p>
                <pre>{row['worst_output']}</pre>
            </div>
        </div>
    </div>
    """)

examples_html = "\n".join(example_blocks)

# ✅ ADD THIS AT TOP (only once)
df_inputs = pd.read_excel("data/dataset.xlsx")
input_list = df_inputs.iloc[:, -1].dropna().tolist()


# Group records by input_id
cases = defaultdict(list)
for r in processed_records:
    cases[r.get("input_id", "")].append(r)

# Create case index page (IMPROVED UI)
case_links = ""
for case_id in cases.keys():
    case_links += f'<div class="case-box"><a href="{case_id}.html">{case_id}</a></div>'

case_index_html = f"""
<html>
<head>
<title>Case Summary</title>
<style>
body {{
    font-family: Arial;
    padding: 30px;
    background: #f4f7fb;
    display: flex;
    justify-content: center;
}}

.container {{
    text-align: center;
}}

.case-box {{
    background: white;
    padding: 15px 30px;
    margin: 10px auto;
    width: 200px;
    border-radius: 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    transition: 0.2s;
}}

.case-box:hover {{
    transform: scale(1.05);
}}

a {{
    text-decoration: none;
    font-size: 18px;
    color: #2563eb;
    font-weight: bold;
}}
</style>
</head>
<body>
<div class="container">
<h1>Case List</h1>
{case_links}
</div>
</body>
</html>
"""

with open(OUT_DIR / "case_index.html", "w", encoding="utf-8") as f:
    f.write(case_index_html)

# Create individual case pages
for case_id, records in cases.items():

    # ✅ FIXED: get input from dataset using index mapping
    try:
        index = int(case_id.split("_")[1]) - 1
        input_text = input_list[index] if index < len(input_list) else "Input not available"
    except:
        input_text = "Input not available"

    best_action = None
    best_decision = None
    best_action_score = -1
    best_decision_score = -1

    for r in records:
        score = float(r.get("quality_score", 0))
        raw = r.get("final_output", "")

        output = None

        # PRIORITY: parsed_output
        if "parsed_output" in r and isinstance(r["parsed_output"], dict):
            output = r["parsed_output"]
            score += 5
        else:
            if isinstance(raw, dict):
                output = raw
                score += 3
            elif isinstance(raw, str):
                start = raw.find("{")
                end = raw.rfind("}") + 1

                if start != -1 and end != -1:
                    try:
                        output = json.loads(raw[start:end])
                        score += 2
                    except:
                        continue

        if not output:
            continue

        # Prefer structured outputs always (not just high score)

        if "action_items" in output:
          if best_action is None or score >= best_action_score:
           best_action = output
           best_action_score = score

        if "decisions" in output and output["decisions"]:
          if best_decision is None or score >= best_decision_score:
           best_decision = output
           best_decision_score = score

    action_rows = ""
    decision_rows = ""

    # ACTIONS
    if best_action and "action_items" in best_action:
        for item in best_action["action_items"]:
            action_rows += f"""
            <tr>
                <td>{item.get('owner','')}</td>
                <td>{item.get('action','')}</td>
                <td>{item.get('due_date','')}</td>
            </tr>
            """

    # DECISIONS (FIXED FILTER)
    if best_decision and "decisions" in best_decision:
        for d in best_decision["decisions"]:
            decision_text = d.get('decision', '').lower()

            # ✅ Improved filtering (only remove clear actions)
            action_keywords = [
                "will prepare",
                "will update",
                "will coordinate",
                "will set up"
            ]

            if any(keyword in decision_text for keyword in action_keywords):
                continue

            decision_rows += f"""
            <tr>
                <td>{d.get('decision','')}</td>
                <td>{d.get('context','')}</td>
            </tr>
            """

    case_html = f"""
    <html>
    <head>
    <title>{case_id}</title>
    <style>
    body {{
        font-family: Arial;
        padding: 20px;
        background: #f4f7fb;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 20px;
        background: white;
    }}
    th, td {{
        border: 1px solid #ddd;
        padding: 8px;
    }}
    th {{
        background: #2f3b52;
        color: white;
    }}

    .input-box {{
        background: white;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 20px;
        border: 1px solid #ddd;
        white-space: pre-wrap;
    }}
    </style>
    </head>
    <body>

    <h2>{case_id}</h2>

    <h3>Input</h3>
    <div class="input-box">
    {input_text}
    </div>

    <h3>Action Items</h3>
    <table>
        <tr>
            <th>Owner</th>
            <th>Action</th>
            <th>Deadline</th>
        </tr>
        {action_rows}
    </table>

    <h3>Decisions</h3>
    <table>
        <tr>
            <th>Decision</th>
            <th>Context</th>
        </tr>
        {decision_rows}
    </table>

    </body>
    </html>
    """

    with open(OUT_DIR / f"{case_id}.html", "w", encoding="utf-8") as f:
        f.write(case_html)

html = f"""
<html>
<head>
<title>LLM Evaluation Report</title>
<style>
body {{
    font-family: 'Segoe UI', Arial;
    background: #f4f7fb;
    margin: 0;
    padding: 0;
}}
.container {{
    width: 92%;
    margin: 20px auto;
}}
.header {{
    background: white;
    padding: 20px;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    margin-bottom: 20px;
}}
.badge {{
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background: #e8f0fe;
    color: #174ea6;
    font-size: 13px;
    margin-right: 8px;
    margin-top: 8px;
}}
.button-row {{
    margin-top: 14px;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
}}
.small {{
    color: #555;
    font-size: 14px;
}}
details {{
    background: white;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    margin-bottom: 14px;
    overflow: hidden;
}}
summary {{
    padding: 18px 20px;
    cursor: pointer;
    font-weight: 700;
    list-style: none;
}}
summary::-webkit-details-marker {{
    display: none;
}}
.section-body {{
    padding: 0 20px 20px 20px;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-top: 12px;
}}
.card {{
    background: #fafbff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 14px;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    background: white;
    font-size: 14px;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 9px;
    text-align: left;
    vertical-align: top;
}}
th {{
    background: #2f3b52;
    color: white;
}}
img {{
    width: 100%;
    max-width: 100%;
    border-radius: 10px;
}}
pre {{
    white-space: pre-wrap;
    word-wrap: break-word;
    background: #f8f9fb;
    padding: 10px;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    margin: 8px 0;
    min-height: 90px;
}}
a.button {{
    display: inline-block;
    padding: 10px 14px;
    background: #2563eb;
    color: white;
    text-decoration: none;
    border-radius: 8px;
}}
a.button.secondary {{
    background: #64748b;
}}
.example-box {{
    margin-bottom: 18px;
    padding: 14px;
    background: #fafbff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
}}
.two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}}
@media (max-width: 900px) {{
    .two-col {{
        grid-template-columns: 1fr;
    }}
}}
.muted {{
    color: #667085;
    font-size: 13px;
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>LLM Evaluation Report</h1>
        <p class="small">This report compares prompt versions using a weighted rubric, ranked scores, charts, and example outputs.</p>
        <span class="badge">Top Prompt: {summary["top_prompt"]}</span>
        <span class="badge">Top Score: {summary["top_score"]}</span>
        <span class="badge">Prompts: {report["prompt"].nunique()}</span>
        <span class="badge">Runs: {int(report["runs"].sum())}</span>
        <div class="button-row">
            <a class="button" href="/static/ranked_comparison_table.csv" download>Download Full CSV</a>
            <a class="button" href="/static/scoring_rubric.csv" download>Download Rubric CSV</a>
            <a class="button" href="/static/executive_summary.json" download>Download Summary JSON</a>
            <a class="button" href="/static/example_cases.csv" download>Download Examples CSV</a>
            <a class="button secondary" href="/static/case_index.html" target="_blank">Open HTML Summary</a>
        </div>
    </div>

    <details open>
        <summary>Executive Summary</summary>
        <div class="section-body">
            <div class="grid">
                <div class="card">
                    <p><b>Top prompt:</b> {summary["top_prompt"]}</p>
                    <p><b>Top score:</b> {summary["top_score"]}</p>
                    <p><b>Key win reason:</b> {summary["key_win_reason"]}</p>
                    <p><b>Biggest weakness:</b> {summary["biggest_weakness"]}</p>
                    <p><b>Recommendation:</b> {summary["recommendation"]}</p>
                </div>
                <div class="card">
                    <p><b>Best signal:</b> high correctness and completeness with structured output.</p>
                    <p><b>Decision rule:</b> rank by final score, then inspect structure and completeness.</p>
                    <p><b>Review focus:</b> compare top prompts side-by-side before shipping.</p>
                </div>
            </div>
        </div>
    </details>

    <details>
        <summary>Scoring Rubric</summary>
        <div class="section-body">
            <div class="grid">
                <div class="card"><b>Correctness</b><br>Accuracy of extracted information.</div>
                <div class="card"><b>Completeness</b><br>Captured all relevant items.</div>
                <div class="card"><b>Structure</b><br>Followed the required output format.</div>
                <div class="card"><b>Conciseness</b><br>Clarity and brevity.</div>
                <div class="card"><b>Usefulness</b><br>Practical usability.</div>
            </div>
            <div class="card" style="margin-top:14px;">
                <h4>Rubric Weights</h4>
                {rubric_data.to_html(index=False, escape=False)}
            </div>
        </div>
    </details>

    <details>
        <summary>Ranked Comparison</summary>
        <div class="section-body">
            <p class="muted">Small on-screen table for quick reading. Full detailed CSV is available in exports.</p>
            {small_table_html}
        </div>
    </details>

    <details>
        <summary>Charts</summary>
        <div class="section-body">
            <div class="grid">
                <div class="card">
                    <h3>Prompt Ranking</h3>
                    <img src="/static/prompt_scores.png" alt="Prompt ranking chart">
                </div>
                <div class="card">
                    <h3>Metric Breakdown</h3>
                    <img src="/static/metric_breakdown.png" alt="Metric breakdown chart">
                </div>
                <div class="card">
                    <h3>Latency Tradeoff</h3>
                    <img src="/static/quality_latency.png" alt="Latency tradeoff chart">
                </div>
            </div>
        </div>
    </details>

    <details>
        <summary>Side-by-Side Outputs</summary>
        <div class="section-body">
            <p class="muted">Compare the best and worst outputs per prompt in a compact side-by-side layout.</p>
            {examples_html}
        </div>
    </details>
</div>
</body>
</html>
"""

with open(OUT_DIR / "llm_eval_report.html", "w", encoding="utf-8") as f:
    f.write(html)

with open(OUT_DIR / "combined_report.json", "w", encoding="utf-8") as f:
    json.dump({
        "executive_summary": summary,
        "ranked_table_file": str(OUT_DIR / "ranked_comparison_table.csv"),
        "examples_file": str(OUT_DIR / "example_cases.csv"),
        "html_report": str(OUT_DIR / "llm_eval_report.html"),
    }, f, indent=2)

print(json.dumps(summary, indent=2))