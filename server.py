"""
NotebookLM Webapp — FastAPI backend
Wraps the `notebooklm` CLI and serves a single-page frontend.
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
STORE_FILE      = BASE_DIR / "notebooks_store.json"
REPORTS_FILE    = BASE_DIR / "reports_store.json"
CUSTOM_TPL_FILE = BASE_DIR / "custom_templates.json"
STATIC_DIR      = BASE_DIR / "static"

ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

app = FastAPI(title="NotebookLM Manager", version="1.0.0")

# ── helpers ───────────────────────────────────────────────────────────────────

def run_cli(args: list[str], timeout: int = 120) -> dict:
    """Execute notebooklm CLI, return {ok, stdout, stderr, returncode}."""
    try:
        r = subprocess.run(
            ["notebooklm"] + args,
            capture_output=True, text=True, env=ENV,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "CLI timeout", "returncode": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "returncode": -1}


def parse_json_output(raw: str) -> dict | list | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def extract_notebook_id(url_or_id: str) -> str:
    """Accept full URL or bare UUID."""
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", url_or_id)
    return m.group(1) if m else url_or_id


def load_store() -> list[dict]:
    if STORE_FILE.exists():
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_store(notebooks: list[dict]) -> None:
    STORE_FILE.write_text(json.dumps(notebooks, ensure_ascii=False, indent=2), encoding="utf-8")


def load_reports() -> list[dict]:
    if REPORTS_FILE.exists():
        with open(REPORTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_reports(reports: list[dict]) -> None:
    REPORTS_FILE.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")

# ── report templates ──────────────────────────────────────────────────────────

REPORT_TEMPLATES = {
    "investment_brief": {
        "id": "investment_brief",
        "name": "Real Estate Investment Brief",
        "icon": "📈",
        "description": "Financial analysis, ROI potential, developer track record, pricing, and investment timeline.",
        "questions": [
            "What is the total investment value, land area, number of units, and pricing range of the project?",
            "Describe the developer's financial history, capital structure, and track record.",
            "What is the payment policy, bank loan coverage, and financial incentives for buyers?",
            "What is the project development timeline from groundbreaking to handover?",
            "What are the key value drivers and ROI potential for real estate investors?",
        ],
        "sections": ["Executive Summary", "Developer Profile", "Financial Structure", "Timeline & Milestones", "Investment Outlook"]
    },
    "market_intelligence": {
        "id": "market_intelligence",
        "name": "Market Intelligence Report",
        "icon": "🔍",
        "description": "Competitive positioning, unique selling points, target market, and regional growth drivers.",
        "questions": [
            "What unique design or product features differentiate this project from competitors in the same market?",
            "Who is the target buyer profile and what residential demand does this project address?",
            "What are the location advantages, infrastructure developments, and regional growth catalysts?",
            "How do expert analysts and the media view this project's competitive position?",
            "What amenities, lifestyle features, and wellness offerings are included?",
        ],
        "sections": ["Market Position", "Unique Value Proposition", "Target Audience", "Location & Infrastructure", "Expert Opinions"]
    },
    "due_diligence": {
        "id": "due_diligence",
        "name": "Risk & Due Diligence Report",
        "icon": "⚖️",
        "description": "Legal compliance, construction risks, developer credibility, and buyer protection checklist.",
        "questions": [
            "What are the key legal documents buyers must verify before purchasing (land certificate, construction permit, sales eligibility)?",
            "What are the specific legal risks related to land classification, pink book issuance, and sales guarantee?",
            "What is the developer's history of financial difficulties and how have they been resolved?",
            "What international partners and contractors are involved, and how do they mitigate execution risk?",
            "What contract clauses and buyer protection mechanisms should investors scrutinize?",
        ],
        "sections": ["Legal Framework", "Developer Risk Profile", "Construction Risk", "Contract Review", "Due Diligence Checklist"]
    }
}

# ── custom template helpers ───────────────────────────────────────────────────

def load_custom_templates() -> list[dict]:
    if CUSTOM_TPL_FILE.exists():
        with open(CUSTOM_TPL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_custom_templates(templates: list[dict]) -> None:
    CUSTOM_TPL_FILE.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")


# ── auth ──────────────────────────────────────────────────────────────────────

USERS = {
    "admin":  {"password": "admin123", "role": "admin"},
    "user1":  {"password": "user123",  "role": "user"},
    "user2":  {"password": "user321",  "role": "user"},
}

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
def login(req: LoginRequest):
    user = USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(401, "Invalid username or password.")
    return {"username": req.username, "role": user["role"]}

# ── models ────────────────────────────────────────────────────────────────────

class AddNotebookRequest(BaseModel):
    url: str
    title: Optional[str] = None
    tags: Optional[list[str]] = []

class AddSourceRequest(BaseModel):
    url: str

class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None

class ResearchRequest(BaseModel):
    query: str
    mode: str = "fast"

class ReportRequest(BaseModel):
    template_id: str
    notebook_ids: list[str]

class GenerateRequest(BaseModel):
    type: str          # audio | video | report | quiz | flashcards | mind-map
    instructions: Optional[str] = ""
    format: Optional[str] = ""
    notebook_id: str

# ── notebook endpoints ────────────────────────────────────────────────────────

@app.get("/api/notebooks")
def list_notebooks():
    return load_store()


@app.post("/api/notebooks")
def add_notebook(req: AddNotebookRequest):
    nb_id = extract_notebook_id(req.url)
    if not nb_id:
        raise HTTPException(400, "Could not parse notebook ID from URL.")

    store = load_store()
    if any(n["id"] == nb_id for n in store):
        raise HTTPException(409, "Notebook already in store.")

    # fetch real title from CLI
    title = req.title
    if not title:
        r = run_cli(["list", "--json"])
        if r["ok"]:
            data = parse_json_output(r["stdout"])
            if data and "notebooks" in data:
                match = next((n for n in data["notebooks"] if n["id"] == nb_id), None)
                title = match["title"] if match else nb_id
        title = title or nb_id

    entry = {
        "id": nb_id,
        "title": title,
        "url": req.url,
        "tags": req.tags or [],
        "added_at": datetime.now().strftime("%Y-%m-%d"),
    }
    store.append(entry)
    save_store(store)
    return entry


@app.delete("/api/notebooks/{nb_id}")
def remove_notebook(nb_id: str):
    store = load_store()
    new_store = [n for n in store if n["id"] != nb_id]
    if len(new_store) == len(store):
        raise HTTPException(404, "Notebook not found in store.")
    save_store(new_store)
    return {"removed": nb_id}

# ── source endpoints ──────────────────────────────────────────────────────────

@app.get("/api/notebooks/{nb_id}/sources")
def get_sources(nb_id: str):
    r = run_cli(["source", "list", "--json", "-n", nb_id])
    if not r["ok"]:
        raise HTTPException(500, r["stderr"] or r["stdout"])
    data = parse_json_output(r["stdout"])
    return data or {"sources": [], "count": 0}


@app.post("/api/notebooks/{nb_id}/sources")
def add_source(nb_id: str, req: AddSourceRequest):
    r = run_cli(["source", "add", req.url, "--json", "-n", nb_id], timeout=60)
    if not r["ok"]:
        raise HTTPException(500, r["stderr"] or r["stdout"])
    data = parse_json_output(r["stdout"])
    return data or {"status": "added"}


@app.delete("/api/notebooks/{nb_id}/sources/{source_id}")
def delete_source(nb_id: str, source_id: str):
    r = run_cli(["source", "delete", source_id, "-n", nb_id])
    if not r["ok"]:
        raise HTTPException(500, r["stderr"] or r["stdout"])
    return {"removed": source_id}

# ── chat endpoint ─────────────────────────────────────────────────────────────

@app.post("/api/notebooks/{nb_id}/chat")
def chat(nb_id: str, req: ChatRequest):
    args = ["ask", req.question, "--json", "-n", nb_id]
    if req.conversation_id:
        args += ["-c", req.conversation_id]
    r = run_cli(args, timeout=90)
    if not r["ok"]:
        raise HTTPException(500, r["stderr"] or r["stdout"])
    data = parse_json_output(r["stdout"])
    return data or {"answer": r["stdout"]}

# ── research endpoint ─────────────────────────────────────────────────────────

@app.post("/api/notebooks/{nb_id}/research")
def add_research(nb_id: str, req: ResearchRequest):
    args = ["source", "add-research", req.query, "--mode", req.mode, "-n", nb_id]
    if req.mode == "fast":
        args.append("--import-all")
    else:
        args.append("--no-wait")
    r = run_cli(args, timeout=180)
    return {
        "ok": r["ok"],
        "message": r["stdout"] or r["stderr"],
        "mode": req.mode
    }

# ── report endpoint ───────────────────────────────────────────────────────────

class SaveTemplateRequest(BaseModel):
    id: Optional[str] = None    # omit to auto-generate
    name: str
    icon: str = "📝"
    description: str = ""
    questions: list[str]
    sections: list[str]


@app.get("/api/report-templates")
def get_templates():
    builtin  = list(REPORT_TEMPLATES.values())
    custom   = load_custom_templates()
    # mark origin so frontend can distinguish
    for t in builtin:
        t["builtin"] = True
    for t in custom:
        t["builtin"] = False
    return builtin + custom


@app.post("/api/report-templates/custom")
def save_custom_template(req: SaveTemplateRequest):
    import uuid as _uuid
    customs = load_custom_templates()
    tpl_id = req.id or f"custom_{_uuid.uuid4().hex[:8]}"
    # upsert — replace if same id exists
    customs = [t for t in customs if t["id"] != tpl_id]
    entry = {
        "id":          tpl_id,
        "name":        req.name,
        "icon":        req.icon,
        "description": req.description,
        "questions":   req.questions,
        "sections":    req.sections,
        "builtin":     False,
    }
    customs.append(entry)
    save_custom_templates(customs)
    return entry


@app.delete("/api/report-templates/custom/{tpl_id}")
def delete_custom_template(tpl_id: str):
    customs = load_custom_templates()
    new_customs = [t for t in customs if t["id"] != tpl_id]
    if len(new_customs) == len(customs):
        raise HTTPException(404, "Custom template not found.")
    save_custom_templates(new_customs)
    return {"removed": tpl_id}


@app.post("/api/reports/generate")
def generate_report(req: ReportRequest):
    # look up in built-ins first, then custom
    template = REPORT_TEMPLATES.get(req.template_id)
    if not template:
        custom = {t["id"]: t for t in load_custom_templates()}
        template = custom.get(req.template_id)
    if not template:
        raise HTTPException(400, f"Unknown template: {req.template_id}")
    if not req.notebook_ids:
        raise HTTPException(400, "Select at least one notebook.")

    vi_suffix = " Hãy trả lời hoàn toàn bằng tiếng Việt, sử dụng định dạng markdown rõ ràng."

    results = {}
    for nb_id in req.notebook_ids:
        nb_answers = []
        for question in template["questions"]:
            r = run_cli(["ask", question + vi_suffix, "--json", "-n", nb_id], timeout=90)
            if r["ok"]:
                data = parse_json_output(r["stdout"])
                answer = data.get("answer", "") if data else r["stdout"]
            else:
                answer = f"[Error: {r['stderr'][:200]}]"
            nb_answers.append({"question": question, "answer": answer})
        results[nb_id] = nb_answers

    # get notebook titles
    store = load_store()
    nb_titles = {n["id"]: n["title"] for n in store}

    return {
        "template": template,
        "generated_at": datetime.now().isoformat(),
        "notebooks": [
            {
                "id": nb_id,
                "title": nb_titles.get(nb_id, nb_id),
                "answers": results[nb_id],
            }
            for nb_id in req.notebook_ids
        ]
    }


class SaveReportRequest(BaseModel):
    report: dict          # the full report object from generate
    name: Optional[str] = None   # optional custom name


@app.get("/api/reports/saved")
def list_saved_reports():
    return load_reports()


@app.post("/api/reports/saved")
def save_report(req: SaveReportRequest):
    reports = load_reports()
    import uuid as _uuid
    entry = {
        "id": str(_uuid.uuid4()),
        "name": req.name or req.report.get("template", {}).get("name", "Report"),
        "saved_at": datetime.now().isoformat(),
        "report": req.report,
    }
    reports.insert(0, entry)   # newest first
    save_reports(reports)
    return entry


@app.delete("/api/reports/saved/{report_id}")
def delete_saved_report(report_id: str):
    reports = load_reports()
    new_reports = [r for r in reports if r["id"] != report_id]
    if len(new_reports) == len(reports):
        raise HTTPException(404, "Report not found.")
    save_reports(new_reports)
    return {"removed": report_id}

# ── generate artifacts ────────────────────────────────────────────────────────

@app.post("/api/notebooks/{nb_id}/generate")
def generate_artifact(nb_id: str, req: GenerateRequest):
    type_map = {
        "audio":      ["generate", "audio"],
        "report":     ["generate", "report"],
        "quiz":       ["generate", "quiz"],
        "flashcards": ["generate", "flashcards"],
        "mind-map":   ["generate", "mind-map"],
    }
    base_cmd = type_map.get(req.type)
    if not base_cmd:
        raise HTTPException(400, f"Unknown type: {req.type}")

    args = base_cmd + ["--json", "-n", nb_id, "--language", "vi"]
    if req.instructions:
        args.insert(2, req.instructions)
    if req.format:
        args += ["--format", req.format]

    r = run_cli(args, timeout=60)
    data = parse_json_output(r["stdout"])
    return {
        "ok": r["ok"],
        "data": data,
        "raw": r["stdout"][:500] if not data else None,
        "error": r["stderr"][:300] if not r["ok"] else None,
    }


@app.get("/api/notebooks/{nb_id}/artifacts")
def list_artifacts(nb_id: str):
    r = run_cli(["artifact", "list", "--json", "-n", nb_id])
    if not r["ok"]:
        raise HTTPException(500, r["stderr"] or r["stdout"])
    data = parse_json_output(r["stdout"])
    return data or {"artifacts": []}

# ── claude CLI helpers ────────────────────────────────────────────────────────

import asyncio
import shutil

def _claude_bin() -> str:
    """Return the path to the claude CLI binary, or raise."""
    path = shutil.which("claude")
    if path:
        return path
    raise HTTPException(500, "claude CLI not found on PATH. Run: npm install -g @anthropic-ai/claude-code")


@app.get("/api/claude/auth-status")
def claude_auth_status():
    """Check if claude CLI is available and authenticated."""
    path = shutil.which("claude")
    if not path:
        return {"authenticated": False, "method": "none", "label": "claude CLI not installed"}
    # Quick auth check
    r = subprocess.run(
        [path, "--version"],
        capture_output=True, text=True, timeout=5, env=ENV,
    )
    if r.returncode == 0:
        return {"authenticated": True, "method": "claude_code", "label": f"Claude Code CLI"}
    return {"authenticated": False, "method": "none", "label": "claude CLI error"}


# ── claude streaming chat endpoint ────────────────────────────────────────────

MAX_FILE_MB = 20

@app.post("/api/claude/chat")
async def claude_chat_stream(
    question: str = Form(...),
    history: str  = Form("[]"),
    file: Optional[UploadFile] = File(None),
):
    """
    Stream a Claude response via the claude CLI (-p flag).
    Uses Server-Sent Events so the frontend can render tokens in real-time.
    """
    claude = _claude_bin()

    # parse history
    try:
        prior: list[dict] = json.loads(history)
    except Exception:
        prior = []

    # build plain-text prompt with conversation context
    parts = [
        "You are an expert research and business analyst assistant. "
        "Always respond in Vietnamese (Tiếng Việt) unless the user explicitly asks for another language. "
        "Use markdown formatting for clarity.",
        "",
    ]

    for turn in prior:
        role    = "Human"    if turn.get("role") == "user"      else "Assistant"
        content = turn.get("content", "")
        if content:
            parts.append(f"{role}: {content}")

    # handle file attachment — inline text content in the prompt
    file_bytes: Optional[bytes] = None
    if file and file.filename:
        file_bytes = await file.read()
        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            raise HTTPException(413, f"File too large ({size_mb:.1f} MB). Max {MAX_FILE_MB} MB.")
        try:
            text_content = file_bytes.decode("utf-8", errors="replace")
            parts.append(f"[Attached file: {file.filename}]\n```\n{text_content[:60_000]}\n```")
        except Exception:
            pass  # binary file with no text — skip

    parts.append(f"Human: {question}")
    parts.append("Assistant:")

    full_prompt = "\n".join(parts)

    async def stream_sse():
        try:
            proc = await asyncio.create_subprocess_exec(
                claude, "-p", full_prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=ENV,
            )

            while True:
                chunk = await proc.stdout.read(512)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                yield f"data: {json.dumps({'text': text})}\n\n"

            await proc.wait()

            if proc.returncode != 0:
                err_bytes = await proc.stderr.read()
                err = err_bytes.decode("utf-8", errors="replace")[:400]
                yield f"data: {json.dumps({'error': err})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_sse(), media_type="text/event-stream")


# ── static files ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860, reload=True)
