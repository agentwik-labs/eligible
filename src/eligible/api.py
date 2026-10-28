"""HTTP API. M0: health only. /v1/check and the demo page arrive in M6."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from eligible import __version__
from eligible.config import get_settings

app = FastAPI(title="Eligible", version=__version__)


class Health(BaseModel):
    status: str
    version: str
    llm_mode: str
    models: dict[str, str]


@app.get("/healthz")
def healthz() -> Health:
    s = get_settings()
    return Health(
        status="ok",
        version=__version__,
        llm_mode=s.llm_mode,
        models={"extract": s.extract_model, "decide": s.decide_model, "judge": s.judge_model},
    )
