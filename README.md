## promptAnalysis Module

The `promptAnalysis` module implements a dataset-driven evaluation pipeline for comparing different prompt strategies on Large Language Models.

### Key Features

* **Dataset Integration**

  * Loads 300+ meeting transcripts from an Excel dataset
  * Supports both clean and noisy (realistic) inputs

* **Prompt Comparison**

  * Evaluates multiple prompt variants (e.g., strict vs loose)
  * Applies the same inputs across all prompts for fair comparison

* **Automated Evaluation**

  * Uses LLM-as-a-judge (Groq) for scoring
  * Combines model-based and heuristic metrics

* **Multi-Metric Scoring**

  * Accuracy
  * Relevance
  * Completeness
  * Consistency
  * Usefulness
  * Structure
  * Conciseness
  * Latency
  * Cost

* **Weighted Scoring System**

  * Configurable weights via UI
  * Produces final composite score per prompt

* **Reporting & Visualization**

  * Generates ranked comparison tables
  * Visualizes performance using charts
  * Exports HTML reports

### Purpose

This module enables systematic benchmarking of prompts by running structured experiments across a dataset, helping identify the most effective prompt design for a given task.

##  How to Run the Project

### 1. Clone the repository

```bash
git clone <your-repo-link>
cd llm_eval
```

### 2. Create and activate virtual environment

```bash
python -m venv venv
source venv/bin/activate   # Mac/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add API keys

Update `config.json` with your API keys:

* GROQ_API_KEY
* OPENAI_API_KEY (optional)
* GOOGLE_API_KEY (optional)
* ANTHROPIC_API_KEY (optional)

### 5. Run the application

```bash
uvicorn config_panel:app --reload
```

### 6. Open in browser

```
http://127.0.0.1:8000
```

Click **Run Pipeline** to execute evaluation.
