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

테스트 프롬프트 (시스템 프롬프트 미사용, user 프롬프트에 규칙 포함. **v13 기준**):
```
아래 규칙대로 JSON만 출력. 다른 텍스트 금지.
출력형식: {"nodes":[{"name":"..."}],"deactivate":[]}
규칙: 노드는 원자 개념 하나씩. 1인칭은 "나" 노드.

입력: 나 쿠팡에서 물류 기획 담당하고 있어
알려진 사실: 없음
```

Edge Gallery 설정: Max tokens 4000, TopK 64, TopP 0.95, Temp 1.00, GPU, thinking OFF

베이스 모델 출력 예시 (S22U, 7.3초, v11 구 스키마 기준):
```json
{
  "nodes": [
    {"name": "쿠팡"},
    {"name": "물류 기획 담당자"}  // ❌ 비원자 (물류, 기획, 담당 각각이어야 함)
  ]
  // ❌ "나" 노드 누락
}
```

(v13에서 edges·retention·category 필드 모두 폐기됨)

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

### 대전제: 품질이 먼저다

모바일에서 속도를 줄이겠다고 파이프라인 단계를 함부로 생략하거나 합치면 그래프 품질이 망가진다.
각 단계는 독립적인 이유로 존재한다. 최적화는 **"같은 품질을 더 빠르게"** 만 허용한다.

### 현재 파이프라인 — 각 단계의 품질 역할

```
[저장]
1. save-pronoun   → "거기" → "스타벅스 강남점"으로 치환. 이거 빠지면 노드가 "거기"로 생성됨
2. extract        → 노드/엣지/카테고리/deactivate 추출. 핵심 추출기
3. negation       → "안 좋아" → 안 노드 분리. 빠지면 "안좋아"가 하나의 노드가 됨
4. typo-correct   → 오타 교정 (자모 거리). 중복 노드 방지
5. alias-suggest  → 별칭 등록. 인출 매칭률 직결

[인출]
6. retrieve-expand → "허리 어때?" → ["허리", "디스크", "L4", "통증"]. 검색 커버리지 결정
7. retrieve-filter → 무관한 문장 제거. 이거 빠지면 응답에 노이즈 섞임
8. category-supplement → BFS 단절 보완. 비연결 서브그래프 도달

[응답]
9. chat           → 맥락 기반 자연어 답변
```

### 품질 기준선 (Phase 0에서 확립)

GGUF 변환 후 아래 기준을 **반드시** 통과해야 다음 단계 진행:

| 태스크 | 품질 기준 | 측정 방법 |
|--------|----------|----------|
| extract | 노드 원자성 100%, 카테고리 코드 형식 100%, retention 정확도 95%+ | 기존 training.jsonl 테스트셋 50건 |
| extract | deactivate 정확도 90%+ | 상충 입력 10건 |
| save-pronoun | 치환 정확도 90%+ | 대명사/날짜 포함 입력 20건 |
| retrieve-filter | pass/reject 일치율 95%+ | MLX 출력 대비 |
| retrieve-expand | 키워드 리콜 80%+ (핵심 키워드 누락 없음) | MLX 출력 대비 |
| negation | "안/못" 분리 정확도 100% | 부정부사 입력 10건 |

**95% 미만이면 해당 어댑터는 llama.cpp에서 재학습한다.** "속도 빠르니까 품질 좀 떨어져도 OK" 없음.

### 최적화 — 품질 영향 분석

#### A. 품질 무관 (인프라 개선)

| 최적화 | 절감 | 품질 영향 | 비고 |
|--------|------|----------|------|
| 어댑터 스왑 오버헤드 제거 | 8-12초 | 없음 | MLX=전체 리로드, llamadart=LoRA만 적용 |
| HTTP 제거 (인프로세스) | 1-2초 | 없음 | 네트워크 왕복 제거 |
| max_tokens 적정화 | 1-3초 | 없음 | extract: 512, filter: 8, expand: 256 (현재와 동일) |

이것만으로 **10-17초 절감**. 파이프라인 로직 변경 없이 달성.

#### B. 품질 보존 (로직 최적화)

| 최적화 | 절감 | 품질 영향 | 조건 |
|--------|------|----------|------|
| save-pronoun regex 사전 체크 | 3-5초 (60-70% 입력) | 없음 | 이미 구현됨. 대명사/날짜 미감지 시 LLM 스킵 |
| alias-suggest 비동기화 | 3초 | 없음 | 응답 후 백그라운드 처리. 즉시 사용 못해도 다음 입력부터 적용 |
| BFS 조기 종료 | 0-5초 | 거의 없음 | 카테고리 보완에서 새 노드 0개면 추가 필터 스킵 |

#### C. 품질 리스크 있음 — 반드시 검증 후 적용

| 최적화 | 절감 | 품질 리스크 | 검증 방법 |
|--------|------|------------|----------|
| retrieve-filter 배치화 (5문장/호출) | 필터 단계 50%+ | 배치 시 문장 간 간섭으로 판단 정확도 하락 가능 | 재학습 + 기존 테스트셋 pass/reject 비교. 일치율 95% 미만이면 폐기 |
| save-pronoun + extract 통합 | 3-5초 | 2B 모델에 두 태스크 동시 학습은 간섭 위험 높음. 치환 실패 → 노드 오염 전파 | 재학습 + 치환 정확도 + 추출 정확도 **둘 다** 기존 대비 95%+. 하나라도 미달이면 폐기 |
| extract에 deactivate 통합 (이미 적용) | — | Task6 v2에서 통합 완료. 추출 정확도 모니터링 중 | val_loss 기준 |

#### D. 금지 — 하면 안 되는 최적화

| 아이디어 | 왜 안 되는가 |
|----------|-------------|
| retrieve-filter 생략 | 노이즈 문장이 chat 응답에 그대로 유입. 엉뚱한 답변 |
| retrieve-expand 생략 | 질문 키워드만으로 BFS 시작 → 동의어/관련어 놓침 → 커버리지 붕괴 |
| save-pronoun 전면 생략 | "거기", "아까", "그 사람" 이 노드로 영구 저장. 그래프 오염 |
| negation 후처리 생략 | "안 좋아"가 분리 안 되면 부정 의미 소실 |
| typo-correct 생략 | 오타마다 중복 노드 증식. "스타벅스" vs "스ㅏ타벅스" |
| 양자화 단계 추가 하향 (Q2/Q3) | extract는 JSON 구조 출력. 양자화 낮추면 형식 붕괴 직격 |

### Progressive UI — 체감 속도 개선 (품질 무관)

실제 파이프라인 시간은 그대로 두되, 사용자 체감을 개선:

```
0초   : 입력 수신, "처리 중..." 표시
~5초  : retrieve 결과 → "관련 기억 3건 발견" 표시
~10초 : save 결과 → "노드 2개, 엣지 3개 저장" 표시  
~15초 : chat 응답 스트리밍 시작 → 토큰 단위로 표시
```

파이프라인 인디케이터: 현재 단계명 + 경과 시간 표시.

### 예상 결과

| 시나리오 | 현재(Mac) | 모바일(그대로) | 모바일(A+B 적용) | 비고 |
|----------|----------|--------------|----------------|------|
| 단순 입력 (대명사 없음, 트리플 2개) | 15초 | 35초 | 15-20초 | pronoun 스킵 + 인프라 절감 |
| 복잡 입력 (대명사+트리플 8개) | 25초 | 55초 | 35-40초 | 모든 단계 필수 실행 |
| 질문만 (인출+응답) | 10초 | 22초 | 12-15초 | 저장 단계 없음 |

"모바일(A+B 적용)"은 **품질 동일, 인프라+로직 최적화만** 적용한 수치.
C(배치화/통합)는 재학습+검증 통과 후에만 추가 적용.

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
- `data/finetune/models/tasks/extract/adapter_config.json` — LoRA 설정 (rank=8, scale=20.0)
