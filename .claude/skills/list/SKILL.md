---
name: list
description: 시냅스에 뭐가 저장되어 있는지 보여준다. "내 그래프 보여줘", "뭐 기억하고 있어?", "저장된 거 확인", "시냅스 목록", 특정 도메인이나 노드를 찾을 때 사용. 사용자가 자신의 지식 그래프 내용을 궁금해하면 이 스킬을 호출한다.
disable-model-invocation: true
---

# Synapse List — 그래프 조회

개인 지식 그래프의 내용을 조회한다.

## 사용법

`$ARGUMENTS`를 파싱하여 적절한 명령을 실행한다.

### 전체 노드 조회
```bash
python3 scripts/list_nodes.py nodes
```

### 도메인 필터
```bash
python3 scripts/list_nodes.py nodes "기술"
```

### 도메인 요약
```bash
python3 scripts/list_nodes.py domains
```

### 특정 노드의 연결 보기
```bash
python3 scripts/list_nodes.py show "React Native"
```

### 엣지 조회
```bash
python3 scripts/list_nodes.py edges
python3 scripts/list_nodes.py edges "맥미니"
```

## 출력 형식

결과를 사용자가 읽기 쉽게 정리하여 보여준다:

- 노드: 이름, 도메인, weight, safety 여부
- 엣지: source ──(label)── target 형태
- 도메인: 도메인명 + 노드 수

inactive 노드는 기본 비표시. 사용자가 요청하면 포함.
