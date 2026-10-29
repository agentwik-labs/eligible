"""HTTP API and the demo page (SPEC §3)."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from eligible import __version__
from eligible.config import get_settings
from eligible.models import CheckResult
from eligible.pipeline import Checker
from eligible.retrieve.chunk import Chunk

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
SAMPLES = ROOT / "data" / "receipts"

app = FastAPI(title="Eligible", version=__version__)


class Health(BaseModel):
    status: str
    version: str
    llm_mode: str
    models: dict[str, str]


class CheckText(BaseModel):
    text: str


class Sample(BaseModel):
    id: str
    text: str


@cache
def checker() -> Checker:
    return Checker()


@app.get("/healthz")
def healthz() -> Health:
    s = get_settings()
    return Health(
        status="ok",
        version=__version__,
        llm_mode=s.llm_mode,
        models={"extract": s.extract_model, "decide": s.decide_model, "judge": s.judge_model},
    )


@app.post("/v1/check")
async def check(request: Request) -> CheckResult:
    """JSON `{"text": "..."}` or a multipart `file` holding receipt text."""
    if request.headers.get("content-type", "").startswith("multipart/"):
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(422, "send a file field named 'file'")
        if (upload.content_type or "").startswith("image/"):
            raise HTTPException(
                415, "Receipt images need the Anthropic API backend; paste the receipt text."
            )
        text = (await upload.read()).decode("utf-8", errors="replace")
    else:
        try:
            text = CheckText.model_validate(await request.json()).text
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, 'send JSON like {"text": "..."}') from e
    if not text.strip():
        raise HTTPException(422, "the receipt is empty")
    return await run_in_threadpool(checker().check, text)


@app.get("/v1/sources/{chunk_id}")
def source(chunk_id: str) -> Chunk:
    chunk = checker().retriever.chunk_by_id(chunk_id)
    if chunk is None:
        raise HTTPException(404, f"no source chunk {chunk_id}")
    return chunk


@app.get("/v1/samples")
def samples() -> list[str]:
    return sorted(p.stem for p in SAMPLES.glob("r*.txt"))


@app.get("/v1/samples/{sample_id}")
def sample(sample_id: str) -> Sample:
    path = SAMPLES / f"{sample_id}.txt"
    if not sample_id.isalnum() or not path.exists():
        raise HTTPException(404, "no such sample")
    return Sample(id=sample_id, text=path.read_text())


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")
