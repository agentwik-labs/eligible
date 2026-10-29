"""HTTP API and the demo page (SPEC §3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.datastructures import UploadFile

from eligible import __version__
from eligible.config import get_settings
from eligible.models import CheckResult
from eligible.pipeline import Checker
from eligible.retrieve.chunk import Chunk
from eligible.retrieve.index import INDEX_PATH
from eligible.showcase import engineering
from eligible.tracing import Trace, Tracer

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
SAMPLES = ROOT / "data" / "receipts"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the embedding model and index before the first visitor, not during their check."""
    if INDEX_PATH.exists():
        await run_in_threadpool(checker().retrieve, "warm up")
    yield


app = FastAPI(title="Eligible", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


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
    return Checker(tracer=Tracer(get_settings().trace_path))


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


@app.get("/v1/traces")
def traces(limit: int = 50) -> list[Trace]:
    """Recent requests with their spans, newest first."""
    tracer = checker().tracer
    return tracer.recent(min(max(limit, 1), 500)) if tracer else []


@app.get("/traces", include_in_schema=False)
def traces_page() -> FileResponse:
    return FileResponse(WEB / "traces.html")


@app.get("/v1/engineering")
def engineering_data() -> dict[str, Any]:
    """Numbers for the engineering page, all read from committed reports."""
    return engineering()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/engineering", include_in_schema=False)
def engineering_page() -> FileResponse:
    return FileResponse(WEB / "engineering.html")
