# F1 진입 프롬프트 — synapse_engine Dart 패키지 scaffold

> 다음 세션 시작 시 이 프롬프트를 그대로 입력.

---

PLAN-20260425-SYN-flutter-rewrite 의 F1 마일스톤 진입한다.

## 현재 상태

- 브랜치: `feature/v22-rewrite`
- 작업 디렉토리: `/Volumes/macex/workspace/claude-agentic-subagent-team/projects/synapse`
- F0 완료 (commit `351cf13` 까지) — 설계 문서 12 종 v22 2차안 정합 + 변경 이력 잡음 제거 + DESIGN_APP/UI 책임 분리 + /hypergraph 라우트 + 그래프 패널 명세
- 어댑터 제거 PoC 는 별도 브랜치/세션에서 진행 중 — 이 세션에선 무관

## F1 명세 (PLAN §3)

| 항목 | 내용 |
|---|---|
| 산출물 | `synapse_engine/pubspec.yaml`, `synapse_engine/lib/synapse_engine.dart` 진입점, `synapse_engine/lib/src/` 구조 (db, llm, graph, kiwi, flow, markdown, models, internal) |
| 패키지 위치 | 프로젝트 루트 아래 `synapse_engine/` (시냅스 앱 `app/` 과 monorepo 로 공존) |
| 검증 | `dart pub get` 성공 + 빈 진입점 import 성공 |

## 단일 출처 문서 (이 안에 모든 명세)

- `docs/DESIGN_ENGINE.md` — 2 계층 API (`SynapseFlow` / `LlmTasks` / `GraphOps`) + `allowedKinds` / `reservedKinds` + 패키지 디렉토리 구조 + 갑질 재사용 시나리오
- `docs/DESIGN_HYPERGRAPH.md` — 9 테이블 스키마 (F2 에서 구현)
- `docs/DESIGN_APP.md` — Flutter 기술 스택·번들 정책·디바이스 벤치마크
- `docs/DESIGN_PIPELINE.md` — 자동저장·의미 처리·인출 파이프라인 (F3~F5 에서 구현)

## 참고 자산

- `archive/synapse_engine_v15/` — 검증된 인프라 (llamadart 통합·LoRA 핫스왑·thinking 블록 제거·Kiwi WASM). **인프라 코드만 참고**, 데이터 흐름·스키마는 v22 2차안 신규 구현
- `engine/` (Python frozen) — 알고리즘 참조 구현

## 진행 룰 (전역 CLAUDE.md)

1. 마일스톤 단위로 커밋
2. F1 끝나면 진행 보고 → 사용자 "계속" / "ㄱ" / "고" 승인 대기
3. 보고 형식: `✅ 완료 / 📁 변경 파일 / ➡️ 다음 단계 / 🔍 검토 체크리스트 (완결성·회귀 리스크·원칙 준수·롤백 가능성)`
4. F2 (DB 스키마) 으로 자동 진입 금지

## 작업 시작

PLAN F1 산출물 표에 따라 `synapse_engine/` 디렉토리에 Dart 패키지 scaffold 진행.
