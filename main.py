from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import load_config
from triage.pipeline import run_triage
from triage.providers.claude import ClaudeProvider
from triage.providers.local import LocalProvider

# --- startup -----------------------------------------------------------

_raw_config = load_config()

if _raw_config.llm_provider == "claude":
    _provider = ClaudeProvider(model_name=_raw_config.model_name)
else:
    _provider = LocalProvider()

# Attach the instantiated provider so pipeline.py can call .complete()
_raw_config.llm_provider = _provider  # type: ignore[assignment]
config = _raw_config

# --- app ---------------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- schemas -----------------------------------------------------------

class TriageResponse(BaseModel):
    summary: str
    confidence: str = Field(description="0-100% score reflecting how grounded the answer is in the knowledge base")
    action_items: list[str]
    sources: list[str]


# --- endpoints ---------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/triage",
    response_model=TriageResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/plain": {"schema": {"type": "string"}}},
        }
    },
)
async def triage(request: Request):
    body = await request.body()
    error_log = body.decode()
    if not error_log.strip():
        raise HTTPException(status_code=422, detail="Request body must not be empty.")
    try:
        result = run_triage(error_log, config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TriageResponse(**result)
