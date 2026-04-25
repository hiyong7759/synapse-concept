# Synapse 설계 — 비서 앱

## 컨셉

**개인 비서.** 나의 맥락을 알고 있으며, 필요할 때 꺼내주고, 내가 원하는 일을 대신 처리해준다.

인터페이스: `/note` (지식 축적, 자동저장 + 사용자 명시 의미 처리) + `/synapse` (인출·융합 세션, 통찰 승격) 2 라우트.

비서 능동 흐름 (태스크 수행·소통 보조·일상 관리·온보딩) 과 하이퍼그래프 뷰·조직 연결 UI 는 후속 PLAN.

---

## 기술 스택 — Flutter 단일 코드베이스 (모바일 + 데스크톱)

**사용 빈도 1순위는 모바일** (iOS·Android), 데스크톱 (macOS·Windows) 은 같은 Flutter 코드베이스로 부수적으로 따라온다.

| 후보 | LoRA 핫스왑 | 크로스플랫폼 | 판정 |
|------|------------|-------------|------|
| Flutter + llamadart v0.6.10 | ✅ 다중 동적 스왑 | iOS·Android·macOS·Windows | **채택** |
| MLX Swift | ❌ 로드타임만 | iOS only | 탈락 |
| React Native llama.rn | ❌ 미지원 | iOS+Android | 탈락 |
| 네이티브 각각 | ✅ | N배 개발 | 비효율 |

근거:
- llamadart 가 llama.cpp 래핑, GGUF + 런타임 LoRA 핫스왑 명시 지원. 인프라 코드는 `archive/synapse_engine_v15/` 에 검증된 형태로 보존되어 있어 그대로 재사용.
- Flutter 단일 코드베이스로 모바일 + 데스크톱. 모바일 우선 위젯이 데스크톱에서도 자연 확장.
- llama.cpp 생태계가 Gemma 4 E2B GGUF 지원 (ggml-org 공식 제공).

DB: **sqflite + sqflite_common_ffi** (데스크톱) — 9 테이블 스키마는 `synapse_engine` 패키지 내부에서 `EngineConfig.allowedKinds` 로 동적 빌드.

형태소 분석기: **kiwi-nlp (WASM)** — 모바일·데스크톱 단일. 토큰 결과 스키마는 서버용 `kiwipiepy` 와 동일.

LLM 호출: **인프로세스 llamadart 직접 호출** — HTTP·MLX 서버·localhost:8765 없음. 네트워크 레이턴시 0.

**번들 구성**: 베이스 모델 (Gemma 4 E2B-it 4bit GGUF, ~1.2GB) + `enable_thinking=False` + `docs/*_SYSTEMPROMPT.md` 조합이 다수 태스크를 처리. 어댑터 1 종 (`retrieve-expand`, ~52MB) 만 번들 — `save-pronoun`/`meta-filter`/`typo-normalize`/`synapse-answer`/`retrieve-filter` 는 베이스 + 시스템 프롬프트로 처리. 단일 모델 + 앱 번들 고정 정책. 다운로드 인프라·모델 카탈로그·다른 베이스용 어댑터는 후속 PLAN.

---

## 앱 아키텍처

엔진은 별도 Dart 패키지 `synapse_engine` 으로 분리되어 시냅스 앱·갑질 등 도메인 앱이 공유한다. 패키지 내부 설계는 `DESIGN_ENGINE.md` (2 계층 API + `allowedKinds` 유연성). 앱은 패키지 import + UI 위주.

```
app/                          ← 시냅스 Flutter 앱
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
```

LLM·그래프 원자 작업은 `synapse_engine` 의 `LlmTasks`/`GraphOps` 로 노출, 시냅스 흐름은 `SynapseFlow` 로 압축. 앱은 이 3 객체만 호출.

---

## 사용자 서비스 흐름

```
[앱 최초 설치]
  ↓
[기본 화면] ── 좌측 post 사이드바 (번호·제목·수정시간 + ✦ insight) + 우측 라우트 컨텐츠
  │
  ├── /note ── 지식 축적 (모든 입력의 단일 그릇)
  │     │
  │     ├── 입력 (한 줄 메모 / 긴 마크다운 / 평문 — 형식 인지·선택 없음)
  │     │     ↓
  │     ├── [자동저장] (1.5초 디바운스 + 페이지 이탈, LLM 미사용)
  │     │     posts.source UPDATE 한 줄. <50ms. 손실 방지 단일 목적.
  │     │     상태 표시: "변경됨 / 저장 중… / ✓ 저장됨 (방금)"
  │     │     ↓
  │     ├── [의미 처리] (사용자 명시 ⌘S 또는 "정리" 버튼)
  │     │     상태 표시: "⚙ 정리 중… → ✦ 정리됨"
  │     │     posts.source flush → sentences 재계산 → Kiwi 노드 추출
  │     │     → node_sentence_mentions / sentence_categories / node_category_mentions
  │     │     → LLM 정정 후보 생성 (별칭 보호 + 자모 거리 사전 필터)
  │     │     ↓
  │     ├── [정정 카드 인라인]  자동 적용 금지 (원칙 14-③)
  │     │     "스ㅏ타벅스 → 스타벅스?" [적용] [무시]
  │     │     [적용] 시: alias 등록 + source/sentences 갱신
  │     │     별칭 등록 토큰(`스벅` 등)은 카드에 안 뜸 (사용자 정감 보존)
  │     │     ↓
  │     └── 재진입·이어쓰기·post 삭제 (사이드바 호버 액션)
  │
  └── /synapse ── 인출·융합 세션 (지식 발화)
        │
        ├── 질문 입력
        │     ↓
        ├── [retrieve-expand 어댑터] 노드 후보 키워드 확장
        │     ↓
        ├── [Kiwi 보강] 형태소 분석으로 후보 추가
        │     ↓
        ├── [BFS 인출] 세 경로 (문장 바구니 + 카테고리 공유 + 사용자 heading 계층)
        │     ↓
        ├── [retrieve-filter] 무관 sentence 제거 (불확실 → pass)
        │     ↓
        ├── [synapse-answer] 컨텍스트 sentences 합성 (원문 나열 아닌 융합)
        │     ↓
        ├── 답변 카드 표시 + 메시지 hover 시 [⬆ 통찰로 승격]
        │     ↓
        └── [통찰 승격] (사용자 명시 클릭)
              새 posts(kind='insight', title=본문 첫 행)
              + 본체 sentence(origin='insight', 편집 불가)
              + 시냅스 세션 retrieve 캐시 노드 전부와 node_sentence_mentions 일괄 INSERT
                (Hebbian — 함께 발화한 것이 모두 엮임)
              → /note 사이드바에 ✦ 아이콘 + 앰버 보더로 표시
              → 다음 retrieve 에서 우선 점화 (다음 시냅스의 중력)
```

**핵심**:
- 모드 선택 없음 — 사용자는 입력 형식을 인지·선택하지 않음. 평문이든 마크다운이든 같은 그릇 (`note` post).
- 자동저장과 의미 처리의 두 층 분리 — 매 입력 LLM 호출 폐지로 모바일 배터리·발열 보호 (원칙 13).
- 정정은 제안만 — 사용자 [적용] 클릭 강제 (원칙 14-③). 자동 표준화로 사용자 정감 변질 금지.
- 통찰 = 함께 발화한 것의 허브 — 본체 1 sentence 가 retrieve 캐시 노드 전부와 자동 일괄 연결 (Hebbian).
- 시간 기반 자동 경계 없음 — post 는 사용자가 명시적으로 닫을 때까지 열려있고 재진입 가능.

---

## 변경 알림 및 사용자 관여

### 변경 유형별 알림

| 변경 유형 | 알림 방식 | 사용자 액션 |
|-----------|-----------|-------------|
| 지식 축적 (`kind='note'`) | 의미 처리 응답에 `correction_candidates` 누적, 인라인 카드 표시 | [적용] [무시] |
| 통찰 승격 (`kind='insight'`) | 시냅스 세션에서 `[⬆ 통찰로 승격]` 클릭 시 새 insight post 생성 확인 | [취소] / [확인] |
| 삭제/대량 변경 | 처리 전 사전 확인 요청 | 승인/거부 |

### 취소

`post_id` 단위 rollback. 해당 post 의 sentences·`node_sentence_mentions`·`node_category_mentions`·`aliases`·post 행을 CASCADE 로 일괄 정리하고, 공출현 참조가 남지 않은 노드는 고아 정리.

### 정정

`/note` 본문이 항상 편집 가능 상태이므로 별도 "정정" 액션 불필요. 본문 직접 수정은 `/note` 입력 영역에서 즉시 가능 (자동저장이 백그라운드로 받음).

LLM 정정 후보는 의미 처리 직후 / 재진입 시 인라인 카드로 노출:

```
의미 처리 (⌘S / "정리") 직후
  ↓
LLM 정정 카드 (별칭 보호 + 자모 거리 사전 필터 통과 후보)
  ┌─────────────────────────────────┐
  │ "스ㅏ타벅스" → "스타벅스" ?      │
  │ [적용]  [무시]                   │
  └─────────────────────────────────┘
  ↓
[적용] 클릭
  ↓
aliases INSERT (origin='user') + posts.source / sentences 갱신
```

- 자동 적용 금지 (원칙 14-③). 사용자 [적용] 클릭 강제.
- 별칭 등록 토큰 (`스벅` 등) 은 카드에 안 뜸 (사용자 정감 보존).

### 인출 과정 사용자 관여

BFS 탐색의 중간 루프를 사용자가 볼 수 있다. 잘못된 방향으로 탐색이 진행되면 사용자가 개입하여 방향 수정 가능.

---

## 디바이스 벤치마크 (실측, 2026-04-11)

| 디바이스 | 속도 | 조건 |
|----------|------|------|
| Samsung S22U | 7.3초/호출 | GPU, 베이스 모델(파인튜닝 없음), max_tokens=4000 |
| iPhone 15 Pro | 5.3초/호출 | 동일 프롬프트 |

테스트 프롬프트:
```
아래 규칙대로 JSON만 출력. 다른 텍스트 금지.
출력형식: {"nodes":[{"name":"..."}],"deactivate":[]}
규칙: 노드는 원자 개념 하나씩. 1인칭은 "나" 노드.

입력: 나 쿠팡에서 물류 기획 담당하고 있어
알려진 사실: 없음
```

Edge Gallery 설정: Max tokens 4000, TopK 64, TopP 0.95, Temp 1.00, GPU, thinking OFF.

→ 파인튜닝 + 프롬프트 축소 시 **3~5초/호출** 예상.

---

## 모델 변환 파이프라인

```
MLX safetensors → HF PEFT 포맷 (키 리매핑) → convert_lora_to_gguf.py → GGUF LoRA
```

1. **베이스**: ggml-org/gemma-4-E2B-it-GGUF (Q4_K_M) 다운로드. 변환 불필요
2. **어댑터**:
   - adapters.safetensors 키 리매핑 (lora_a→lora_A.weight, prefix 추가)
   - adapter_config.json을 HF PEFT 형식으로 변환
   - llama.cpp `convert_lora_to_gguf.py` 실행
3. **검증**: 동일 입력 → MLX vs GGUF 출력 비교 (20+ 테스트케이스, 95% 일치 기준)

변환 대상:
- **필수 1 종**: `retrieve-expand` — 베이스 모델 단독으로 처리 어려운 키워드 확장 태스크.
- **베이스 + 시스템 프롬프트로 처리 (어댑터 불필요)**: `save-pronoun`·`meta-filter`·`typo-normalize`·`synapse-answer`·`retrieve-filter`. 각각 `docs/*_SYSTEMPROMPT.md` 가 짝.
- **후속 PLAN**: 다른 베이스 모델용 어댑터 (Qwen·Phi 등), 도메인 특화 어댑터.

---

## 파이프라인 최적화

### 대전제: 품질이 먼저다

모바일에서 속도를 줄이겠다고 파이프라인 단계를 함부로 생략하거나 합치면 하이퍼그래프 품질이 망가진다. 각 단계는 독립적인 이유로 존재한다. 최적화는 **"같은 품질을 더 빠르게"** 만 허용한다.

### 자동저장 ≠ 의미 처리 분리 (핵심 최적화)

가장 큰 비용 절감은 **저장을 두 층으로 쪼갠 것**:

| 동작 | 트리거 | LLM | 응답 시간 |
|---|---|---|---|
| 자동저장 | 입력 1.5초 디바운스 + 페이지 이탈 | ❌ 없음 | <50ms |
| 의미 처리 | ⌘S / "정리" 버튼 / 재진입 시 제안 | ✅ 있음 | 0.5~3초 |

매 입력마다 LLM 호출은 모바일에서 지속 불가 (배터리·발열). 자동저장은 sqflite UPDATE 한 줄, 의미 처리는 사용자가 "정리" 의도를 줄 때만. 원칙 9·13 (`DESIGN_PRINCIPLES.md`) 와 파이프라인 세부 (`DESIGN_PIPELINE.md`) 참조.

### 의미 처리 파이프라인 — 각 단계의 품질 역할

```
[의미 처리 — 사용자 명시 트리거 시만]
1. save-pronoun   → "거기" → "스타벅스 강남점"으로 치환. 이거 빠지면 노드가 "거기"로 생성됨
2. Kiwi 추출      → 형태소 분석 기반 노드 (lemma 정규화)
3. meta-filter    → 메타 대화 사전 필터링 ("방금 그거 다시" 같은 발화)
4. negation       → "안 좋아" → 안 노드 분리
5. typo-normalize → LLM 정정 후보 생성 (별칭 보호 + 자모 거리 사전 필터)
                    → UI 카드로 노출, 사용자 [적용] 클릭 강제 (자동 적용 금지)
6. alias-suggest  → 별칭 등록 (사용자 적용 시)

[인출 — /synapse]
7. retrieve-expand → "허리 어때?" → ["허리", "디스크", "L4", "통증"]. 검색 커버리지 결정
8. retrieve-filter → 무관한 문장 제거. 이거 빠지면 응답에 노이즈 섞임
9. category-supplement → 카테고리 바구니 공유로 BFS 단절 보완. 비연결 서브그래프 도달

[응답 — /synapse]
10. synapse-answer → 맥락 기반 합성 (원문 나열이 아니라 융합)
```

### 품질 기준선

GGUF 변환 후 아래 기준을 **반드시** 통과해야 다음 단계 진행:

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
| 어댑터 스왑 오버헤드 제거 | 8-12초 | 없음 | llamadart=LoRA만 적용 |
| HTTP 제거 (인프로세스) | 1-2초 | 없음 | 네트워크 왕복 제거 |
| max_tokens 적정화 | 1-3초 | 없음 | save-pronoun: 256, filter: 8, expand: 256 |

이것만으로 **10-17초 절감**. 파이프라인 로직 변경 없이 달성.

#### B. 품질 보존 (로직 최적화)

| 최적화 | 절감 | 품질 영향 | 조건 |
|--------|------|----------|------|
| save-pronoun regex 사전 체크 | 3-5초 (60-70% 입력) | 없음 | 대명사/날짜 미감지 시 LLM 스킵 |
| alias-suggest 비동기화 | 3초 | 없음 | 응답 후 백그라운드 처리. 즉시 사용 못해도 다음 입력부터 적용 |
| BFS 조기 종료 | 0-5초 | 거의 없음 | 카테고리 보완에서 새 노드 0개면 추가 필터 스킵 |

#### C. 품질 리스크 있음 — 반드시 검증 후 적용

| 최적화 | 절감 | 품질 리스크 | 검증 방법 |
|--------|------|------------|----------|
| retrieve-filter 배치화 (5문장/호출) | 필터 단계 50%+ | 배치 시 문장 간 간섭으로 판단 정확도 하락 가능 | 재학습 + 기존 테스트셋 pass/reject 비교. 일치율 95% 미만이면 폐기 |
| save-pronoun + meta-filter 통합 | 3-5초 | 2B 모델에 두 태스크 동시 학습은 간섭 위험 높음 | 재학습 + 정확도 둘 다 95%+. 하나라도 미달이면 폐기 |

#### D. 금지 — 하면 안 되는 최적화

| 아이디어 | 왜 안 되는가 |
|----------|-------------|
| retrieve-filter 생략 | 노이즈 문장이 답변에 그대로 유입. 엉뚱한 답변 |
| retrieve-expand 생략 | 질문 키워드만으로 BFS 시작 → 동의어/관련어 놓침 → 커버리지 붕괴 |
| save-pronoun 전면 생략 | "거기", "아까", "그 사람" 이 노드로 영구 저장. 하이퍼그래프 오염 |
| typo-normalize 자동 적용 | 사용자 정감 변질 (예: `스벅` → `스타벅스` 강제 표준화). 별칭 보호 정신 위반 |
| 양자화 단계 추가 하향 (Q2/Q3) | JSON 구조 출력 형식 붕괴 직격 |

### Progressive UI — 체감 속도 개선

실제 파이프라인 시간은 그대로 두되, 사용자 체감을 개선:

```
0초   : ⌘S / "정리" 트리거, "⚙ 정리 중..." 표시
~1초  : Kiwi 노드 추출 완료 → "노드 X개 추출" 표시
~2초  : LLM 정정 후보 생성 → 카드 인라인 노출
~3초  : "✦ 정리됨"
```

### 예상 결과

| 시나리오 | 트리거 | 응답 시간 | 비고 |
|---|---|---|---|
| 자동저장 (모든 입력) | 1.5초 디바운스 + 페이지 이탈 | <50ms | sqflite UPDATE 한 줄. LLM 호출 없음 |
| 의미 처리 — 단순 (대명사 없음) | ⌘S / "정리" | 0.5~1.5초 | save-pronoun 스킵, Kiwi + meta-filter + typo-normalize |
| 의미 처리 — 복잡 (대명사·다수 노드) | ⌘S / "정리" | 1.5~3초 | 전 파이프라인 |
| 시냅스 한 턴 (인출+합성) | /synapse 입력 | 5~10초 | retrieve-expand + retrieve-filter + synapse-answer |

A+B 적용은 **품질 동일, 인프라 + 로직 최적화만**. C 는 재학습 + 검증 통과 후에만 추가 적용.

---

## 보안

- 온디바이스 + 로컬 저장이 첫 번째 방어선
- 외부로 나가는 정보는 항상 사용자 최종 확인
- 민감 정보는 LLM이 자동 판단하여 사용자에게 알림
- DB 암호화, 앱 잠금(생체인증) 등 추가 보안 레이어는 후속 PLAN

---

## 리스크

| 리스크 | 영향 | 확률 | 대응 |
|--------|------|------|------|
| MLX→GGUF 변환 품질 저하 | 높음 | 중 | 진입 전 검증. 실패 시 llama.cpp 재학습 |
| llamadart + Gemma 4 호환성 | 높음 | 낮음 | 검증. 실패 시 직접 FFI |
| 6GB 디바이스 메모리 부족 | 중 | 중 | Q4_0 대체 (~1.2GB). mmap 활용 |
| 어댑터 스왑 레이턴시 | 낮음 | 낮음 | 빈번 어댑터 캐시, 파이프라인 재배치 |
| 앱 번들 크기 (1.2GB) | 낮음 | 높음 | 단일 모델 + 앱 번들 고정 정책. 다운로드 인프라는 후속 PLAN |
| convert_lora_to_gguf.py 변경 | 낮음 | 높음 | llama.cpp 커밋 고정, 변환 결과 버전관리 |

---

## 조직 연결 (후속 PLAN)

조직 연결 흐름·UI 는 [`DESIGN_ORG.md`](DESIGN_ORG.md) 의 흐름 명세 + [`DESIGN_PRINCIPLES.md §2`](DESIGN_PRINCIPLES.md) 네트워크 원칙을 단일 출처로 별도 PLAN 에서 구현.

---

## 핵심 파일 참조 — Python frozen 자산 (참조 구현)

알고리즘 명세 — Python frozen 자산을 참조 구현으로 사용. 같은 동작을 Dart 로 재현할 때의 단일 출처.

- `engine/save.py` — 정규식·부정부사·DB upsert 흐름 (Kiwi 단독 추출 + meta-filter + save-pronoun)
- `engine/retrieve.py` — BFS + ADJACENT_SUBCATEGORIES + 필터 루프
- `engine/llm.py` — 시스템 프롬프트 호출 + thinking 블록 제거 regex
- `engine/db.py` — 9 테이블 스키마 (Dart 측은 `EngineConfig.allowedKinds` 로 동적 빌드)
- `api/mlx_server.py` — ModelState 어댑터 스왑 패턴 (Dart 측은 `synapse_engine` 의 `LlamadartBackend` 로 대체)
- `archive/synapse_engine_v15/` — Dart llamadart 통합 + LoRA 핫스왑 인프라 (검증된 자산, 인프라 코드 직접 재사용)
- `data/finetune/models/tasks/retrieve-expand/adapter_config.json` — LoRA 설정 (rank=8, scale=20.0)
