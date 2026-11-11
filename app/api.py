"""HTTP surface. One process serves the API and the built front end."""
from __future__ import annotations

import base64
import json
import re

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, store
from .otari import Otari, OtariError
from .pipeline import analyze

app = FastAPI(title="Fine Print", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "base_url": config.OTARI_BASE_URL,
        "key_present": bool(config.OTARI_API_KEY),
        "reader": config.READER_MODEL or "auto",
        "checker": config.CHECKER_MODEL or "auto",
        "guardrail": f"{config.GUARDRAIL_PROFILE}:{config.GUARDRAIL_MODE}",
        "mcp_url": config.MCP_URL or "direct",
        "budget_usd": config.MONTHLY_BUDGET_USD,
    }


@app.get("/api/models")
def models() -> dict:
    try:
        client = Otari()
        rows = client.catalog()
        return {"count": len(rows), "models": rows}
    except OtariError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/budget")
def budget(end_user: str = "household") -> dict:
    spent = store.month_spend(end_user)
    return {
        "end_user": end_user,
        "spent_usd": round(spent, 6),
        "limit_usd": config.MONTHLY_BUDGET_USD,
        "remaining_usd": round(max(0.0, config.MONTHLY_BUDGET_USD - spent), 6),
    }


@app.get("/api/history")
def history() -> dict:
    return {"items": store.recent(12)}


@app.get("/api/analysis/{analysis_id}")
def analysis(analysis_id: str) -> dict:
    found = store.get_analysis(analysis_id)
    if not found:
        raise HTTPException(status_code=404, detail="no such analysis")
    return found


@app.post("/api/analyze")
async def analyze_upload(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    end_user: str = Form(default="household"),
) -> JSONResponse:
    data_url = ""
    if file is not None:
        raw = await file.read()
        if len(raw) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="that file is too large")
        mime = file.content_type or "image/jpeg"
        if mime not in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/gif"}:
            raise HTTPException(status_code=415, detail="send a photo of the paper (jpg, png, webp) or paste the text")
        data_url = f"data:{mime};base64," + base64.b64encode(raw).decode()
    if not data_url and not text.strip():
        raise HTTPException(status_code=400, detail="send a photo or paste the text")
    try:
        result = analyze(text=text.strip(), image_data_url=data_url, end_user=end_user)
    except OtariError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "status": exc.status, "code": exc.code})
    return JSONResponse(result)


@app.post("/api/analyze/json")
def analyze_json(payload: dict) -> JSONResponse:
    """Used by the smoke test and by anything that already has text."""
    try:
        result = analyze(text=str(payload.get("text") or ""), end_user=str(payload.get("end_user") or "household"))
    except OtariError as exc:
        raise HTTPException(status_code=502, detail={"message": str(exc), "status": exc.status, "code": exc.code})
    return JSONResponse(result)


SAMPLES = [
    {"name": "bill_clean", "label": "A water bill that is exactly what it claims", "note": "the happy path"},
    {"name": "bill_doctored", "label": "A water bill whose total does not add up", "note": "wrong sum, wrong account"},
    {"name": "notice_injection", "label": "A final notice with instructions in it", "note": "aimed at the assistant, not at you"},
    {"name": "letter_insurance", "label": "A hospital letter that asks for no money", "note": "documents, not payment"},
]


@app.get("/api/samples")
def samples() -> dict:
    items = []
    for row in SAMPLES:
        image = config.FIXTURES / f"{row['name']}.png"
        if image.exists():
            items.append({**row, "image": f"/fixtures/{row['name']}.png"})
    return {"items": items}


@app.get("/issuer/{slug}")
def issuer_page(slug: str):
    """The published payment page of a demo issuer, served locally so a demo needs no internet."""
    if not re.fullmatch(r"[a-z0-9.-]{3,60}", slug):
        raise HTTPException(status_code=400, detail="bad slug")
    path = config.ROOT / "app" / "data" / "issuers" / f"{slug}.txt"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no such issuer page")
    return FileResponse(path, media_type="text/plain")


if config.FIXTURES.exists():
    app.mount("/fixtures", StaticFiles(directory=str(config.FIXTURES)), name="fixtures")

if config.WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.WEB_DIST), html=True), name="web")


@app.get("/favicon.svg")
def favicon():
    path = config.WEB_DIST / "favicon.svg"
    if path.exists():
        return FileResponse(path)
    raise HTTPException(status_code=404)


def run() -> None:
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8077, reload=False)
