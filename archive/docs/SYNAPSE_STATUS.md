# Synapse 프로젝트 현황 (2026-03-29)

## 한 줄 정의

개인 정보를 그래프로 구조화해두고, 질문에 맞는 맥락만 골라서 LLM 프롬프트를 만들어주는 엔진.

## 아키텍처

```
synapse/core/     ← npm 패키지 (@synapse/core). LLM 없음. 순수 로직.
poomacy-v2/       ← React + Vite + Tailwind. NLI + AI Chat 통합. @synapse/core import.
claude code/      ← 기존 Python 스킬 유지 (v5 스키마 반영)
```

- Synapse = 맥락 저장소 + 맥락 제공 엔진. 채팅 앱이 아님.
- Core만 패키지로 분리. 채팅/온보딩/구조화는 소비자 앱(Poomacy)이 담당.
- 보안: 그래프는 절대 서버에 저장하지 않음. 완전 로컬 (IndexedDB/OPFS).

## DB 스키마 (v5)

```sql
-- 노드: 수평한 단어/개념
nodes: id, name, domain, status(active|inactive), source(user|ai),
       weight, safety, safety_rule, created_at, updated_at

-- 엣지: 노드 사이의 관계
edges: id, source_node_id, target_node_id, type, label, created_at, last_used

-- 별칭: 키워드 매칭 강화
aliases: alias, node_id (PK)

-- 필터: 맥락에서 제외할 도메인/노드 프리셋
filters: id, name
filter_rules: filter_id, domain, node_id, action(exclude)
```

- status: active | inactive 2종. deleted 없음. 비활성화하면 엣지 보존.
- v5에서 제거: sid, confidence, exposure_log.

## 탐색 규칙

```
1. 키워드 정규화: 한국어 조사 제거 + 불용어 필터
2. 시작 노드 매칭: aliases → 노드명 substring → 엣지 type 순서
3. 도메인 매칭: KNOWN_DOMAINS (DB에 노드 없어도 인식)
4. BFS: 정방향만. 본인 노드 경유 차단 (무한 확산 방지).
5. 교집합: 시작 노드끼리 엣지로 연결 → AND, 비연결 → OR.
6. 도메인 필터: 도메인 키워드가 있으면 해당 도메인 결과만 유지.
7. missing: 매칭 실패 키워드, 노드 없는 도메인 → 안내 메시지 반환.
```

## Core 패키지 (@synapse/core)

위치: `synapse/core/`

### 파일 구조
```
core/src/
  types.ts           — Node, Edge, Alias, Filter 등 18개 타입
  db-adapter.ts      — BetterSqliteAdapter (Node.js)
  sql-js-adapter.ts  — SqlJsAdapter (브라우저, IndexedDB 영속화)
  graph-store.ts     — GraphStore: CRUD 14개 메서드
  graph-search.ts    — GraphSearch: BFS 탐색 + 키워드 매칭
  prompt-builder.ts  — formatPrompt: 서브그래프 → 프롬프트 텍스트
  index.ts           — Synapse 클래스 + createSynapse() 팩토리
```

### API

```typescript
// 초기화
import { createSynapse } from '@synapse/core';              // Node.js
import { SqlJsAdapter, GraphStore, GraphSearch } from '@synapse/core'; // 브라우저

// Node.js
const synapse = createSynapse('~/.synapse/synapse.db');

// 브라우저
const db = await SqlJsAdapter.create({
  data: savedData,                              // IndexedDB에서 로드
  onSave: (data) => saveToIndexedDB(data),      // 변경 시 저장
});
const store = new GraphStore(db);
const search = new GraphSearch(db);

// 맥락 조회
search.getContext("맥미니 개발환경")
// → { status, prompt, nodes_used, safety_nodes, node_count, edge_count, missing? }

// 노드/엣지 추가
store.addBatch({ nodes: [{name, domain, source?, safety?}], edges: [{source, target, type?, label?}] })

// 조회
store.listNodes({ domain?, status?, search?, limit? })
store.listEdges(nodeName?)
store.listDomains()
store.showNode(name)         // 상세 + 연결된 엣지
store.findNode(name)         // 정확→substring 매칭

// 수정
store.updateNode(name, { domain?, status?, safety? })
store.deactivateNode(name)   // inactive + 고아 노드 알림
store.restoreNode(name)      // active 복원
store.deleteEdge(src, tgt)
store.updateEdge(src, tgt, { type?, label? })
```

## 설계 결정

- 필터: exclude만 기록. "렌즈" → "필터"로 이름 변경.
- 정방향 BFS만. 역방향 필요하면 엣지 추가로 해결.
- aliases 자동 감지 어려움 → 수동 등록 or missing 안내.
- 작은 로컬 LLM(1~4B) 키워드 분류 시도 → 포맷 준수 어려워서 보류.
- 데이터 품질이 핵심. 탐색 로직 충분, 엣지를 촘촘하게 넣는 게 중요.
- LLM과의 상호작용이 사용자 경험 결정 → Poomacy에서 풀 문제.

## 현재 그래프 데이터

- 83 active 노드, 162 엣지, 17개 도메인
- DB 위치: `~/.synapse/synapse.db`
- Python 스킬도 같은 DB 사용 (Claude Code용)

## 다음: Poomacy NLI Chat 통합

상세 계획: `synapse/docs/NLI_CHAT_PLAN.md`
