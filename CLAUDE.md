# Synapse — 개인 지식 그래프

## 핵심 원칙 (이것부터 읽어라)

1. **노드는 원자다.** 하나의 개념 = 하나의 노드. 중복 생성 금지. 대소문자, 언어 불문 같은 개념이면 같은 노드.
2. **엣지는 선택자다.** 모든 관계, 속성, 상세 정보는 엣지로 표현한다. 노드에 데이터를 넣지 않는다.
3. **meta 컬럼, JSON 필드 같은 것을 노드에 추가하지 마라.** "기간", "전공", "담당업무" 같은 상세 정보도 전부 엣지다.
4. **동의어/다국어는 same 엣지 또는 aliases.** React Native ──(same)── 리액트 네이티브. 별칭은 aliases 테이블에 등록.
5. **BFS 전체 탐색 → LLM이 필터링.** 탐색 결과가 넓어도 잘라내지 마라. 사용자가 쌓은 맥락이다.
6. **모든 질문은 개인 맥락이 있으면 더 나은 답을 만든다.**

## 구조

```
노드 = 개념 (React Native, 허리디스크, 맥미니, 조용희)
엣지 = 관계 (link/same/similar + label)
별칭 = 키워드 매칭 강화 (aliases 테이블)
필터 = 맥락에서 제외할 도메인/노드 프리셋
```

상세 정보 표현 예시:
```
㈜더나은 ──(입사)── 2018.02
서일대학 ──(전공)── 산업시스템경영
허리디스크 ──(부위)── L4-L5
```

노드에 description, meta, detail 같은 필드를 추가하는 것은 이 설계를 위반한다.

## DB 스키마 (v5)

```sql
nodes:   id, name, domain, status(active|inactive), source(user|ai), weight, safety, safety_rule, created_at, updated_at
edges:   id, source_node_id, target_node_id, type, label, created_at, last_used
aliases: alias, node_id (PK)
filters: id, name
filter_rules: filter_id, domain, node_id, action(exclude)
```

- status는 active | inactive 2종. deleted 없음. 비활성화하면 엣지 보존됨.
- sid, confidence, exposure_log는 v5에서 제거됨.
- edges.last_used로 불용 엣지 판단.

## 스크립트

| 명령 | 용도 |
|------|------|
| `./synapse "질문"` | 맥락 자동 주입 + LLM 답변 |
| `python3 scripts/get_context.py "질문"` | 맥락 프롬프트만 추출 |
| `python3 scripts/add_nodes.py '<json>'` | 노드/엣지 추가 |
| `python3 scripts/list_nodes.py nodes` | 노드 목록 |
| `python3 scripts/list_nodes.py edges` | 엣지 목록 |
| `python3 scripts/update_node.py <명령> <인자>` | 수정/비활성화 |
| `python3 scripts/check_onboarding.py` | 온보딩 상태 확인 |

## DB

SQLite (`synapse.db`). 스키마는 `scripts/init_db.py` 참고.

## 아키텍처

```
synapse/core/     ← npm 패키지 (TypeScript). LLM 없음. 순수 로직.
poomacy/          ← 채팅 + 온보딩 + 구조화 + UI. @synapse/core import.
claude code/      ← 기존 Python 스킬 유지 (v5 스키마 반영)
```

## 상세 설계

`KNOWLEDGE_MODEL_V4.md` 참고.
