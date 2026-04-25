# Synapse Mobile + Desktop — Flutter 풀 오프라인 (v22 2차안)

**최종 업데이트**: 2026-04-25 (v22 2차안 — **모바일 우선·데스크톱 통합** 으로 전환. Python+MLX 위주의 포팅 표현 폐기. Flutter 단일 코드베이스 (iOS·Android·macOS·Windows) + 인프로세스 `llamadart`. HTTP·MLX 서버 없음. 데스크톱은 같은 위젯이 자연 확장. Phase 0~4 자체 일정은 [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) 의 F1~F10 마일스톤으로 대체. 본 문서는 ① 디바이스 벤치마크, ② 모델 변환 파이프라인, ③ 파이프라인 최적화 분석, ④ 리스크 — 4 가지 결정 자료를 보존하는 역할로 재정의.)

## Context

Synapse 는 풀 오프라인 온디바이스 개인 지식 하이퍼그래프 앱. **사용 빈도 1순위는 모바일** 이며, 데스크톱(macOS·Windows) 은 같은 Flutter 코드베이스로 부수적으로 따라온다.

엔진은 별도 Dart 패키지 `synapse_engine` 으로 분리되어 시냅스 앱·갑질 등 도메인 앱이 공유한다. 패키지 내부 설계는 `DESIGN_ENGINE.md` (2 계층 API + `allowedKinds` 유연성).

**번들 구성**: 베이스 모델 (Gemma 4 E2B-it 4bit GGUF, ~1.2GB) + `enable_thinking=False` + `docs/*_SYSTEMPROMPT.md` 조합이 다수 태스크를 처리. 모바일에 번들할 어댑터는 v22 2차안 단계에서 1 종 (`retrieve-expand`, ~52MB) — `save-pronoun`/`meta-filter`/`typo-normalize`/`synapse-answer`/`retrieve-filter` 는 베이스 + 시스템 프롬프트로 처리한다. 단일 모델 + 앱 번들 고정 정책이며, 다운로드 인프라·모델 카탈로그·다른 베이스용 어댑터는 후속 PLAN.

## 1. 기술 스택 결정

**Flutter + llamadart (llama.cpp 바인딩) — 모바일·데스크톱 단일**

| 후보 | LoRA 핫스왑 | 크로스플랫폼 | 판정 |
|------|------------|-------------|------|
| Flutter + llamadart v0.6.10 | ✅ 다중 동적 스왑 | iOS·Android·macOS·Windows | **채택** |
| MLX Swift | ❌ 로드타임만 | iOS only | 탈락 |
| React Native llama.rn | ❌ 미지원 | iOS+Android | 탈락 |
| 네이티브 각각 | ✅ | N배 개발 | 비효율 |

근거:
- llamadart 가 llama.cpp 래핑, GGUF + 런타임 LoRA 핫스왑 명시 지원 — 인프라 코드는 `archive/synapse_engine_v15/` 에 검증된 형태로 보존되어 있어 그대로 재사용.
- Flutter 단일 코드베이스로 모바일 (iOS·Android) + 데스크톱 (macOS·Windows). 모바일 우선 위젯이 데스크톱에서도 자연 확장.
- llama.cpp 생태계가 Gemma 4 E2B GGUF 지원 (ggml-org 공식 제공).

DB: **sqflite + sqflite_common_ffi** (데스크톱) — v22 2차안 9 테이블 스키마는 `synapse_engine` 패키지 내부에서 `EngineConfig.allowedKinds` 로 동적 빌드.

형태소 분석기: **kiwi-nlp (WASM)** — 모바일·데스크톱 단일. 서버용 `kiwipiepy` (C++) 는 본 모바일 범위 밖 (Python frozen 환경에 남음). 토큰 결과 스키마는 양쪽 동일.

LLM 호출: **인프로세스 llamadart 직접 호출** — HTTP·MLX 서버·localhost:8765 없음. 네트워크 레이턴시 0.

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

(v13에서 retention·category 필드 폐기, v15에서 edges 테이블 자체 폐기)

→ 파인튜닝 필수. 파인튜닝 시 프롬프트 대폭 축소 → **3~5초/호출** 예상.

## 3. 앱 아키텍처

엔진은 별도 패키지로 분리되었으므로 앱은 패키지 import + UI 위주.

```
app/                          ← 시냅스 Flutter 앱 (PLAN F6 에서 신규)
├── lib/
│   ├── main.dart
│   ├── routes/
│   │   ├── note.dart         ← /note (축적 + 자동저장 + 의미 처리)
│   │   └── synapse.dart      ← /synapse (인출·융합 + 통찰 승격)
│   ├── widgets/
│   │   ├── post_sidebar.dart ← post 목록 (✦ insight 구분)
│   │   ├── note_editor.dart  ← 단일 입력 + 정정 카드 인라인
│   │   └── synapse_thread.dart
│   ├── providers/            ← Riverpod 등 상태 관리 (자동저장 디바운스 포함)
│   └── theme/                ← 모바일 우선 토큰 + 데스크톱 확장
├── assets/                   ← 패키지 assets 와 별개 (앱 전용 아이콘 등)
├── ios/  android/  macos/  windows/
└── pubspec.yaml              ← synapse_engine 의존성

(synapse_engine 패키지 내부 — DESIGN_ENGINE.md §1 참고)
```

**핵심 변경**:
- HTTP 서버 (`api/mlx_server.py`) 제거 → `synapse_engine` 패키지 내부 인프로세스 llamadart 직접 호출.
- Python `engine/*.py` (save·retrieve·llm·db) 는 알고리즘 참조 구현으로 frozen, 이식은 Dart 신규 구현 (PLAN F2~F5).
- LLM·그래프 원자 작업은 `synapse_engine` 의 `LlmTasks`/`GraphOps` 로 노출, 시냅스 흐름은 `SynapseFlow` 로 압축. 앱은 이 3 객체만 호출.

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

변환 대상 (v22 2차안 단계):
- **필수 1 종**: `retrieve-expand` — 베이스 모델 단독으로 처리 어려운 키워드 확장 태스크.
- **베이스 + 시스템 프롬프트로 처리 (어댑터 불필요)**: `save-pronoun`·`meta-filter`·`typo-normalize`·`synapse-answer`·`retrieve-filter`. 각각 `docs/*_SYSTEMPROMPT.md` 가 짝.
- **후속 PLAN**: 다른 베이스 모델용 어댑터 (Qwen·Phi 등), 도메인 특화 어댑터.

## 5. 파이프라인 최적화

### 대전제: 품질이 먼저다

모바일에서 속도를 줄이겠다고 파이프라인 단계를 함부로 생략하거나 합치면 하이퍼그래프 품질이 망가진다.
각 단계는 독립적인 이유로 존재한다. 최적화는 **"같은 품질을 더 빠르게"** 만 허용한다.

### v22 2차안 — 자동저장 ≠ 의미 처리 분리 (핵심 최적화)

v22 2차안의 가장 큰 변화는 **저장을 두 층으로 쪼갠 것**:

| 동작 | 트리거 | LLM | 응답 시간 |
|---|---|---|---|
| 자동저장 | 입력 1.5초 디바운스 + 페이지 이탈 | ❌ 없음 | <50ms |
| 의미 처리 | ⌘S / "정리" 버튼 / 재진입 시 제안 | ✅ 있음 | 0.5~3초 |

매 입력마다 LLM 호출하는 v18 이전 모델은 모바일에서 지속 불가 (배터리·발열). 자동저장은 sqflite UPDATE 한 줄, 의미 처리는 사용자가 "정리" 의도를 줄 때만 — 모바일 기기에서 가장 큰 비용 절감. 원칙 9·13 (`DESIGN_PRINCIPLES.md`) 와 파이프라인 세부 (`DESIGN_PIPELINE.md`) 참조.

### 의미 처리 파이프라인 — 각 단계의 품질 역할

```
[의미 처리 — 사용자 명시 트리거 시만]
1. save-pronoun   → "거기" → "스타벅스 강남점"으로 치환. 이거 빠지면 노드가 "거기"로 생성됨
2. Kiwi 추출      → 형태소 분석 기반 노드 (lemma 정규화). v17 부터 LLM extract 폐기
3. meta-filter    → 메타 대화 사전 필터링 ("방금 그거 다시" 같은 발화)
4. negation       → "안 좋아" → 안 노드 분리
5. typo-normalize → LLM 정정 후보 생성 (별칭 보호 + 자모 거리 사전 필터)
                    → UI 카드로 노출, 사용자 [적용] 클릭 강제 (자동 적용 금지, 원칙 14-③)
6. alias-suggest  → 별칭 등록 (사용자 적용 시)

[인출 — /synapse]
7. retrieve-expand → "허리 어때?" → ["허리", "디스크", "L4", "통증"]. 검색 커버리지 결정
8. retrieve-filter → 무관한 문장 제거. 이거 빠지면 응답에 노이즈 섞임
9. category-supplement → 카테고리 바구니 공유로 BFS 단절 보완. 비연결 서브그래프 도달

[응답 — /synapse]
10. synapse-answer → 맥락 기반 합성 (원문 나열이 아니라 융합)
```

### 품질 기준선 (PLAN F3 진입 전 확립)

GGUF 변환 후 아래 기준을 **반드시** 통과해야 다음 단계 진행 (v17 이후 extract 폐기 반영, v22 2차안 단계 측정 대상만):

| 태스크 | 품질 기준 | 측정 방법 |
|--------|----------|----------|
| save-pronoun | 치환 정확도 90%+ | 대명사/날짜 포함 입력 20건 |
| retrieve-filter | pass/reject 일치율 95%+ | MLX 출력 대비 |
| retrieve-expand | 키워드 리콜 80%+ (핵심 키워드 누락 없음) | MLX 출력 대비 |
| meta-filter | 메타/사실 분류 정확도 90%+ | 메타 대화 입력 20건 |
| typo-normalize | 후보 정확도 90%+ + 별칭 보호 100% | 오타 + 별칭 등록 토큰 혼합 30건 |

**95% 미만이면 해당 어댑터는 llama.cpp 에서 재학습한다.** "속도 빠르니까 품질 좀 떨어져도 OK" 없음. Kiwi 노드 추출은 결정론적 — LLM 측정 대상 아님.

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
| save-pronoun 전면 생략 | "거기", "아까", "그 사람" 이 노드로 영구 저장. 하이퍼그래프 오염 |
| negation 후처리 생략 | "안 좋아"가 분리 안 되면 부정 의미 소실 |
| typo-correct 생략 | 오타마다 중복 노드 증식. "스타벅스" vs "스ㅏ타벅스" |
| 양자화 단계 추가 하향 (Q2/Q3) | extract는 JSON 구조 출력. 양자화 낮추면 형식 붕괴 직격 |

### Progressive UI — 체감 속도 개선 (품질 무관)

실제 파이프라인 시간은 그대로 두되, 사용자 체감을 개선:

```
0초   : 입력 수신, "처리 중..." 표시
~5초  : retrieve 결과 → "관련 기억 3건 발견" 표시
~10초 : save 결과 → "노드 2개, 바구니 멤버 3건 저장" 표시  
~15초 : chat 응답 스트리밍 시작 → 토큰 단위로 표시
```

파이프라인 인디케이터: 현재 단계명 + 경과 시간 표시.

### 예상 결과

v22 2차안에서는 **자동저장이 LLM 트랙에서 분리**되었으므로 시나리오가 다음과 같이 정렬된다:

| 시나리오 | 트리거 | 응답 시간 | 비고 |
|---|---|---|---|
| 자동저장 (모든 입력) | 1.5초 디바운스 + 페이지 이탈 | <50ms | sqflite UPDATE 한 줄. LLM 호출 없음 |
| 의미 처리 — 단순 (대명사 없음) | ⌘S / "정리" | 0.5~1.5초 | save-pronoun 스킵, Kiwi + meta-filter + typo-normalize |
| 의미 처리 — 복잡 (대명사·다수 노드) | ⌘S / "정리" | 1.5~3초 | 전 파이프라인 |
| 시냅스 한 턴 (인출+합성) | /synapse 입력 | 5~10초 | retrieve-expand + retrieve-filter + synapse-answer |

"모바일 (A+B 적용)" 은 **품질 동일, 인프라 + 로직 최적화만** 적용한 수치.
C (배치화·통합) 는 재학습 + 검증 통과 후에만 추가 적용.

## 6. 단계별 실행 계획 — PLAN F1~F10 으로 대체

기존 Phase 0~4 자체 일정은 [`PLAN-20260425-SYN-flutter-rewrite.md`](../deliverables/SYN/20260425/user/PLAN-20260425-SYN-flutter-rewrite.md) 의 F1~F10 마일스톤으로 대체된다. 본 문서는 본 마일스톤들의 결정 자료(벤치마크·변환·최적화·리스크)만 보존한다.

| 본 문서 섹션 | 대응 PLAN 마일스톤 |
|---|---|
| §2 디바이스 벤치마크 | F3 (LlmTasks 단위 호출) — 어댑터 핫스왑·tok/s·RAM 재측정 |
| §4 모델 변환 파이프라인 | F3 진입 전 `retrieve-expand` GGUF 변환 + 검증 |
| §5 파이프라인 최적화 | F5 (SynapseFlow noteProcess) 구현 시 인용 |
| §7 리스크 | F0 정합 단계에서 매 마일스톤 점검 사항으로 인계 |

설계 정합 + DB + LLM + Graph + Flow + UI 통합·검증 흐름은 PLAN F0~F10 표를 단일 출처로 본다.

## 7. 리스크

| 리스크 | 영향 | 확률 | 대응 |
|--------|------|------|------|
| MLX→GGUF 변환 품질 저하 | 높음 | 중 | Phase 0에서 검증. 실패 시 llama.cpp 재학습 |
| llamadart + Gemma 4 호환성 | 높음 | 낮음 | Phase 1에서 검증. 실패 시 직접 FFI |
| 6GB 디바이스 메모리 부족 | 중 | 중 | Q4_0 대체 (~1.2GB). mmap 활용 |
| 어댑터 스왑 레이턴시 | 낮음 | 낮음 | 빈번 어댑터 캐시, 파이프라인 재배치 |
| 앱 번들 크기 (1.5GB) | 낮음 | 높음 | 첫 실행 다운로드, 어댑터만 번들 (~40-70MB) |
| convert_lora_to_gguf.py 변경 | 낮음 | 높음 | llama.cpp 커밋 고정, 변환 결과 버전관리 |

## 8. 핵심 파일 참조 — Python frozen 자산 (참조 구현)

v22 1차안에서 freeze 된 Python 측 알고리즘. **포팅 대상이 아니라 참조 구현** — 같은 동작을 Dart 로 재현할 때의 알고리즘 명세 역할.

- `engine/save.py` — 정규식·부정부사·DB upsert 흐름 (Kiwi 단독 추출 + meta-filter + save-pronoun)
- `engine/retrieve.py` — BFS + ADJACENT_SUBCATEGORIES + 필터 루프
- `engine/llm.py` — 시스템 프롬프트 호출 + thinking 블록 제거 regex
- `engine/db.py` — v22 1차안 9 테이블 스키마 (Dart 측은 `EngineConfig.allowedKinds` 로 동적 빌드)
- `api/mlx_server.py` — ModelState 어댑터 스왑 패턴 (Dart 측은 `synapse_engine` 의 `LlamadartBackend` 로 대체)
- `archive/synapse_engine_v15/` — Dart llamadart 통합 + LoRA 핫스왑 인프라 (검증된 자산, 인프라 코드 직접 재사용)
- `data/finetune/models/tasks/retrieve-expand/adapter_config.json` — LoRA 설정 (rank=8, scale=20.0)
