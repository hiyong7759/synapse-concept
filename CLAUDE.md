# Synapse — 개인 지식 그래프

## 핵심 원칙 (이것부터 읽어라)

> **원칙 전체 목록은 `docs/DESIGN_PRINCIPLES.md` — 모든 설계 문서의 원칙이 통합된 단일 출처.**

프로젝트 전체를 관통하는 13개 원칙 요약 (상세는 `DESIGN_PRINCIPLES.md §1` 참고):

**존재론**
1. 언급된 것만 존재한다.
2. 노드는 원자다 (품사 무관, 하나의 개념 = 하나의 노드).
3. 외부 참조는 저장하지 않는다.

**구조**
4. 엣지는 문장을 뛰어넘는 의미 관계다 (조사 엣지 폐기, `/review` 승인 필요).
5. 엣지는 유방향이다.
6. 동의어/다국어는 aliases.
7. meta 컬럼·JSON 필드를 노드에 추가 금지 (예외: `node_categories`).

**저장과 승인**
8. 저장과 합성의 분리 (자동 저장은 sentence + 노드 + `node_mentions` + `unresolved_tokens`까지).
9. DB에 있는 것은 전부 승인된 것.
10. 입력 단위 = 마크다운 구조화된 게시물.

**동작**
11. 도메인은 관찰하는 것이다.
12. 지능체는 분리되어 있다 (시냅스는 LLM 없이도 동작).
13. 모든 질문은 개인 맥락이 있으면 더 나은 답을 만든다.

개인/조직 모드, /review 검토, 카테고리, UI, 데이터 정책 원칙 → `docs/DESIGN_PRINCIPLES.md §2~§6` 참고.

## CLI

```bash
python3 -m engine.cli           # 대화형 (MLX 서버 필요: python api/mlx_server.py)
python3 -m engine.cli --no-llm  # LLM 없이 BFS 구조만 (독립 동작 보장)
python3 -m engine.cli --stats   # DB 통계
python3 -m engine.cli --reset   # DB 초기화
python3 -m engine.cli --typos   # 오타 의심 노드 쌍 스캔
```

DB 위치: `~/.synapse/synapse.db` (SYNAPSE_DATA_DIR 환경변수로 변경 가능)

## 파인튜닝/학습 작업

학습·파인튜닝 관련 작업 전 **반드시 `docs/DESIGN_FINETUNE.md`의 "작업 규칙" 섹션을 먼저 읽어라.**

핵심: 추측 금지 · 매번 환경 검증 · 새 환경/버전/데이터는 100 iters 소규모 검증 필수 · 하이퍼파라미터 임의 변경 금지.

## 환경

- **학습**: RunPod (FP16, google/gemma-4-E2B-it)
- **로컬 추론**: Mac M4 + MLX 4bit (`api/mlx_server.py`)
- **학습 데이터**: `data/finetune/`
- **학습 모델 (로컬)**: `data/finetune/models/`
- **RunPod 산출물**: `runpod_output/adapters/`

## 상세 설계 (`docs/`)

| 문서 | 주제 |
|---|---|
| `DESIGN_PRINCIPLES.md` | **모든 설계 원칙의 단일 출처** (존재론·구조·저장·동작·모드·/review·카테고리·UI·데이터 정책) |
| `DESIGN_OVERVIEW.md` | 제품 비전·데이터 정책 |
| `DESIGN_GRAPH.md` | 그래프 모델 — 노드·엣지·스키마 v13 |
| `DESIGN_PIPELINE.md` | 저장·인출·응답 파이프라인 세부 + 날짜 처리 규칙 |
| `DESIGN_ENGINE.md` | 엔진 패키지 구조 (모바일 포팅 포함) |
| `DESIGN_REVIEW.md` | `/review` 섹션별 런타임 제안 + 승인 흐름 |
| `DESIGN_CATEGORY.md` | 카테고리 분류체계 (19 대분류) + 인접 맵 |
| `DESIGN_FINETUNE.md` | 파인튜닝 — 작업 규칙 · 태스크 정의 · 하이퍼파라미터 |
| `DESIGN_APP.md` | 비서 앱 |
| `DESIGN_MOBILE.md` | 모바일 포팅 |
| `DESIGN_ORG.md` | 개인-조직 연결 |
| `DESIGN_UI.md` | 채팅·그래프 뷰 UI |
