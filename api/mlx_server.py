"""
Synapse MLX Router Server
- OpenAI /v1/chat/completions 호환
- model 필드로 태스크 어댑터 라우팅 (synapse/<task>)
- 베이스 모델 1회 로드, 어댑터 스왑

실행: python api/mlx_server.py
"""

import os, time, json, logging
from pathlib import Path
from typing import Optional

import mlx.core as mx
from mlx_lm import load
from mlx_lm.generate import generate, stream_generate
from mlx_lm.sample_utils import make_sampler

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 경로 설정 ──────────────────────────────────────────────
BASE_MODEL = os.getenv("SYNAPSE_BASE_MODEL", "unsloth/gemma-4-E2B-it-UD-MLX-4bit")
ADAPTER_BASE = Path(os.getenv("SYNAPSE_ADAPTER_BASE",
    str(Path(__file__).parent.parent / "archive/finetune/models/tasks")))
HOST = os.getenv("SYNAPSE_HOST", "127.0.0.1")
PORT = int(os.getenv("SYNAPSE_PORT", "8765"))

# ── 사용 가능한 태스크 ─────────────────────────────────────
TASKS = [
    "extract",
    "retrieve-filter",
    "retrieve-expand",
    "retrieve-expand-org",
    "routing",
    "save-pronoun",
    "save-state-personal",
    "save-state-org",
    "save-subject-org",
    "security-access",
    "security-context",
    "security-org",
    "security-personal",
]

# ── 모델 상태 ──────────────────────────────────────────────
class ModelState:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.current_adapter: Optional[str] = None

    def load_base(self):
        log.info(f"베이스 모델 로드 중: {BASE_MODEL}")
        self.model, self.tokenizer = load(BASE_MODEL)
        self.current_adapter = None
        log.info("베이스 모델 로드 완료")

    def switch_adapter(self, task: Optional[str]):
        """task=None이면 베이스 모델(어댑터 없음)로 스왑."""
        if self.current_adapter == task:
            return
        if task is None:
            log.info(f"베이스 모델로 스왑 (어댑터 없음)")
            self.model, self.tokenizer = load(BASE_MODEL)
        else:
            adapter_path = str(ADAPTER_BASE / task)
            if not Path(adapter_path).exists():
                raise ValueError(f"어댑터 없음: {adapter_path}")
            log.info(f"어댑터 스왑: {self.current_adapter} → {task}")
            self.model, self.tokenizer = load(BASE_MODEL, adapter_path=adapter_path)
        self.current_adapter = task
        mx.eval(self.model.parameters())
        log.info(f"로드 완료: {task or 'base'}")

state = ModelState()

# ── FastAPI ────────────────────────────────────────────────
app = FastAPI(title="Synapse MLX Server")

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str          # "synapse/<task>" 또는 태스크명
    messages: list[Message]
    max_tokens: int = 256
    temperature: float = 0.0

@app.on_event("startup")
async def startup():
    state.load_base()

@app.get("/v1/models")
def list_models():
    all_models = [{"id": f"synapse/{t}", "object": "model"} for t in TASKS]
    all_models.append({"id": "synapse/chat", "object": "model"})
    return {"object": "list", "data": all_models}

@app.post("/v1/chat/completions")
async def chat(req: ChatRequest):
    # 태스크 추출: "synapse/retrieve-filter" → "retrieve-filter"
    model_id = req.model
    task = model_id.replace("synapse/", "").strip()

    # "chat" = 베이스 모델 (어댑터 없음)
    if task == "chat":
        try:
            state.switch_adapter(None)
        except Exception as e:
            raise HTTPException(500, str(e))
    elif task not in TASKS:
        raise HTTPException(400, f"Unknown task: {task}. Available: {TASKS + ['chat']}")
    else:
        try:
            state.switch_adapter(task)
        except ValueError as e:
            raise HTTPException(404, str(e))

    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    prompt = state.tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )

    t0 = time.time()
    sampler = make_sampler(temp=req.temperature)
    output = generate(
        state.model, state.tokenizer,
        prompt=prompt,
        max_tokens=req.max_tokens,
        sampler=sampler,
        verbose=False,
    )
    elapsed = time.time() - t0

    return {
        "id": f"synapse-{int(time.time())}",
        "object": "chat.completion",
        "model": req.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": output.strip()},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1},
        "_meta": {"adapter": task, "elapsed_sec": round(elapsed, 2)}
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "current_adapter": state.current_adapter,
        "available_tasks": TASKS,
    }

if __name__ == "__main__":
    log.info(f"Synapse MLX Server 시작: http://{HOST}:{PORT}")
    log.info(f"어댑터 경로: {ADAPTER_BASE}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
