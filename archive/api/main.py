"""Synapse FastAPI 서버.

Status: **frozen at v22 1차안** (2026-04-25). v22 2차안 라우트(`/note`,
`POST /posts/{id}/process`, `/synapse/turn`, `/promote`) 는 Flutter 측이
`synapse_engine` 을 직접 호출 — Python HTTP 서버는 더 이상 갱신되지 않는다.

이 서버는 학습·dogfood·gabjil 실험의 백엔드로 보존된다.
신규 클라이언트는 Flutter `synapse_engine` 패키지를 임베드하여 사용.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# SYNAPSE_DATA_DIR 환경변수 적용 (engine/db.py가 import 전에 읽어야 함)
data_dir = os.environ.get("SYNAPSE_DATA_DIR", "~/.synapse")
os.environ["SYNAPSE_DATA_DIR"] = str(Path(data_dir).expanduser())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.graph import router
from engine.workers import install_default_hooks

# v15-A2: 저장 완료 이벤트에 카테고리/별칭 워커 연결 (daemon 스레드, 비블로킹)
install_default_hooks(background=True)

app = FastAPI(title="Synapse API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
