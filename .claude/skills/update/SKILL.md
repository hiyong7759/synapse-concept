---
name: update
description: 시냅스 그래프의 노드와 엣지를 수정, 비활성화, 삭제, 복원한다. "이거 잘못됐어", "도메인 바꿔줘", "이 노드 지워", "연결 끊어줘", "관계 수정해줘" 같은 그래프 교정 요청에 사용한다. 노드뿐 아니라 엣지(관계)도 수정/삭제할 수 있다.
disable-model-invocation: true
---

# Synapse Update — 노드 교정

그래프의 노드를 수정하거나 비활성화/삭제한다.

## 사용법

`$ARGUMENTS`를 파싱하여 적절한 명령을 실행한다.

### 노드 속성 수정
```bash
python3 scripts/update_node.py update "노드이름" '{"domain": "새도메인"}'
```

### 노드 비활성화
```bash
python3 scripts/update_node.py deactivate "노드이름"
```

비활성화 시 고아 노드가 발생하면 사용자에게 알린다:
```
⚠️ "Kubernetes"를 비활성화하면 다음 노드가 고아가 됩니다: Helm, kubectl
이 노드들도 비활성화할까요?
```

### 노드 삭제 (비활성화)
```bash
python3 scripts/update_node.py delete "노드이름"
```

delete는 deactivate와 동일하게 동작한다 (status → inactive). 노드와 엣지가 보존되며 복원 가능.

### 노드 복원
```bash
python3 scripts/update_node.py restore "노드이름"
```

### 엣지 삭제
```bash
python3 scripts/update_node.py delete-edge "소스노드" "타겟노드"
```

### 엣지 수정 (label 변경)
```bash
python3 scripts/update_node.py update-edge "소스노드" "타겟노드" '{"label": "새라벨"}'
```

## 교정 철학

- 처음부터 완벽할 필요 없다
- 결과물이 이상하면 → 노드 목록에서 원인 찾아 수정
- 비활성화가 기본 (20~30년 전 경험도 필요해질 수 있음)
- inactive 노드는 탐색 대상에서 빠지지만 그래프에 남음 (엣지 보존)
- status는 active | inactive 2종만 존재
