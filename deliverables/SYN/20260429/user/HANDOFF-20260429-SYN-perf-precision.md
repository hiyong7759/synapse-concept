# HANDOFF — /synapse 속도/품질 작업, 다음 세션 진입

브랜치: `feature/synapse-route` (HEAD `54e8e5c`)

## 1. 어디까지 됐나

### 커밋된 흐름 (PLAN-synapse-route 의 AB · B + PLAN-synapse-perf 의 F·C·C+·B·C++·C+++·C++++ + 32K 코멘트 정정)

| commit | 핵심 |
|---|---|
| `1fd9803` | F-측정 — `perf_measure_test.dart` (회귀 도구). dogfood DB 스냅샷으로 `synapseTurn` 1~2회 호출 → `[synapseTurn]` 로그 |
| `273b7cf` | F — `synapseTurn` 5구간 Stopwatch (`kDebugMode` 가드) |
| `32ea05a` | C — retrieve-filter batch + `[o]/[x]` echo 마킹 |
| `64b48e8` | C+ — `_applyFilter` chunk Future.wait |
| `694836e` | B — 단계 indicator UI (`SynapseProgressStage` enum, `_LoadingIndicator` 라벨) |
| `3bae5df` | test — perf_measure 가 답변 텍스트 print |
| `ff31187` | C++ — bare `o`/`x` 프롬프트 + few-shot 2 + batch=5 |
| `b0fff49` | C+++ — batch=5 → 10 |
| `6ac321b` | C++++ — batch=10 → 50 |
| `54e8e5c` | docs/bfs — `8K → 32K` 코멘트 정정 (DESIGN_PIPELINE.md §모델 라인 454) |

### 메모리 추가
- [reference_model_context.md](/Users/hiyong/.claude/projects/-Volumes-macex-workspace-claude-agentic-subagent-team-projects-synapse/memory/reference_model_context.md) — Gemma 4 E2B Q4_K_M = **양자화 32K / 원본 128K**. 8K 로 과소평가 금지

## 2. 미커밋 변경 (working tree)

```
M synapse_engine/lib/src/flow/synapse_flow.dart   ← catch ERROR print (kDebugMode)
M synapse_engine/lib/src/graph/bfs.dart           ← batchSize=maxSentences (사용자 시킨 대로) + [retrieveFilter] in/out count print + flutter/foundation import
M synapse_engine/lib/src/llm/tasks.dart           ← retrieveFilter 의 raw 응답 print (임시 디버그)
M synapse_engine/test/flow/perf_measure_test.dart ← SYNAPSE_TEST_MAX_SENT 환경변수 + 답변 텍스트 print
```

이 중 **임시 디버그 print 3종은 측정 끝나면 제거 또는 `kDebugMode` 가드 정리** 해야 함.

## 3. 핵심 발견

### 3.1 `_maxSentences=50` 은 너무 좁음

dogfood DB (9 posts / 395 sentences / 938 nodes / 4566 mentions) 에서 Q="취업규칙에서 휴가 며칠 주게 되어 있어?" sweep:

| maxSent | bfs (turn1/2) | total (turn1/2) | 휴가 키워드 sentences | ctx 실측 |
|---|---|---|---|---|
| 50 | 393 / 86 ms | 979 / 162 ms | 33 | 50 |
| 100 | 296 / 79 ms | 494 / 113 ms | 43 | 100 |
| 150 | 277 / 111 ms | 504 / 155 ms | 56 | 150 |
| 200 | 282 / 80 ms | 2127 / 119 ms | 65 | 200 |
| 300 | 261 / 86 ms | 461 / 126 ms | 87 | 300 |
| **400** | **315 / 93 ms** | **538 / 134 ms** | **90** | **390 (자연 한도)** |
| 500 | 282 / 126 ms | 488 / 168 ms | 90 | 390 (한도 동일) |

→ **BFS 자연 한도 ≈ 390** (사용자 dogfood DB 기준). 50 한도가 87% 손실이었음.

### 3.2 그러나 이 측정은 retrieve-filter 가 **작동 안 한** 결과

`_applyFilter` 디버그 로그:
```
[retrieveFilter] in=30  out=30  drop=0 (0%)
[retrieveFilter] in=332 out=332 drop=0 (0%)   ← 한 layer 의 candidates 332개 한 번에
[retrieveFilter] in=28  out=28  drop=0 (0%)
```

`drop=0` = LLM filter 가 모든 sentence keep = **fallback all-keep 발동**.

원인: `[retrieveFilter ERROR] Exception: Exception: Initial decode failed` — llamadart 의 `llama_decode` 가 throw, `synapse_flow.dart` 의 try/catch 가 잡고 모두 keep.

즉 휴가 sentences 33→90 증가는 **BFS 자연 확장** 효과지 filter 효과 0. **precision 평가 = 미완**.

### 3.3 `Initial decode failed` 원인 — 미해결

지금까지 의심:
- ❌ ~~contextSize 4K 너무 작음~~ — `LlamadartInferenceBackend.contextSize=4096` 인데 32K → 16K → 8K 순으로 시도해보니 모델 로드 단계 **segfault**. 즉 contextSize 변경이 segfault 의 직접 원인이라 4K 로 복귀. 진짜 `Initial decode failed` 의 원인은 contextSize 가 아닐 수 있음 — 사용자가 "그 문제 맞아?" 의문 제기

다른 후보 (다음 세션 점검):
1. **KV 캐시 누적** — llamadart 가 `_sharedPrefixLength` 로 prefix 재사용. 매 generate 호출 후 user prompt 가 KV 에 남아 누적 → 4K 한도 초과 → fail
2. **prompt 형식 토큰화 실패** — 시스템 프롬프트의 「」 같은 특수 문자, `1./2./...` 형식
3. **Future.wait 동시 호출 (chunks≥2)** — 단일 chunk 호출에서도 ERROR 났으니 동시성만은 아님
4. **maxTokens 설정 vs n_batch mismatch** — llamadart 의 `maxBatchTokens` default 0 → tokenCount. n_batch 옵션 필요할 수도
5. **GGUF metadata 의 n_ctx_train vs llamadart contextSize 불일치**
6. **gpuLayers=99 + Metal 한도** — 16K/32K 시 segfault 의 진짜 원인일 가능성

### 3.4 사용자 dogfood 환경에서는?

dogfood 시 사용자가 답변을 받았다고 했음 → synapseAnswer LLM 호출은 정상 작동했을 가능성. 단:
- retrieve-filter 도 작동했는지 = **확인 안 됨** (dogfood 로그 안 봄)
- 측정 환경 ≠ dogfood 환경 (build flavour, cold cache 등). 측정 환경 한정 문제일 수도

## 4. 사용자 결정사항 (이번 세션 합의)

- 마일스톤 C/E (통찰 승격, PostSidebar 점검) **보류**
- 속도 개선 우선
- `_maxSentences = 500` (안전 마진 두고 최대) **사용자 명시**
- `_filterBatchSize = _maxSentences` (한 호출당 다 평가) **사용자 명시**
- 정확도 측정 **요구** (recall 만 보지 말고 precision 도) — 미완
- 그래프 커질 때 예측 **요구** — 미완
- 작업 완료 후 **main 머지 + 브랜치 정리 + 새 워크트리 규칙** 시작 (사용자 명시, 후속)

## 5. 다음 세션 진입 권장 순서

### A. 미커밋 변경 정리
1. 임시 print 3종 평가 — `kDebugMode` 가드로 유지 vs 제거
2. `bfs.dart` 의 `batchSize=maxSentences` 결정 (사용자는 그렇게 시켰지만 작은 모델이 한 번에 처리 못 할 수도 → batch=50 안전)
3. `perf_measure_test.dart` 의 `SYNAPSE_TEST_MAX_SENT` env 받기는 회귀 도구로 유지 가능

### B. `Initial decode failed` 진단 (필수)
1. `_applyFilter` Future.wait 폐지 → 직렬 await for-loop 로 변경 후 측정 — 동시성 원인 분리
2. ERROR 그대로면 prompt 단순화 시도 (1./2. 제거, few-shot 제거)
3. llamadart `_sharedPrefixLength` 동작 확인 — KV 캐시 reset API 있는지
4. `LlamaEngine.loadModel` 에 `contextSize` 변경 + `gpuLayers=0` (CPU only) 시도 — segfault 가 GPU 메모리인지 분리
5. 또는 dogfood Flutter 앱에서 직접 `[retrieveFilter] in/out` 로그 보고 **측정 환경 한정 문제인지** 검증

### C. precision 평가 (B 완료 후)
filter 작동 시 입력 N → 출력 M, drop 비율 측정. 휴가 / 무관 sentence 분류로 precision 계산.

### D. `_maxSentences` 정식 결정
- precision 양호하면 `_maxSentences=400~500` 으로 인상 commit (현재 default 50)
- precision 떨어지면 더 작은 값 (200?)

## 6. 측정 환경 사용법

```bash
# DB 복사 (사용자 dogfood DB → tmp)
cp ~/Library/Containers/dev.synapse.synapseApp/Data/Documents/synapse.db /tmp/synapse_perf.db

# 측정
cd synapse_engine
SYNAPSE_TEST_MODEL=/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf \
SYNAPSE_TEST_DB=/tmp/synapse_perf.db \
SYNAPSE_TEST_PROMPT_DIR=../docs \
SYNAPSE_TEST_MAX_SENT=500 \
flutter test test/flow/perf_measure_test.dart --tags perf
```

`[synapseTurn] expand=Xms match=Xms bfs=Xms answer=Xms persist=Xms total=Xms (ctx=N)` 로그 + `[retrieveFilter] in=N out=M drop=K (X%)` 로그 + 답변 텍스트 출력.

## 7. 모델 환경 (절대 잊지 말 것)

- 모델: **Gemma 4 E2B-it Q4_K_M GGUF** (`/Volumes/macex/models/gemma-4-E2B-it-Q4_K_M.gguf`, 3.1GB)
- **양자화 컨텍스트 32K / 원본 128K** ([DESIGN_PIPELINE.md:454](docs/DESIGN_PIPELINE.md#L454))
- llamadart 0.6.10, `LlamadartInferenceBackend.contextSize` default = **4096** ← 의심 후보
- 어댑터 0개 (모든 LLM task = base + system prompt)
- macOS Metal GPU, gpuLayers=99 (all)

## 8. PLAN 파일

- [PLAN-20260429-SYN-synapse-route.md](deliverables/SYN/20260429/user/PLAN-20260429-SYN-synapse-route.md) — /synapse 라우트 1차 (AB + B 끝, C·E 보류)
- [PLAN-20260429-SYN-synapse-perf.md](deliverables/SYN/20260429/user/PLAN-20260429-SYN-synapse-perf.md) — 속도 개선 (F·B·C·C+ 끝, A 스트리밍 보류)

## 9. 후속 일괄 정리 (사용자 명시)

전체 작업 완료 후:
1. main 머지
2. 브랜치 정리 (feature/v22-rewrite, feature/synapse-route, feature/hypergraph-perf 등)
3. 새 워크트리 규칙 하에 작업 시작
