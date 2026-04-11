# Synapse Mobile Porting Plan

## Context
Synapse는 Python+MLX 기반 개인 지식 그래프 시스템. 모바일 포팅하여 오프라인 온디바이스 완결형 앱으로 만든다.

## 1. 기술 스택 결정

**Flutter + llamadart (llama.cpp 바인딩)**

| 후보 | LoRA 핫스왑 | 크로스플랫폼 | 판정 |
|------|------------|-------------|------|
| Flutter llamadart v0.6.10 | ✅ 다중 동적 스왑 | iOS+Android | **채택** |
| MLX Swift | ❌ 로드타임만 | iOS only | 탈락 |
| React Native llama.rn | ❌ 미지원 | iOS+Android | 탈락 |
| 네이티브 각각 | ✅ | 2배 개발 | 비효율 |

근거:
- llamadart가 llama.cpp 래핑, GGUF + 런타임 LoRA 핫스왑 명시 지원
- 단일 코드베이스로 iOS/Android
- llama.cpp 생태계가 Gemma 4 E2B GGUF 지원 확인 (ggml-org 공식 제공)

DB: **sqflite** — 현재 SQLite 스키마 그대로 포팅

## 2. 디바이스 벤치마크 (실측, 2026-04-11)

| 디바이스 | 속도 | 조건 |
|----------|------|------|
| Samsung S22U | 7.3초/호출 | GPU, 베이스 모델(파인튜닝 없음), max_tokens=4000 |
| iPhone 15 Pro | 5.3초/호출 | 동일 프롬프트 |

테스트 프롬프트 (시스템 프롬프트 미사용, user 프롬프트에 규칙 포함):
```
아래 규칙대로 JSON만 출력. 다른 텍스트 금지.
출력형식: {"retention":"memory|daily","nodes":[...],"edges":[...],"deactivate":[]}
규칙: 노드는 원자 개념 하나씩. 1인칭은 "나" 노드. 엣지 label은 원문 조사, 없으면 null.
카테고리: PER BOD MND FOD WRK TEC EDU MON LIV LAW TRV NAT CUL HOB SOC REL REG

입력: 나 쿠팡에서 물류 기획 담당하고 있어
알려진 사실: 없음
```

Edge Gallery 설정: Max tokens 4000, TopK 64, TopP 0.95, Temp 1.00, GPU, thinking OFF

베이스 모델 출력 (S22U, 7.3초):
```json
{
  "retention": "daily",        // ❌ "memory"여야 함 (사실/이력)
  "nodes": [
    {"name": "쿠팡", "category": "회사"},          // ❌ WRK.company 형식 미준수
    {"name": "물류 기획 담당자", "category": "직업"} // ❌ 비원자 (물류, 기획, 담당 각각)
  ],
  "edges": [
    {"source": "쿠팡", "label": "에서", "target": "물류 기획 담당자"}
  ]
  // ❌ "나" 노드 누락
}
```

→ 파인튜닝 필수. 파인튜닝 시 프롬프트 대폭 축소 → **3~5초/호출** 예상.

## 3. 앱 아키텍처

```
flutter_synapse/
├── lib/
│   ├── engine/
│   │   ├── db.dart          ← db.py (124줄) 직접 포팅. 동일 SQL DDL
│   │   ├── inference.dart   ← mlx_server.py 대체. llamadart 모델 로딩 + 어댑터 스왑
│   │   ├── llm.dart         ← llm.py (256줄) 파이프라인 함수. HTTP→직접호출
│   │   ├── save.dart        ← save.py (663줄) 저장 파이프라인 전체
│   │   ├── retrieve.dart    ← retrieve.py (464줄) BFS + 카테고리 보완
│   │   └── pipeline.dart    ← 오케스트레이터 (retrieve→save→respond)
│   ├── models/              ← Triple, SaveResult, RetrieveResult
│   ├── ui/                  ← Chat 인터페이스
│   └── main.dart
├── assets/
│   ├── models/gemma-4-e2b-Q4_K_M.gguf   ← ~1.5GB (첫 실행 시 다운로드)
│   └── adapters/                          ← 5~14개 GGUF LoRA (~2-5MB each)
└── scripts/
    └── convert_adapters.py               ← MLX→PEFT→GGUF 변환
```

핵심 변경: HTTP 서버(mlx_server.py) 제거 → 인프로세스 llamadart 직접 호출. 네트워크 레이턴시 0.

## 4. 모델 변환 파이프라인

```
MLX safetensors → HF PEFT 포맷 (키 리매핑) → convert_lora_to_gguf.py → GGUF LoRA
```

1. **베이스**: ggml-org/gemma-4-E2B-it-GGUF (Q4_K_M) 다운로드. 변환 불필요
2. **어댑터**:
   - adapters.safetensors 키 리매핑 (lora_a→lora_A.weight, prefix 추가)
   - adapter_config.json을 HF PEFT 형식으로 변환
   - llama.cpp `convert_lora_to_gguf.py` 실행
3. **검증**: 동일 입력 → MLX vs GGUF 출력 비교 (20+ 테스트케이스)

변환 대상 (우선순위):
- **필수 5개**: extract, retrieve-filter, retrieve-expand, save-pronoun, chat(base)
- **보류**: routing, security-*, save-state-*, save-subject-org 등

## 5. 파이프라인 최적화

### 현재 파이프라인 (6회 직렬 LLM)
```
save-pronoun(~5s) → extract(~5s) → negation(0-5s) → retrieve-expand(~4s) → retrieve-filter×N(~3s×N) → chat(~5s)
= 모바일 예상 30~50초
```

### 최적화 전략 (단계별)

**즉시 적용 (재학습 없음):**
- 어댑터 스왑 오버헤드 제거: MLX는 모델 전체 리로드(~2-3초), llamadart는 LoRA만 적용(<0.5초) → **8-12초 절감**
- save-pronoun 스킵: 대명사/날짜 미감지 시 LLM 호출 생략 (이미 regex 체크 구현됨, ~60-70% 입력에 해당)
- 별칭 제안 백그라운드 처리 또는 생략

**재학습 필요:**
- retrieve-filter 배치화: 1문장/호출 → 5문장/호출 → 필터 단계 50%+ 축소
- save-pronoun + extract 통합: 2회 → 1회 → 3-5초 절감

**UI 최적화:**
- Progressive 표시: 검색 결과 즉시 표시, 저장 결과 이어서, 응답 스트리밍
- 파이프라인 단계 인디케이터 ("검색 확장 중...", "BFS 탐색 중...")

### 예상 결과

| 시나리오 | 현재(Mac) | 모바일(그대로) | 모바일(최적화) |
|----------|----------|--------------|--------------|
| 단순 입력 | 15초 | 35초 | 18초 |
| 복잡 입력 | 25초 | 55초 | 28초 |
| 질문만 | 10초 | 22초 | 14초 |

## 6. 단계별 실행 계획

### Phase 0: 모델 변환 + 검증 (3-4일)

| 태스크 | 내용 |
|--------|------|
| 0.1 | convert_adapters.py 작성 (MLX→PEFT 키 리매핑) |
| 0.2 | 필수 5개 어댑터 변환 |
| 0.3 | llama.cpp CLI로 베이스+어댑터 추론 검증 |
| 0.4 | MLX vs GGUF 출력 비교 (20+ 테스트, 95% 일치 기준) |

**Go/No-Go**: 변환 품질 95% 미달 시 → llama.cpp 네이티브 재학습 (1-2주 추가)

### Phase 1: 추론 PoC (3-4일)

| 태스크 | 내용 |
|--------|------|
| 1.1 | Flutter 프로젝트 + llamadart 셋업 |
| 1.2 | 베이스 GGUF 로딩 + extract 어댑터 추론 테스트 |
| 1.3 | 어댑터 핫스왑 검증 (extract↔retrieve-filter, 스왑 <1초 목표) |
| 1.4 | 디바이스별 벤치마크 (tok/s, RAM, 스왑 레이턴시) |
| 1.5 | 챗 템플릿 + thinking 블록 제거 검증 |

**성공기준**: 로딩 <30초, 추론 정상, 스왑 <1초, RAM <3GB

### Phase 2: 엔진 포팅 (6-8일)

| 파일 | 일수 | 핵심 |
|------|------|------|
| db.dart | 1일 | 동일 DDL, WAL, FK |
| inference.dart | 2일 | llamadart 래퍼, 시스템 프롬프트 14개 |
| llm.dart | 1일 | 파이프라인 함수 5개 |
| save.dart | 2일 | 정규식 패턴, 부정부사 후처리, DB upsert |
| retrieve.dart | 2일 | BFS, ADJACENT_SUBCATEGORIES 70쌍, 필터 루프 |
| pipeline.dart | 1일 | 오케스트레이터 + progress 콜백 |

### Phase 3: UI + 통합 (5-7일)

| 태스크 | 내용 |
|--------|------|
| 3.1 | Chat 화면 (입력, 버블, 저장결과 인라인 표시) |
| 3.2 | 파이프라인 진행 인디케이터 |
| 3.3 | 모델 다운로드/셋업 (첫 실행 플로우) |
| 3.4 | 설정 (DB 통계, 모델 경로, export/import) |
| 3.5 | 백그라운드 Isolate (UI 블로킹 방지) |

### Phase 4: 최적화 (출시 후)
- retrieve-filter 배치화 (재학습)
- save-pronoun+extract 통합 (재학습)
- Progressive 스트리밍 UI
- 저사양 기기 메모리 최적화

## 7. 리스크

| 리스크 | 영향 | 확률 | 대응 |
|--------|------|------|------|
| MLX→GGUF 변환 품질 저하 | 높음 | 중 | Phase 0에서 검증. 실패 시 llama.cpp 재학습 |
| llamadart + Gemma 4 호환성 | 높음 | 낮음 | Phase 1에서 검증. 실패 시 직접 FFI |
| 6GB 디바이스 메모리 부족 | 중 | 중 | Q4_0 대체 (~1.2GB). mmap 활용 |
| 어댑터 스왑 레이턴시 | 낮음 | 낮음 | 빈번 어댑터 캐시, 파이프라인 재배치 |
| 앱 번들 크기 (1.5GB) | 낮음 | 높음 | 첫 실행 다운로드, 어댑터만 번들 (~40-70MB) |
| convert_lora_to_gguf.py 변경 | 낮음 | 높음 | llama.cpp 커밋 고정, 변환 결과 버전관리 |

## 8. 핵심 파일 참조

- `engine/save.py` (663줄) — 가장 큰 포팅 대상. 정규식, 부정부사, DB upsert
- `engine/retrieve.py` (464줄) — BFS, ADJACENT_SUBCATEGORIES, 필터 루프
- `engine/llm.py` (256줄) — 시스템 프롬프트 14개, thinking 블록 제거 regex
- `engine/db.py` (124줄) — v9 스키마 DDL, WAL, FK
- `api/mlx_server.py` (166줄) — ModelState 어댑터 스왑 패턴 → inference.dart로 대체
- `archive/finetune/models/tasks/extract/adapter_config.json` — LoRA 설정 (rank=8, scale=20.0)
