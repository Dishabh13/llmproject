from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from fastapi import FastAPI, Form, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from cryptography.fernet import Fernet, InvalidToken
from data.file_parser import parse_bytes, SUPPORTED_EXTENSIONS
from security_helper import (
    load_config,
    save_config,
    store_api_key,
    decrypt_secret,
)
app = FastAPI()
app.mount("/static", StaticFiles(directory="output"), name="static")

CONFIG_FILE = "config.json"
UPLOAD_DIR  = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Shared CSS
# ─────────────────────────────────────────────────────────────────────────────

STYLES = """
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    min-height: 100vh;
  }

  .page { max-width: 760px; margin: 0 auto; padding: 48px 24px 80px; }

  .page-title {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.3px;
    margin-bottom: 32px;
    color: #1d1d1f;
  }

  .card {
    background: #fff;
    border-radius: 14px;
    padding: 28px 28px 24px;
    margin-bottom: 20px;
    border: 1px solid #e5e5ea;
  }

  .card-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #86868b;
    margin-bottom: 18px;
  }

  label {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: #3a3a3c;
    margin-bottom: 5px;
  }

  input[type=text], input[type=password], input[type=number], select {
    width: 100%;
    padding: 10px 13px;
    border: 1px solid #d2d2d7;
    border-radius: 8px;
    font-size: 14px;
    color: #1d1d1f;
    background: #fafafa;
    outline: none;
    transition: border-color .15s, box-shadow .15s;
    margin-bottom: 14px;
    -webkit-appearance: none;
    appearance: none;
  }

  input:focus, select:focus {
    border-color: #0071e3;
    box-shadow: 0 0 0 3px rgba(0,113,227,.12);
    background: #fff;
  }

  .key-wrap { position: relative; margin-bottom: 14px; }
  .key-wrap input { padding-right: 44px; margin-bottom: 0; }
  .key-toggle {
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    background: none; border: none; cursor: pointer;
    color: #86868b; font-size: 15px; padding: 2px; line-height: 1;
  }
  .key-toggle:hover { color: #1d1d1f; }

  .weight-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }
  .weight-item label { font-size: 13px; margin-bottom: 4px; }
  .weight-item input { margin-bottom: 0; }
  .weight-total {
    margin-top: 12px;
    font-size: 13px;
    color: #86868b;
    text-align: right;
  }
  .weight-total span { font-weight: 600; color: #1d1d1f; }

  .mode-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
  .mode-tab {
    flex: 1; padding: 11px 16px; border-radius: 9px;
    border: 1.5px solid #d2d2d7; background: #fafafa;
    font-size: 14px; font-weight: 500; color: #6e6e73;
    cursor: pointer; text-align: center; transition: all .15s;
  }
  .mode-tab.active {
    border-color: #0071e3; background: #e8f0fe; color: #0071e3;
  }
  .mode-panel { display: none; }
  .mode-panel.active { display: block; }

  .dropzone {
    border: 2px dashed #d2d2d7; border-radius: 10px;
    padding: 36px 20px; text-align: center;
    transition: border-color .2s, background .2s;
    cursor: pointer; background: #fafafa;
  }
  .dropzone.dragover { border-color: #0071e3; background: #f0f6ff; }
  .dropzone .dz-icon { font-size: 32px; margin-bottom: 10px; }
  .dropzone .dz-hint { font-size: 13px; color: #86868b; margin-top: 6px; }
  .dropzone .dz-btn {
    display: inline-block; margin-top: 14px; padding: 8px 18px;
    border-radius: 7px; border: 1.5px solid #0071e3;
    font-size: 13px; font-weight: 500; color: #0071e3;
    background: #fff; cursor: pointer;
  }
  #file-name-display {
    margin-top: 10px; font-size: 13px; font-weight: 500;
    color: #3a3a3c; display: none;
  }
  #file-name-display .fn-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #e8f0fe; border-radius: 6px; padding: 4px 10px;
  }

  .btn {
    display: inline-block; padding: 11px 22px; border-radius: 9px;
    font-size: 14px; font-weight: 500; cursor: pointer; border: none;
    transition: opacity .15s, transform .1s; text-decoration: none;
  }
  .btn:active { transform: scale(.98); }
  .btn-primary { background: #0071e3; color: #fff; }
  .btn-primary:hover { opacity: .88; }
  .btn-secondary { background: #e5e5ea; color: #1d1d1f; }
  .btn-secondary:hover { background: #d2d2d7; }
  .btn-block { display: block; width: 100%; text-align: center; }

  .results-wrap { overflow-x: auto; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; padding: 9px 12px;
    background: #f5f5f7; font-weight: 600; font-size: 11px;
    color: #6e6e73; text-transform: uppercase; letter-spacing: .4px;
    border-bottom: 1px solid #e5e5ea;
  }
  td { padding: 10px 12px; border-bottom: 1px solid #f2f2f2; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  .score-badge {
    display: inline-block; padding: 3px 9px; border-radius: 20px;
    font-weight: 600; font-size: 12px;
  }
  .score-hi  { background: #d1f7e0; color: #1a7f3c; }
  .score-mid { background: #fff3cc; color: #996600; }
  .score-lo  { background: #fde8e7; color: #c0392b; }

  .back {
    font-size: 13px; color: #0071e3; text-decoration: none;
    margin-bottom: 24px; display: inline-block;
  }
  .back:hover { text-decoration: underline; }

  .flash {
    padding: 13px 16px; border-radius: 9px; margin-bottom: 20px;
    font-size: 14px; font-weight: 500;
  }
  .flash-ok   { background: #d1f7e0; color: #1a7f3c; }
  .flash-err  { background: #fde8e7; color: #c0392b; }

  @media (max-width: 600px) {
    .weight-grid { grid-template-columns: 1fr 1fr; }
    .mode-tabs   { flex-direction: column; }
  }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main config page (GET /)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def form(saved: str = "", err: str = ""):
    config  = load_config()
    weights = config.get("weights", {})

    # API key fields are kept blank for security.
    # The user can enter a new key to add it to the list.
    groq_key = ""
    openai_key = ""
    google_key = ""
    anthropic_key = ""

    def sel(v):
        return "selected" if config.get("selected_model") == v else ""

    flash = ""
    if saved:
        flash = '<div class="flash flash-ok">✓ Configuration saved.</div>'
    if err:
        flash = f'<div class="flash flash-err">⚠ {err}</div>'

    weight_fields = [
        ("accuracy",     "Accuracy"),
        ("relevance",    "Relevance"),
        ("completeness", "Completeness"),
        ("consistency",  "Consistency"),
        ("usefulness",   "Usefulness"),
        ("structure",    "Structure"),
        ("conciseness",  "Conciseness"),
        ("latency",      "Latency"),
        ("cost",         "Cost"),
    ]

    w_inputs = ""
    for key, label in weight_fields:
        val = weights.get(key, 0)
        w_inputs += f"""
        <div class="weight-item">
          <label for="w_{key}">{label}</label>
          <input type="number" id="w_{key}" name="{key}" value="{val}"
                 min="0" max="100" oninput="updateTotal()">
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Eval — Config</title>
  {STYLES}
</head>
<body>
<div class="page">

  <div class="page-title">LLM Evaluation Config</div>
  {flash}

  <form method="post" action="/">

    <div class="card">
      <div class="card-title">API Keys</div>

      <label>Groq API Key</label>
      <div class="key-wrap">
        <input type="password" name="groq" id="groq_key"
               value="{groq_key}"
               placeholder="gsk_..." autocomplete="off">
        <button type="button" class="key-toggle" onclick="toggleKey('groq_key')" title="Show/hide">👁</button>
      </div>

      <label>OpenAI API Key</label>
      <div class="key-wrap">
        <input type="password" name="openai" id="openai_key"
               value="{openai_key}"
               placeholder="sk-..." autocomplete="off">
        <button type="button" class="key-toggle" onclick="toggleKey('openai_key')" title="Show/hide">👁</button>
      </div>

      <label>Google API Key</label>
      <div class="key-wrap">
        <input type="password" name="google" id="google_key"
               value="{google_key}"
               placeholder="AIza..." autocomplete="off">
        <button type="button" class="key-toggle" onclick="toggleKey('google_key')" title="Show/hide">👁</button>
      </div>

      <label>Anthropic API Key</label>
      <div class="key-wrap">
        <input type="password" name="anthropic" id="anthropic_key"
               value="{anthropic_key}"
               placeholder="sk-ant-..." autocomplete="off">
        <button type="button" class="key-toggle" onclick="toggleKey('anthropic_key')" title="Show/hide">👁</button>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Model Selection</div>
      <label>Model</label>
      <select name="model">
        <option value="groq"             {sel('groq')}>Groq (Llama 3.3-70b)</option>
        <option value="gpt-4o-mini"      {sel('gpt-4o-mini')}>GPT-4o mini</option>
        <option value="gpt-4o"           {sel('gpt-4o')}>GPT-4o</option>
        <option value="gemini-1.5-pro"   {sel('gemini-1.5-pro')}>Gemini 1.5 Pro</option>
        <option value="gemini-1.5-flash" {sel('gemini-1.5-flash')}>Gemini 1.5 Flash</option>
        <option value="claude-3-sonnet"  {sel('claude-3-sonnet')}>Claude 3 Sonnet</option>
        <option value="claude-3-haiku"   {sel('claude-3-haiku')}>Claude 3 Haiku</option>
      </select>
    </div>

    <div class="card">
      <div class="card-title">Evaluation Weights &nbsp;<small style="font-size:11px;font-weight:400;text-transform:none;">(must sum to 100)</small></div>
      <div class="weight-grid">
        {w_inputs}
      </div>
      <div class="weight-total">Total: <span id="total-display">—</span></div>
    </div>

    <button type="submit" class="btn btn-primary btn-block">Save Configuration</button>
  </form>

  <div class="card" style="margin-top:20px;">
    <div class="card-title">Evaluation</div>
    <a href="/eval-mode" style="text-decoration:none;">
      <button type="button" class="btn btn-primary btn-block">
        Choose Input &amp; Run Evaluation →
      </button>
    </a>
  </div>

</div>

<script>
function toggleKey(id) {{
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}}

function updateTotal() {{
  const fields = ['accuracy','relevance','completeness','consistency',
                  'usefulness','structure','conciseness','latency','cost'];
  let sum = 0;
  fields.forEach(f => {{
    const el = document.getElementById('w_' + f);
    if (el) sum += parseInt(el.value) || 0;
  }});
  const disp = document.getElementById('total-display');
  disp.textContent = sum;
  disp.style.color = sum === 100 ? '#34c759' : '#ff3b30';
}}

updateTotal();
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Save config (POST /)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/", response_class=HTMLResponse)
async def save(
    request:      Request,
    openai:       str = Form(""),
    google:       str = Form(""),
    anthropic:    str = Form(""),
    groq:         str = Form(""),
    model:        str = Form(...),
    accuracy:     int = Form(...),
    relevance:    int = Form(...),
    completeness: int = Form(...),
    consistency:  int = Form(...),
    usefulness:   int = Form(0),
    structure:    int = Form(0),
    conciseness:  int = Form(0),
    latency:      int = Form(...),
    cost:         int = Form(...),
):
    total = (accuracy + relevance + completeness + consistency +
             usefulness + structure + conciseness + latency + cost)

    if total != 100:
        return RedirectResponse(
            f"/?err=Weights+must+sum+to+100+(got+{total})", status_code=303
        )

    config = load_config()
    store_api_key(config, "openai", openai)
    store_api_key(config, "google", google)
    store_api_key(config, "anthropic", anthropic)
    store_api_key(config, "groq", groq)
    
    config["selected_model"] = model
    config["weights"] = {
        "accuracy": accuracy,
        "relevance": relevance,
        "completeness": completeness,
        "consistency": consistency,
        "usefulness": usefulness,
        "structure": structure,
        "conciseness": conciseness,
        "latency": latency,
        "cost": cost,
    }
    save_config(config)
    return RedirectResponse("/?saved=1", status_code=303)

# ─────────────────────────────────────────────────────────────────────────────
# Eval mode chooser
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/eval-mode", response_class=HTMLResponse)
def eval_mode_page():
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Eval — Choose Input</title>
  {STYLES}
</head>
<body>
<div class="page">
  <a class="back" href="/">← Back to Config</a>
  <div class="page-title">Choose Evaluation Input</div>

  <div class="mode-tabs">
    <div class="mode-tab active" id="tab-dataset" onclick="switchMode('dataset')">📊 Dataset</div>
    <div class="mode-tab"        id="tab-file"    onclick="switchMode('file')">📄 Upload Document</div>
  </div>

  <!-- Dataset panel -->
  <div id="panel-dataset" class="mode-panel active">
    <div class="card">
      <div class="card-title">Dataset Evaluation</div>
      <p style="font-size:14px;color:#6e6e73;margin-bottom:20px;">
        Run on the built-in <code>data/dataset.xlsx</code> — the original dataset flow.
      </p>
      <form method="post" action="/run-dataset">
        <button class="btn btn-primary btn-block" type="submit">Run Dataset Evaluation</button>
      </form>
    </div>
  </div>

  <!-- File upload panel -->
  <div id="panel-file" class="mode-panel">
    <div class="card">
      <div class="card-title">Document Upload</div>
      <p style="font-size:14px;color:#6e6e73;margin-bottom:20px;">
        Upload a meeting transcript. Text is extracted and evaluated for
        <strong>action items</strong> and <strong>decisions</strong>.
        Accepted: <strong>.pdf &nbsp; .docx &nbsp; .doc &nbsp; .txt &nbsp; .json</strong>
      </p>

      <form id="upload-form-el" method="post" action="/run-file" enctype="multipart/form-data">

        <div class="dropzone" id="dropzone"
             onclick="document.getElementById('file-input').click()"
             ondragover="onDragOver(event)"
             ondragleave="onDragLeave(event)"
             ondrop="onDrop(event)">
          <div class="dz-icon">📁</div>
          <div style="font-size:14px;font-weight:500;">Drop your file here</div>
          <div class="dz-hint">or click to browse</div>
          <span class="dz-btn">Browse</span>
        </div>

        <input type="file" id="file-input" name="file" style="display:none"
               accept=".pdf,.docx,.doc,.txt,.json"
               onchange="onFileSelected(this)">

        <div id="file-name-display">
          <div class="fn-badge">
            <span>📎</span><span id="fn-text"></span>
          </div>
        </div>

        <div style="margin-top:20px;">
          <button class="btn btn-primary btn-block" type="submit" id="upload-btn" disabled>
            Extract &amp; Evaluate
          </button>
        </div>
      </form>
    </div>
  </div>

</div>

<script>
function switchMode(mode) {{
  document.getElementById('tab-dataset').classList.toggle('active', mode === 'dataset');
  document.getElementById('tab-file').classList.toggle('active', mode === 'file');
  document.getElementById('panel-dataset').classList.toggle('active', mode === 'dataset');
  document.getElementById('panel-file').classList.toggle('active', mode === 'file');
}}

function onFileSelected(input) {{
  if (input.files && input.files[0]) showFile(input.files[0].name);
}}

function showFile(name) {{
  document.getElementById('fn-text').textContent = name;
  document.getElementById('file-name-display').style.display = 'block';
  document.getElementById('upload-btn').disabled = false;
}}

function onDragOver(e) {{
  e.preventDefault();
  document.getElementById('dropzone').classList.add('dragover');
}}

function onDragLeave() {{
  document.getElementById('dropzone').classList.remove('dragover');
}}

function onDrop(e) {{
  e.preventDefault();
  document.getElementById('dropzone').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  document.getElementById('file-input').files = dt.files;
  showFile(file.name);
}}
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Dataset pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/run-dataset", response_class=HTMLResponse)
def run_dataset():
    try:
        _run_pipeline_dataset()
        return RedirectResponse("/results-dataset", status_code=303)
    except Exception as e:
        return _error_page(str(e))


def _run_pipeline_dataset():
    base = str(Path(__file__).parent)
    for script in ["main.py", "process_outputs.py", "evaluation_grok.py", "report.py"]:
        rc = subprocess.call([sys.executable, os.path.join(base, script)], cwd=base)
        if rc != 0:
            raise RuntimeError(f"{script} exited with non-zero code {rc}")


@app.get("/results-dataset", response_class=HTMLResponse)
def results_dataset():
    try:
        with open("scored_results.json", "r") as f:
            data = json.load(f)
        results = data if isinstance(data, list) else data.get("results", [])
        results = sorted(results, key=lambda x: x.get("final_score", 0), reverse=True)
        return _results_page(results,
                             title="Dataset Evaluation Results",
                             subtitle=f"{len(results)} records from dataset.xlsx")
    except Exception as e:
        return _error_page(str(e))

@app.get("/results-file", response_class=HTMLResponse)
def results_file():
    try:
        with open("scored_results.json", "r") as f:
            data = json.load(f)

        results = data if isinstance(data, list) else data.get("results", [])
        results = sorted(
          results,
          key=lambda x: float(x.get("final_score") or 0),
          reverse=True
)
        return _results_page(
            results,
            title="Document Evaluation Results",
            is_file=True   # 👈 IMPORTANT
        )

    except Exception as e:
        return _error_page(str(e))
# ─────────────────────────────────────────────────────────────────────────────
# File upload pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/run-file", response_class=HTMLResponse)
async def run_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return _error_page(
            f"Unsupported file type '{ext}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        raw_bytes = await file.read()
        record = parse_bytes(raw_bytes, file.filename)
    except Exception as e:
        return _error_page(f"Text extraction failed: {e}")

    with open("file_inputs.json", "w") as f:
        json.dump([record], f, indent=2)

    try:
        results = _run_pipeline_file()
        return RedirectResponse("/results-file", status_code=303)
    except Exception as e:
        return _error_page(str(e))


def _run_pipeline_file() -> list:
    base = str(Path(__file__).parent)

    rc = subprocess.call([sys.executable, os.path.join(base, "main_file.py")], cwd=base)
    if rc != 0:
        raise RuntimeError("main_file.py failed — check your API key / model selection.")

    subprocess.call([sys.executable, os.path.join(base, "process_outputs.py")], cwd=base)
    subprocess.call([sys.executable, os.path.join(base, "evaluation.py")], cwd=base)

    try:
        with open("scored_results.json", "r") as f:
            data = json.load(f)
        results = data if isinstance(data, list) else data.get("results", [])
        return sorted(
         results,
         key=lambda x: float(x.get("final_score") or 0),
         reverse=True
         )
    except Exception:
        return []


def safe_round(x):
    try:
        return round(float(x or 0), 2)
    except:
        return 0.0


def _results_page(results: list, title: str = "Results",
                  subtitle: str = "", extracted_text: str = "", is_file: bool = False) -> str:

    # -------------------------
    # BUILD TABLE ROWS
    # -------------------------
    rows = ""
    for r in results:
        m  = r.get("metrics", {}) or {}
        fs = safe_round((r.get("final_score") or 0) * 100)

        rows += f"""<tr>
          <td style="font-weight:500;white-space:nowrap">{r.get('input_id','')}</td>
          <td><span class="score-badge-blue">{fs}</span></td>
          <td>{safe_round((m.get('accuracy') or 0) * 100)}</td>
          <td>{safe_round((m.get('relevance') or 0) * 100)}</td>
          <td>{safe_round((m.get('completeness') or 0) * 100)}</td>
          <td>{safe_round((m.get('consistency') or 0) * 100)}</td>
          <td>{safe_round((m.get('usefulness') or 0) * 100)}</td>
        </tr>"""

    # -------------------------
    # INPUT CONTENT SECTION ⭐ NEW
    # -------------------------
    input_section = ""
    if extracted_text:
        esc = extracted_text.replace("<","&lt;").replace(">","&gt;")
        input_section = f"""
        <div class="card">
          <div class="card-title">Input / File Content</div>
          <pre style="font-size:12px;line-height:1.65;color:#3a3a3c;
                      white-space:pre-wrap;word-break:break-word;
                      max-height:250px;overflow-y:auto;">{esc}</pre>
        </div>"""

    # -------------------------
    # ACTION + DECISION SECTION (unchanged)
    # -------------------------
    ad_section = ""
    if any(r.get("parsed_output") for r in results):
        all_actions   = []
        all_decisions = []
        all_risks     = []   
        for r in results:
            p = r.get("parsed_output", {}) or {}
            if isinstance(p, dict):
                for k, v in p.items():
                    lst = v if isinstance(v, list) else [str(v)]
                    if "action"   in k.lower(): all_actions.extend(lst)
                    if "decision" in k.lower(): all_decisions.extend(lst)
                    if "risk" in k.lower() or "issue" in k.lower(): all_risks.extend(lst)

        def build_table(items, cols):
            if not items:
                return "<p style='color:#86868b;font-size:13px'>None extracted.</p>"
            ths = "".join(f"<th>{c}</th>" for c in cols)
            trs = "".join(f"<tr><td>{i+1}</td><td>{str(item)[:200]}</td></tr>"
                          for i, item in enumerate(items))
            return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"

        if all_actions or all_decisions:
            ad_section = f"""
            <div class="card">
              <div class="card-title">Action Items</div>
              <div class="results-wrap">{build_table(all_actions, ['#','Action Item'])}</div>
            </div>
            <div class="card">
              <div class="card-title">Decisions</div>
              <div class="results-wrap">{build_table(all_decisions, ['#','Decision'])}</div>
              <div class="card">
              <div class="card-title">Risks / Issues</div>
              <div class="results-wrap">{build_table(all_risks, ['#','Risk'])}</div>
              </div>
            </div>"""

    report_link = "/report-file" if is_file else "/report"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Eval — {title}</title>

  {STYLES}

  <style>
    /* 🔵 NEW BLUE SCORE BADGE */
    .score-badge-blue {{
        background: #e6f0ff;
        color: #1d4ed8;
        padding: 6px 10px;
        border-radius: 8px;
        font-weight: 600;
        display: inline-block;
        min-width: 45px;
        text-align: center;
    }}
  </style>

</head>
<body>
<div class="page">

  <a class="back" href="/eval-mode">← New Evaluation</a>

  <div class="page-title">{title}</div>

  {input_section}

  {ad_section}

  <div class="card">
    <div class="card-title">Metric Scores (/100)</div>
    <div class="results-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Score</th>
            <th>Accuracy</th>
            <th>Relevance</th>
            <th>Completeness</th>
            <th>Consistency</th>
            <th>Usefulness</th>
          </tr>
        </thead>
        <tbody>
          {rows if rows else '<tr><td colspan="7" style="text-align:center;padding:24px;color:#86868b;">No results yet.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>

  <div style="display:flex;gap:12px;margin-top:4px;flex-wrap:wrap;">
        
    <a href="{report_link}" style="text-decoration:none;flex:1;min-width:140px;">
      <button class="btn btn-secondary btn-block">Full Report</button>
    </a>

    <a href="/" style="text-decoration:none;flex:1;min-width:140px;">
      <button class="btn btn-secondary btn-block">Back to Config</button>
    </a>

  </div>

</div>
</body>
</html>
"""


def _ul(items: list) -> str:
    if not items: return ""
    lis = "".join(f"<li style='margin-bottom:3px'>{str(i)[:120]}</li>" for i in items[:8])
    return f"<ul style='padding-left:16px;margin:0;font-size:13px'>{lis}</ul>"


def _error_page(msg: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Error</title>{STYLES}</head>
<body><div class="page">
  <a class="back" href="/">← Back</a>
  <div class="flash flash-err">⚠ {msg}</div>
</div></body></html>
""")


# ─────────────────────────────────────────────────────────────────────────────
# Report passthrough (UPDATED FOR NEW APPROACH)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/report-file", response_class=HTMLResponse)
def report_file():
    try:
        # ✅ UPDATED FILE
        with open("scored_results.json", "r") as f:
            data = json.load(f)

        results = data if isinstance(data, list) else data.get("results", [])

        all_actions = []
        all_decisions = []
        all_risks = []

        for r in results:
            p = r.get("final_output", {}) or {}

            # Handle BOTH dict + string outputs
            if isinstance(p, dict):
                actions = p.get("action_items", [])
                decisions = p.get("decisions", [])
                risks = p.get("risks", [])

                if isinstance(actions, list):
                    all_actions.extend(actions)

                if isinstance(decisions, list):
                    all_decisions.extend(decisions)

                if isinstance(risks, list):
                    all_risks.extend(risks)

        # -------------------------
        # ACTION TABLE
        # -------------------------
        def action_table():
            if not all_actions:
                return "<p>No action items found.</p>"

            rows = ""
            for i, a in enumerate(all_actions):
                if isinstance(a, dict):
                    rows += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{a.get('action','')}</td>
                        <td>{a.get('owner','')}</td>
                        <td>{a.get('due_date','')}</td>
                    </tr>
                    """
                else:
                    rows += f"<tr><td>{i+1}</td><td>{a}</td><td>-</td><td>-</td></tr>"

            return f"""
            <table>
                <tr><th>#</th><th>Action</th><th>Owner</th><th>Due Date</th></tr>
                {rows}
            </table>
            """

        # -------------------------
        # DECISION TABLE
        # -------------------------
        def decision_table():
            if not all_decisions:
                return "<p>No decisions found.</p>"

            rows = ""
            for i, d in enumerate(all_decisions):
                if isinstance(d, dict):
                    rows += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{d.get('decision','')}</td>
                        <td>{d.get('context','')}</td>
                    </tr>
                    """
                else:
                    rows += f"<tr><td>{i+1}</td><td>{d}</td><td>-</td></tr>"

            return f"""
            <table>
                <tr><th>#</th><th>Decision</th><th>Context</th></tr>
                {rows}
            </table>
            """

        # -------------------------
        # ✅ RISKS TABLE (FIXED)
        # -------------------------
        def risk_table():
            if not all_risks:
                return "<p>No risks found.</p>"

            rows = ""
            for i, r in enumerate(all_risks):
                if isinstance(r, dict):
                    rows += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{r.get('issue','')}</td>
                        <td>{r.get('context','')}</td>
                    </tr>
                    """
                else:
                    rows += f"<tr><td>{i+1}</td><td>{r}</td><td>-</td></tr>"

            return f"""
            <table>
                <tr><th>#</th><th>Risk</th><th>Context</th></tr>
                {rows}
            </table>
            """

        return HTMLResponse(f"""
        <html>
        <head>{STYLES}</head>
        <body>
        <div class="page">

            <a class="back" href="/results-file">← Back</a>

            <div class="page-title">Detailed Report</div>

            <div class="card">
                <div class="card-title">Action Items</div>
                {action_table()}
            </div>

            <div class="card">
                <div class="card-title">Decisions</div>
                {decision_table()}
            </div>

            <div class="card">
                <div class="card-title">Risks / Issues</div>
                {risk_table()}
            </div>

        </div>
        </body>
        </html>
        """)

    except Exception as e:
        return _error_page(str(e))


# -------------------------------
# OPTIONAL: KEEP OR REMOVE
# -------------------------------
@app.get("/report", response_class=HTMLResponse)
def show_report():
    try:
        with open("output/llm_eval_report.html", "r") as f:
            return f.read()
    except Exception:
        return HTMLResponse(
            "<h3 style='font-family:sans-serif;padding:40px'>Report not found — run evaluation first.</h3>"
        )


# -------------------------------
# REMOVE THIS (NOT NEEDED)
# -------------------------------
# @app.get("/run")
# def legacy_run():
#     return RedirectResponse("/eval-mode", status_code=302)