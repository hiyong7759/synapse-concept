"""Synapse Graph Engine.

Status: **frozen at v22 1차안** (2026-04-25). 추가 v22 2차안 정합 작업 없음.
v22 2차안 (note 단일 + 자동저장/의미 처리 분리 + 2 계층 API) 은 Flutter
`synapse_engine` 패키지로 신규 구현된다 (PLAN-20260425-SYN-flutter-rewrite).

이 Python 엔진은:
- 학습·dogfood 환경의 참조 구현으로 보존
- 어댑터 학습·MLX 추론·gabjil 실험 등 데이터 작업의 기반
- v22 2차안 차이는 Flutter 측이 직접 반영 (kind 'chat' 제거 → 'note' 단일,
  save() mode 인자 폐지, 자동저장/의미 처리 두 엔드포인트 분리, LLM 정정 후보)
"""
