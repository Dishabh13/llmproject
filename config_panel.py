from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Form, File, UploadFile, Request, Cookie, Response
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
from auth import (
    create_user,
    authenticate_user,
    create_session,
    validate_session,
    destroy_session,
    get_user,
    update_user_api_keys,
    get_user_api_key,
    update_user_config,
    get_user_config,
    add_evaluation_history,
    get_evaluation_history,
    get_user_stats,
    clear_user_api_keys,
)
app = FastAPI()
app.mount("/static", StaticFiles(directory="output"), name="static")

CONFIG_FILE = "config.json"
UPLOAD_DIR  = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user(request: Request):
    """Get current user from session cookie."""
    token = request.cookies.get("session_token")
    if not token:
        return None
    user_id = validate_session(token)
    if not user_id:
        return None
    return get_user(user_id)


def require_auth(request: Request):
    """Check if user is authenticated, return user or None."""
    return get_current_user(request)


def _sidebar_html(active: str = "dashboard"):
    """Generate sidebar HTML."""
    def link_class(name):
        return "sidebar-link active" if active == name else "sidebar-link"
    
    return f'''
    <div class="sidebar">
      <div class="sidebar-logo">LLM Eval</div>
      <nav class="sidebar-nav">
        <a href="/dashboard" class="{link_class('dashboard')}">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
          Dashboard
        </a>
        <a href="/dashboard/profile" class="{link_class('profile')}">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg>
          API Keys
        </a>
        <a href="/dashboard/history" class="{link_class('history')}">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          History
        </a>
        <a href="/dashboard/stats" class="{link_class('stats')}">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
          Statistics
        </a>
        
        <div class="sidebar-section">Evaluation</div>
        <a href="/eval-mode" class="{link_class('eval')}">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
          Run Evaluation
        </a>
        
        <div class="sidebar-section">Account</div>
        <a href="/logout" class="sidebar-link">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
          Logout
        </a>
      </nav>
    </div>
    '''


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

  /* Dashboard Styles */
  .dashboard-layout {
    display: flex;
    min-height: 100vh;
  }

  .sidebar {
    width: 240px;
    background: #fff;
    border-right: 1px solid #e5e5ea;
    padding: 24px 0;
    position: fixed;
    height: 100vh;
    overflow-y: auto;
  }

  .sidebar-logo {
    padding: 0 20px 24px;
    font-size: 18px;
    font-weight: 600;
    color: #1d1d1f;
    border-bottom: 1px solid #e5e5ea;
    margin-bottom: 16px;
  }

  .sidebar-nav { padding: 0 12px; }

  .sidebar-link {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    color: #3a3a3c;
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 4px;
    transition: background .15s;
  }

  .sidebar-link:hover { background: #f5f5f7; }
  .sidebar-link.active { background: #e8f0fe; color: #0071e3; }

  .sidebar-link svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }

  .sidebar-section {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #86868b;
    padding: 16px 12px 8px;
  }

  .dashboard-main {
    margin-left: 240px;
    flex: 1;
    padding: 32px 40px;
    background: #f5f5f7;
    min-height: 100vh;
  }

  .dashboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
  }

  .dashboard-title {
    font-size: 26px;
    font-weight: 600;
    color: #1d1d1f;
  }

  .user-menu {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .user-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #0071e3;
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 14px;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
    margin-bottom: 32px;
  }

  .stat-card {
    background: #fff;
    border-radius: 14px;
    padding: 24px;
    border: 1px solid #e5e5ea;
  }

  .stat-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 12px;
    font-size: 18px;
  }

  .stat-icon.blue { background: #e8f0fe; }
  .stat-icon.green { background: #d1f7e0; }
  .stat-icon.orange { background: #fff3cc; }
  .stat-icon.purple { background: #f0e8fe; }

  .stat-value {
    font-size: 28px;
    font-weight: 600;
    color: #1d1d1f;
    margin-bottom: 4px;
  }

  .stat-label {
    font-size: 13px;
    color: #86868b;
  }

  .content-grid {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 24px;
  }

  .api-key-status {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 0;
    border-bottom: 1px solid #f2f2f2;
  }

  .api-key-status:last-child { border-bottom: none; }

  .key-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .key-indicator.configured { background: #34c759; }
  .key-indicator.missing { background: #d2d2d7; }

  .auth-page {
    max-width: 400px;
    margin: 80px auto;
    padding: 0 24px;
  }

  .auth-card {
    background: #fff;
    border-radius: 16px;
    padding: 40px 36px;
    border: 1px solid #e5e5ea;
    box-shadow: 0 4px 24px rgba(0,0,0,0.04);
  }

  .auth-title {
    font-size: 24px;
    font-weight: 600;
    text-align: center;
    margin-bottom: 8px;
    color: #1d1d1f;
  }

  .auth-subtitle {
    font-size: 14px;
    color: #86868b;
    text-align: center;
    margin-bottom: 32px;
  }

  .auth-footer {
    text-align: center;
    margin-top: 24px;
    font-size: 14px;
    color: #86868b;
  }

  .auth-footer a {
    color: #0071e3;
    text-decoration: none;
  }

  .auth-footer a:hover { text-decoration: underline; }

  input[type=email] {
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
  }

  input[type=email]:focus {
    border-color: #0071e3;
    box-shadow: 0 0 0 3px rgba(0,113,227,.12);
    background: #fff;
  }

  .history-table { width: 100%; }
  .history-table th { font-size: 11px; }
  .history-table td { font-size: 13px; }

  .type-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
  }

  .type-badge.dataset { background: #e8f0fe; color: #0071e3; }
  .type-badge.file { background: #f0e8fe; color: #7c3aed; }

  @media (max-width: 900px) {
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    .content-grid { grid-template-columns: 1fr; }
    .sidebar { display: none; }
    .dashboard-main { margin-left: 0; }
  }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    """Root route - redirect to dashboard if logged in, else to login."""
    user = get_current_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(err: str = "", msg: str = ""):
    """Login page."""
    flash = ""
    if err:
        flash = f'<div class="flash flash-err">{err}</div>'
    if msg:
        flash = f'<div class="flash flash-ok">{msg}</div>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login - LLM Eval</title>
  {STYLES}
</head>
<body>
<div class="auth-page">
  <div class="auth-card">
    <div class="auth-title">Welcome Back</div>
    <div class="auth-subtitle">Sign in to your LLM Eval account</div>
    {flash}
    
    <form method="post" action="/login">
      <label>Username or Email</label>
      <input type="text" name="username" placeholder="Enter your username" required>
      
      <label>Password</label>
      <div class="key-wrap">
        <input type="password" name="password" id="login-password" placeholder="Enter your password" required>
        <button type="button" class="key-toggle" onclick="toggleKey('login-password')">Show</button>
      </div>
      
      <button type="submit" class="btn btn-primary btn-block" style="margin-top:8px;">Sign In</button>
    </form>
    
    <div class="auth-footer">
      Don&apos;t have an account? <a href="/register">Create one</a>
    </div>
  </div>
</div>

<script>
function toggleKey(id) {{
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}}
</script>
</body>
</html>
"""


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle login form submission."""
    success, user_id = authenticate_user(username, password)
    
    if not success:
        return RedirectResponse("/login?err=Invalid+username+or+password", status_code=303)
    
    # Create session
    token = create_session(user_id)
    
    # Set cookie and redirect
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    return resp


@app.get("/register", response_class=HTMLResponse)
def register_page(err: str = ""):
    """Registration page."""
    flash = ""
    if err:
        flash = f'<div class="flash flash-err">{err}</div>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Register - LLM Eval</title>
  {STYLES}
</head>
<body>
<div class="auth-page">
  <div class="auth-card">
    <div class="auth-title">Create Account</div>
    <div class="auth-subtitle">Get started with LLM Eval</div>
    {flash}
    
    <form method="post" action="/register">
      <label>Username</label>
      <input type="text" name="username" placeholder="Choose a username" required minlength="3">
      
      <label>Email</label>
      <input type="email" name="email" placeholder="Enter your email" required>
      
      <label>Password</label>
      <div class="key-wrap">
        <input type="password" name="password" id="reg-password" placeholder="Choose a password" required minlength="6">
        <button type="button" class="key-toggle" onclick="toggleKey('reg-password')">Show</button>
      </div>
      
      <button type="submit" class="btn btn-primary btn-block" style="margin-top:8px;">Create Account</button>
    </form>
    
    <div class="auth-footer">
      Already have an account? <a href="/login">Sign in</a>
    </div>
  </div>
</div>

<script>
function toggleKey(id) {{
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}}
</script>
</body>
</html>
"""


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    response: Response,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """Handle registration form submission."""
    if len(username) < 3:
        return RedirectResponse("/register?err=Username+must+be+at+least+3+characters", status_code=303)
    
    if len(password) < 6:
        return RedirectResponse("/register?err=Password+must+be+at+least+6+characters", status_code=303)
    
    success, result = create_user(username, email, password)
    
    if not success:
        return RedirectResponse(f"/register?err={result.replace(' ', '+')}", status_code=303)
    
    return RedirectResponse("/login?msg=Account+created!+Please+sign+in.", status_code=303)


@app.get("/logout")
def logout(request: Request):
    """Logout and clear session."""
    token = request.cookies.get("session_token")
    if token:
        destroy_session(token)
    
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_token")
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """Main dashboard page."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    stats = get_user_stats(user["id"])
    history = get_evaluation_history(user["id"], limit=5)
    
    # Format last evaluation date
    last_eval = stats.get("last_evaluation")
    if last_eval:
        try:
            dt = datetime.fromisoformat(last_eval)
            last_eval = dt.strftime("%b %d, %Y")
        except:
            last_eval = "N/A"
    else:
        last_eval = "Never"
    
    # Build recent history rows
    history_rows = ""
    for h in history:
        ts = h.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            ts = dt.strftime("%b %d, %H:%M")
        except:
            pass
        
        eval_type = h.get("type", "unknown")
        type_class = "dataset" if eval_type == "dataset" else "file"
        filename = h.get("filename", "-") or "-"
        summary = h.get("results_summary", {})
        avg_score = summary.get("avg_score", 0)
        
        history_rows += f'''
        <tr>
          <td>{ts}</td>
          <td><span class="type-badge {type_class}">{eval_type}</span></td>
          <td>{filename[:30]}</td>
          <td><span class="score-badge-blue">{round(avg_score * 100) if avg_score else 0}</span></td>
        </tr>
        '''
    
    if not history_rows:
        history_rows = '<tr><td colspan="4" style="text-align:center;padding:24px;color:#86868b;">No evaluations yet. Run your first evaluation!</td></tr>'
    
    # API keys status
    api_keys = user.get("api_keys", {})
    providers = [
        ("groq", "Groq"),
        ("openai", "OpenAI"),
        ("google", "Google"),
        ("anthropic", "Anthropic")
    ]
    
    keys_html = ""
    for key, name in providers:
        configured = bool(api_keys.get(key))
        indicator = "configured" if configured else "missing"
        status_text = "Configured" if configured else "Not configured"
        keys_html += f'''
        <div class="api-key-status">
          <span class="key-indicator {indicator}"></span>
          <span style="flex:1;font-size:14px;">{name}</span>
          <span style="font-size:13px;color:#86868b;">{status_text}</span>
        </div>
        '''
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboard - LLM Eval</title>
  {STYLES}
  <style>
    .score-badge-blue {{
      background: #e6f0ff;
      color: #1d4ed8;
      padding: 4px 8px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 12px;
    }}
  </style>
</head>
<body>
<div class="dashboard-layout">
  {_sidebar_html("dashboard")}
  
  <main class="dashboard-main">
    <div class="dashboard-header">
      <div class="dashboard-title">Welcome back, {user["username"]}</div>
      <div class="user-menu">
        <div class="user-avatar">{user["username"][0].upper()}</div>
      </div>
    </div>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon blue">&#128202;</div>
        <div class="stat-value">{stats.get("total_evaluations", 0)}</div>
        <div class="stat-label">Total Evaluations</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green">&#128197;</div>
        <div class="stat-value">{last_eval}</div>
        <div class="stat-label">Last Evaluation</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon orange">&#128273;</div>
        <div class="stat-value">{stats.get("configured_providers", 0)}</div>
        <div class="stat-label">API Keys Configured</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon purple">&#9989;</div>
        <div class="stat-value">{round(stats.get("average_score", 0) * 100) if stats.get("average_score") else 0}%</div>
        <div class="stat-label">Average Score</div>
      </div>
    </div>
    
    <div class="content-grid">
      <div class="card">
        <div class="card-title">Recent Evaluations</div>
        <div class="results-wrap">
          <table class="history-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Type</th>
                <th>File</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {history_rows}
            </tbody>
          </table>
        </div>
        <div style="margin-top:16px;">
          <a href="/dashboard/history" class="btn btn-secondary" style="font-size:13px;padding:8px 14px;">View All History</a>
        </div>
      </div>
      
      <div>
        <div class="card">
          <div class="card-title">API Keys</div>
          {keys_html}
          <div style="margin-top:16px;">
            <a href="/dashboard/profile" class="btn btn-primary btn-block" style="font-size:13px;padding:8px 14px;">Manage API Keys</a>
          </div>
        </div>
        
        <div class="card">
          <div class="card-title">Quick Actions</div>
          <a href="/eval-mode" class="btn btn-primary btn-block" style="margin-bottom:8px;">
            Run New Evaluation
          </a>
          <a href="/dashboard/stats" class="btn btn-secondary btn-block">
            View Statistics
          </a>
        </div>
      </div>
    </div>
  </main>
</div>
</body>
</html>
"""


@app.get("/dashboard/profile", response_class=HTMLResponse)
def profile_page(request: Request, saved: str = "", err: str = ""):
    """Profile page with API key management."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    config = user.get("config", {})
    weights = config.get("weights", {})
    
    flash = ""
    if saved:
        flash = '<div class="flash flash-ok">Configuration saved successfully!</div>'
    if err:
        flash = f'<div class="flash flash-err">{err}</div>'
    
    def sel(v):
        return "selected" if config.get("selected_model") == v else ""
    
    weight_fields = [
        ("accuracy", "Accuracy"),
        ("relevance", "Relevance"),
        ("completeness", "Completeness"),
        ("consistency", "Consistency"),
        ("usefulness", "Usefulness"),
        ("structure", "Structure"),
        ("conciseness", "Conciseness"),
        ("latency", "Latency"),
        ("cost", "Cost"),
    ]
    
    w_inputs = ""
    for key, label in weight_fields:
        val = weights.get(key, 0)
        w_inputs += f'''
        <div class="weight-item">
          <label for="w_{key}">{label}</label>
          <input type="number" id="w_{key}" name="{key}" value="{val}" min="0" max="100" oninput="updateTotal()">
        </div>'''
    
    # API key status
    api_keys = user.get("api_keys", {})
    providers = [
        ("groq", "Groq API Key", "gsk_..."),
        ("openai", "OpenAI API Key", "sk-..."),
        ("google", "Google API Key", "AIza..."),
        ("anthropic", "Anthropic API Key", "sk-ant-..."),
    ]
    
    key_inputs = ""
    for key, label, placeholder in providers:
        configured = bool(api_keys.get(key))
        status = '<span style="color:#34c759;font-size:12px;margin-left:8px;">Configured</span>' if configured else ''
        key_inputs += f'''
        <label>{label}{status}</label>
        <div class="key-wrap">
          <input type="password" name="{key}" id="{key}_key" placeholder="{placeholder}" autocomplete="off">
          <button type="button" class="key-toggle" onclick="toggleKey('{key}_key')">Show</button>
        </div>
        '''
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>API Keys - LLM Eval</title>
  {STYLES}
</head>
<body>
<div class="dashboard-layout">
  {_sidebar_html("profile")}
  
  <main class="dashboard-main">
    <div class="dashboard-header">
      <div class="dashboard-title">API Keys & Configuration</div>
    </div>
    
    {flash}
    
    <form method="post" action="/dashboard/profile">
      <div class="card">
        <div class="card-title">API Keys</div>
        <p style="font-size:13px;color:#86868b;margin-bottom:16px;">Enter a new key to add or replace existing keys. Leave blank to keep current keys.</p>
        {key_inputs}
      </div>
      
      <div class="card">
        <div class="card-title">Model Selection</div>
        <label>Default Model</label>
        <select name="model">
          <option value="groq" {sel('groq')}>Groq (Llama 3.3-70b)</option>
          <option value="gpt-4o-mini" {sel('gpt-4o-mini')}>GPT-4o mini</option>
          <option value="gpt-4o" {sel('gpt-4o')}>GPT-4o</option>
          <option value="gemini-1.5-pro" {sel('gemini-1.5-pro')}>Gemini 1.5 Pro</option>
          <option value="gemini-1.5-flash" {sel('gemini-1.5-flash')}>Gemini 1.5 Flash</option>
          <option value="claude-3-sonnet" {sel('claude-3-sonnet')}>Claude 3 Sonnet</option>
          <option value="claude-3-haiku" {sel('claude-3-haiku')}>Claude 3 Haiku</option>
        </select>
      </div>
      
      <div class="card">
        <div class="card-title">Evaluation Weights <small style="font-size:11px;font-weight:400;text-transform:none;">(must sum to 100)</small></div>
        <div class="weight-grid">
          {w_inputs}
        </div>
        <div class="weight-total">Total: <span id="total-display">-</span></div>
      </div>
      
      <button type="submit" class="btn btn-primary btn-block">Save Configuration</button>
    </form>
  </main>
</div>

<script>
function toggleKey(id) {{
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}}

function updateTotal() {{
  const fields = ['accuracy','relevance','completeness','consistency','usefulness','structure','conciseness','latency','cost'];
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


@app.post("/dashboard/profile", response_class=HTMLResponse)
async def profile_save(
    request: Request,
    openai: str = Form(""),
    google: str = Form(""),
    anthropic: str = Form(""),
    groq: str = Form(""),
    model: str = Form(...),
    accuracy: int = Form(...),
    relevance: int = Form(...),
    completeness: int = Form(...),
    consistency: int = Form(...),
    usefulness: int = Form(0),
    structure: int = Form(0),
    conciseness: int = Form(0),
    latency: int = Form(...),
    cost: int = Form(...),
):
    """Save user profile configuration."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    user_id = user["id"]
    
    total = accuracy + relevance + completeness + consistency + usefulness + structure + conciseness + latency + cost
    
    if total != 100:
        return RedirectResponse(f"/dashboard/profile?err=Weights+must+sum+to+100+(got+{total})", status_code=303)
    
    # Update API keys
    if openai.strip():
        update_user_api_keys(user_id, "openai", openai)
    if google.strip():
        update_user_api_keys(user_id, "google", google)
    if anthropic.strip():
        update_user_api_keys(user_id, "anthropic", anthropic)
    if groq.strip():
        update_user_api_keys(user_id, "groq", groq)
    
    # Update config
    update_user_config(user_id, {
        "selected_model": model,
        "weights": {
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
    })
    
    # Also update global config for pipeline compatibility
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
    
    return RedirectResponse("/dashboard/profile?saved=1", status_code=303)


@app.get("/dashboard/history", response_class=HTMLResponse)
def history_page(request: Request):
    """Evaluation history page."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    history = get_evaluation_history(user["id"], limit=100)
    
    rows = ""
    for h in history:
        ts = h.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            ts = dt.strftime("%Y-%m-%d %H:%M")
        except:
            pass
        
        eval_type = h.get("type", "unknown")
        type_class = "dataset" if eval_type == "dataset" else "file"
        filename = h.get("filename", "-") or "-"
        summary = h.get("results_summary", {})
        avg_score = summary.get("avg_score", 0)
        records = summary.get("records", 0)
        
        rows += f'''
        <tr>
          <td>{ts}</td>
          <td><span class="type-badge {type_class}">{eval_type}</span></td>
          <td>{filename[:40]}</td>
          <td>{records}</td>
          <td><span class="score-badge-blue">{round(avg_score * 100) if avg_score else 0}%</span></td>
        </tr>
        '''
    
    if not rows:
        rows = '<tr><td colspan="5" style="text-align:center;padding:40px;color:#86868b;">No evaluation history yet. Run your first evaluation!</td></tr>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>History - LLM Eval</title>
  {STYLES}
  <style>
    .score-badge-blue {{
      background: #e6f0ff;
      color: #1d4ed8;
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 12px;
    }}
  </style>
</head>
<body>
<div class="dashboard-layout">
  {_sidebar_html("history")}
  
  <main class="dashboard-main">
    <div class="dashboard-header">
      <div class="dashboard-title">Evaluation History</div>
      <a href="/eval-mode" class="btn btn-primary">Run New Evaluation</a>
    </div>
    
    <div class="card">
      <div class="card-title">All Evaluations</div>
      <div class="results-wrap">
        <table class="history-table">
          <thead>
            <tr>
              <th>Date & Time</th>
              <th>Type</th>
              <th>File</th>
              <th>Records</th>
              <th>Avg Score</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </div>
  </main>
</div>
</body>
</html>
"""


@app.get("/dashboard/stats", response_class=HTMLResponse)
def stats_page(request: Request):
    """Statistics page with charts."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    stats = get_user_stats(user["id"])
    history = get_evaluation_history(user["id"], limit=50)
    
    # Prepare data for charts
    model_usage = stats.get("model_usage", {})
    by_type = stats.get("evaluations_by_type", {"dataset": 0, "file": 0})
    
    # Score distribution
    scores = []
    for h in history:
        summary = h.get("results_summary", {})
        if "avg_score" in summary:
            scores.append(round(summary["avg_score"] * 100))
    
    # Model usage chart data
    model_labels = list(model_usage.keys()) if model_usage else ["No data"]
    model_values = list(model_usage.values()) if model_usage else [0]
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Statistics - LLM Eval</title>
  {STYLES}
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<div class="dashboard-layout">
  {_sidebar_html("stats")}
  
  <main class="dashboard-main">
    <div class="dashboard-header">
      <div class="dashboard-title">Statistics & Analytics</div>
    </div>
    
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon blue">&#128202;</div>
        <div class="stat-value">{stats.get("total_evaluations", 0)}</div>
        <div class="stat-label">Total Evaluations</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green">&#9989;</div>
        <div class="stat-value">{round(stats.get("average_score", 0) * 100) if stats.get("average_score") else 0}%</div>
        <div class="stat-label">Average Score</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon orange">&#128200;</div>
        <div class="stat-value">{round(stats.get("highest_score", 0) * 100) if stats.get("highest_score") else 0}%</div>
        <div class="stat-label">Highest Score</div>
      </div>
      <div class="stat-card">
        <div class="stat-icon purple">&#128201;</div>
        <div class="stat-value">{round(stats.get("lowest_score", 0) * 100) if stats.get("lowest_score") else 0}%</div>
        <div class="stat-label">Lowest Score</div>
      </div>
    </div>
    
    <div class="content-grid">
      <div class="card">
        <div class="card-title">Evaluation Type Distribution</div>
        <canvas id="typeChart" height="200"></canvas>
      </div>
      
      <div class="card">
        <div class="card-title">Model Usage</div>
        <canvas id="modelChart" height="200"></canvas>
      </div>
    </div>
    
    <div class="card" style="margin-top:24px;">
      <div class="card-title">Score Trend (Last 20 Evaluations)</div>
      <canvas id="scoreChart" height="100"></canvas>
    </div>
  </main>
</div>

<script>
// Type distribution chart
new Chart(document.getElementById('typeChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Dataset', 'File Upload'],
    datasets: [{{
      data: [{by_type.get("dataset", 0)}, {by_type.get("file", 0)}],
      backgroundColor: ['#0071e3', '#7c3aed'],
      borderWidth: 0
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{
        position: 'bottom'
      }}
    }}
  }}
}});

// Model usage chart
new Chart(document.getElementById('modelChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(model_labels)},
    datasets: [{{
      label: 'Evaluations',
      data: {json.dumps(model_values)},
      backgroundColor: '#0071e3',
      borderRadius: 6
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{
        display: false
      }}
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        ticks: {{
          stepSize: 1
        }}
      }}
    }}
  }}
}});

// Score trend chart
const scores = {json.dumps(scores[-20:] if scores else [])};
new Chart(document.getElementById('scoreChart'), {{
  type: 'line',
  data: {{
    labels: scores.map((_, i) => 'Eval ' + (i + 1)),
    datasets: [{{
      label: 'Score (%)',
      data: scores,
      borderColor: '#0071e3',
      backgroundColor: 'rgba(0, 113, 227, 0.1)',
      fill: true,
      tension: 0.3
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{
        display: false
      }}
    }},
    scales: {{
      y: {{
        beginAtZero: true,
        max: 100
      }}
    }}
  }}
}});
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Config page (for backwards compatibility - now redirects)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request, saved: str = "", err: str = ""):
    """Old config page - redirects to dashboard profile."""
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dashboard/profile", status_code=302)




# ─────────────────────────────────────────────────────────────────────────────
# Eval mode chooser
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/eval-mode", response_class=HTMLResponse)
def eval_mode_page(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Eval - Run Evaluation</title>
  {STYLES}
</head>
<body>
<div class="dashboard-layout">
  {_sidebar_html("eval")}
  
  <main class="dashboard-main">
    <div class="dashboard-header">
      <div class="dashboard-title">Run Evaluation</div>
    </div>

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
  </main>
</div>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Dataset pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/run-dataset", response_class=HTMLResponse)
def run_dataset(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    try:
        _run_pipeline_dataset()
        
        # Log to user history
        try:
            with open("scored_results.json", "r") as f:
                data = json.load(f)
            results = data if isinstance(data, list) else data.get("results", [])
            scores = [r.get("final_score", 0) for r in results if r.get("final_score")]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            add_evaluation_history(
                user["id"],
                eval_type="dataset",
                filename="dataset.xlsx",
                results_summary={
                    "records": len(results),
                    "avg_score": avg_score
                }
            )
        except Exception:
            pass  # Don't fail if history logging fails
        
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
def results_dataset(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
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
def results_file(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
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
            is_file=True
        )

    except Exception as e:
        return _error_page(str(e))
# ─────────────────────────────────────────────────────────────────────────────
# File upload pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/run-file", response_class=HTMLResponse)
async def run_file(request: Request, file: UploadFile = File(...)):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
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
        
        # Log to user history
        try:
            with open("scored_results.json", "r") as f:
                data = json.load(f)
            result_list = data if isinstance(data, list) else data.get("results", [])
            scores = [r.get("final_score", 0) for r in result_list if r.get("final_score")]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            add_evaluation_history(
                user["id"],
                eval_type="file",
                filename=file.filename,
                results_summary={
                    "records": len(result_list),
                    "avg_score": avg_score
                }
            )
        except Exception:
            pass  # Don't fail if history logging fails
        
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
def report_file(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
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
def show_report(request: Request):
    user = require_auth(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    try:
        with open("output/llm_eval_report.html", "r") as f:
            return f.read()
    except Exception:
        return HTMLResponse(
            "<h3 style='font-family:sans-serif;padding:40px'>Report not found - run evaluation first.</h3>"
        )


# -------------------------------
# REMOVE THIS (NOT NEEDED)
# -------------------------------
# @app.get("/run")
# def legacy_run():
#     return RedirectResponse("/eval-mode", status_code=302)
