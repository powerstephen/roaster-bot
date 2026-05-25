import asyncio
import csv
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import SERPAPI_KEY
from scraper.engine import run_roaster, audit_url

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = FastAPI(title="Roaster Bot")

# ── State ─────────────────────────────────────────────────────────────────────
_running = False
_task = None
_results: list[dict] = []
_buffer: list[dict] = []
_subscribers: list[asyncio.Queue] = []


async def _broadcast(ev: dict):
    _buffer.append(ev)
    if len(_buffer) > 500: _buffer[:] = _buffer[-400:]
    for q in list(_subscribers):
        try: q.put_nowait(ev)
        except asyncio.QueueFull: pass


# ── Models ────────────────────────────────────────────────────────────────────
class RoastParams(BaseModel):
    industry: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


class SingleParams(BaseModel):
    url: str
    name: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((UI_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/api/roast")
async def start_roast(params: RoastParams):
    global _running, _task, _results, _buffer

    if _running:
        raise HTTPException(409, "Already running")
    if not SERPAPI_KEY:
        raise HTTPException(400, "SERPAPI_KEY not configured in .env")

    _running = True
    _results = []
    _buffer = []

    async def _job():
        global _running, _results

        async def log_cb(msg):
            await _broadcast({"type": "log", "msg": msg})

        try:
            results = await run_roaster(
                params.industry, params.location, params.limit,
                SERPAPI_KEY, log_cb
            )
            _results = results
            status = "completed"
        except Exception as e:
            results = []
            status = "error"
            await _broadcast({"type": "log", "msg": f"ERROR: {e}"})

        await _broadcast({
            "type": "done",
            "status": status,
            "count": len(results),
            "results": results,
        })
        _running = False

    _task = asyncio.create_task(_job())
    return {"ok": True}


@app.post("/api/roast/single")
async def single_roast(params: SingleParams):
    result = await audit_url(params.url)
    return {**result, "name": params.name, "url": params.url}


@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    for ev in _buffer:
        try: q.put_nowait(ev)
        except: pass
    _subscribers.append(q)

    async def gen():
        try:
            while True:
                if await request.is_disconnected(): break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": ev["type"], "data": json.dumps(ev)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            if q in _subscribers: _subscribers.remove(q)

    return EventSourceResponse(gen())


@app.get("/api/status")
async def status():
    return {"running": _running, "count": len(_results)}


@app.get("/api/results")
async def get_results():
    return _results


@app.get("/api/export.csv")
async def export_csv():
    if not _results:
        raise HTTPException(404, "No results")

    buf = io.StringIO()
    fields = [
        "priority_score", "name", "category", "address", "phone", "website",
        "rating", "reviews", "biz_quality",
        "opportunity_score", "health_score", "grade",
        "load_time", "is_ssl", "critical_count", "needs_work_count",
        "speed", "mobile", "cta", "trust", "booking", "social", "seo", "ssl_score",
        "google_url",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()

    for r in _results:
        dims = r.get("dimensions", {})
        writer.writerow({
            "priority_score": r.get("priority_score", 0),
            "name": r.get("name", ""),
            "category": r.get("category", ""),
            "address": r.get("address", ""),
            "phone": r.get("phone", ""),
            "website": r.get("website", ""),
            "rating": r.get("rating", ""),
            "reviews": r.get("reviews", ""),
            "biz_quality": r.get("biz_quality", 0),
            "opportunity_score": r.get("opportunity_score", 0),
            "health_score": r.get("health_score", 0),
            "grade": r.get("grade", ""),
            "load_time": r.get("load_time", ""),
            "is_ssl": r.get("is_ssl", ""),
            "critical_count": r.get("critical_count", 0),
            "needs_work_count": r.get("needs_work_count", 0),
            "speed": dims.get("speed", {}).get("score", ""),
            "mobile": dims.get("mobile", {}).get("score", ""),
            "cta": dims.get("cta", {}).get("score", ""),
            "trust": dims.get("trust", {}).get("score", ""),
            "booking": dims.get("booking", {}).get("score", ""),
            "social": dims.get("social", {}).get("score", ""),
            "seo": dims.get("seo", {}).get("score", ""),
            "ssl_score": dims.get("ssl", {}).get("score", ""),
            "google_url": r.get("google_url", ""),
        })

    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="roaster_bot_results.csv"'}
    )


if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


# ── Report route ──────────────────────────────────────────────────────────────

import json as _json2
from fastapi.responses import HTMLResponse as _HTMLResponse

@app.get("/report/{idx}", response_class=_HTMLResponse)
async def report(idx: int):
    if idx < 0 or idx >= len(_results):
        raise HTTPException(404, "Result not found — run a search first")

    biz = _results[idx]
    report_html = (UI_DIR / "report.html").read_text(encoding="utf-8")

    # Inject data
    data_js = f"window.REPORT_DATA = {_json2.dumps(biz)};"
    report_html = report_html.replace(
        "const reportData=window.REPORT_DATA||",
        f"{data_js}\nconst reportData=window.REPORT_DATA||"
    )
    return _HTMLResponse(report_html)
