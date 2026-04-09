# 다음 세션 프롬프트

아래 내용을 그대로 복사해서 새 세션에 붙여넣기.

---

## 프롬프트

Synapse 프로젝트의 파인튜닝 + 엔진 코드 수정 작업을 이어서 진행한다.

### 프로젝트 위치
`/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse`

### 읽어야 할 파일 (순서대로)
1. `docs/DESIGN_OVERVIEW.md` — 프로젝트 개요, 핵심 가치, 데이터 정책
2. `docs/DESIGN_GRAPH.md` — 그래프 모델, 스키마, 노드/엣지 규칙, 카테고리 분류체계
3. `docs/DESIGN_PIPELINE.md` — 저장/인출 파이프라인 (LLM 추출 방식 전환 내용 포함)
4. `docs/DESIGN_FINETUNE.md` — 파인튜닝 타겟 7개, task6 데이터 현황
5. `engine/` 디렉토리 전체 구조 파악

---

### 현재 상태 요약

**완료:**
- task6 (노드/엣지/카테고리 추출) 학습 데이터 생성 완료
  - 총 1,677건 (task6_extract_category + task6_sup_a~d)
  - mlx_train: train 4,329건 / valid 482건
  - 저장 경로: `archive/finetune/data/mlx_train/`
  - 카테고리 검증 완료 (잘못된 카테고리 0건, 깨진 엣지 0건)
- 설계 문서 현행화 완료 (DESIGN_GRAPH, PIPELINE, FINETUNE, APP)

**미완료:**
- task6 파인튜닝 실행 (MLX LoRA)
- 엔진 코드 수정 (Kiwi 제거 → LLM 추출 전환)
- task1~5 데이터 생성 및 파인튜닝

---

### 이번 세션 목표

아래 순서로 진행한다. **파인튜닝과 코드 수정은 병렬 가능.**

#### 1. task6 파인튜닝 실행 (MLX LoRA)

```bash
# 파인튜닝 실행
cd /Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse
mlx_lm.lora \
  --model unsloth/gemma-4-E2B-it-UD-MLX-4bit \
  --train \
  --data archive/finetune/data/mlx_train \
  --num-layers 8 \
  --batch-size 4 \
  --num-iterations 600 \
  --learning-rate 1e-4 \
  --save-every 100 \
  --adapter-path archive/finetune/adapters/task6
```

완료 후 Ollama에 등록:
```bash
# 어댑터 병합
mlx_lm.fuse \
  --model unsloth/gemma-4-E2B-it-UD-MLX-4bit \
  --adapter-path archive/finetune/adapters/task6 \
  --save-path archive/finetune/models/task6_fused

# Ollama Modelfile 작성 후 등록
ollama create synapse-task6 -f archive/finetune/models/task6_fused/Modelfile
```

#### 2. 엔진 코드 수정

**현재 저장 파이프라인 (구):**
```
입력 → Kiwi 형태소 분석 → 트리플 체인 → LLM 후처리 → DB
```

**목표 파이프라인 (신):**
```
입력 → LLM 추출 (노드+엣지+카테고리 한 번에) → DB
```

수정 대상:
- `engine/db.py` — `nodes.category` 컬럼 추가 확인 (스키마 마이그레이션)
- `engine/morpheme.py` — 사용 중단 (제거 또는 비활성화)
- `engine/save.py` — Kiwi 호출 제거, LLM 추출 함수로 교체
- `engine/retrieve.py` — 카테고리 기반 BFS 보완 추가 (같은 카테고리 노드 집합 조회)
- `engine/llm.py` — task6 추출 프롬프트 추가

**LLM 추출 시스템 프롬프트 (task6):**
```
한국어 문장에서 지식 그래프의 노드와 엣지를 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":[{"name":"노드명","category":"대분류.소분류"}],"edges":[{"source":"노드명","label":"관계","target":"노드명"}]}
```

**카테고리 분류체계 (17개 대분류):**
```
PER: individual, family, friend, colleague, public, org
BOD: part, disease, medical, exercise, nutrition, sleep
MND: emotion, personality, mental, motivation, coping
FOD: ingredient, recipe, restaurant, drink, product
LIV: housing, appliance, interior, supply, maintenance, moving
MON: income, spending, invest, payment, loan, insurance
WRK: workplace, role, jobchange, business, cert, tool
TEC: sw, hw, ai, infra, data, security
EDU: school, online, language, academic, reading, exam
LAW: statute, contract, admin, rights, tax
TRV: domestic, abroad, transport, stay, flight, place
NAT: animal, plant, weather, terrain, ecology, space
CUL: film, music, book, art, show, media
HOB: sport, outdoor, game, craft, sing, collect, social
SOC: politics, international, incident, economy, issue, news
REL: romance, conflict, comm, manner, online
REG: christianity, buddhism, catholic, islam, other, practice
```

#### 3. 동작 테스트

파인튜닝 완료 전에 베이스 모델(gemma4:e2b)로 먼저 테스트:
```bash
python3 -m engine.cli --no-llm  # 파이프라인 구조만 확인
python3 -m engine.cli           # LLM 추출 실제 동작 확인
```

파인튜닝 완료 후: 베이스 vs 파인튜닝 모델 추출 정확도 비교.

---

### 참고 사항

**모델:**
- 파인튜닝 베이스: `unsloth/gemma-4-E2B-it-UD-MLX-4bit`
- 런타임: Ollama (localhost:11434)
- 자동 선택 우선순위: `gemma4:e2b → gemma4 → gemma2 → ...`

**DB 위치:** `~/.synapse/synapse.db`

**학습 데이터 카테고리 분포 (문장 기준):**
BOD 236 · WRK 216 · MON 206 · TEC 160 · TRV 156 · FOD 122 · HOB 118 · EDU 104 · MND 99 · LIV 98 · NAT 89 · LAW 85 · CUL 66 · SOC 51 · 빈결과 50 · REL 44 · REG 40
