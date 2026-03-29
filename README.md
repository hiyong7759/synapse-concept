# Synapse

Claude Code에 나를 기억하게 만드는 개인 지식 그래프.

![Synapse Graph View](docs/synapse.png)

## 왜 필요한가

Claude에게 "운동 추천해줘"라고 물으면, 일반적인 운동 목록을 준다.
하지만 나는 허리디스크가 있고, 데드리프트를 하다가 재발한 적이 있다.

**Synapse가 없으면:**
```
나: 운동 추천해줘
AI: 스쿼트, 데드리프트, 벤치프레스를 추천합니다.
```

**Synapse가 있으면:**
```
나: 운동 추천해줘
AI: L4-L5 허리디스크 이력이 있으시네요. 데드리프트 대신 트랩바를 추천드리고,
    수영은 허리에 부담 없이 전신 운동이 가능합니다.
```

이건 운동만이 아니다.

```
"빌드가 안 돼"
  → 맥미니 M4 + Expo + React Native 환경을 이미 알고 있어서, 바로 진단

"이력서 써줘"
  → 경력, 기술스택, 프로젝트를 전부 알고 있어서, 누락 없이 구성

"점심 뭐 먹을까"
  → 카페인 알레르기가 있다는 걸 알고 있어서, 녹차 음료 제외
```

나에 대한 정보가 들어가면, 모든 답변이 달라진다.

## 어떻게 동작하나

내 경험과 정보를 **노드**(개념)와 **엣지**(관계)로 저장한다.
질문하면 관련 맥락만 자동으로 꺼내서 프롬프트에 넣어준다.

```
질문 → 키워드 추출 → 그래프 탐색 → 맥락 조립 → AI가 나를 아는 상태로 답변
```

모든 데이터는 내 컴퓨터에만 저장된다. 서버에 올라가지 않는다.

## 설치

```bash
# 1. 마켓플레이스 등록
/plugin marketplace add hiyong7759/synapse

# 2. 플러그인 설치
/plugin install synapse@synapse
```

## 시작하기

설치하면 온보딩이 시작된다.
나에 대해 조금만 알려주면, 그때부터 모든 대화가 달라진다.

편한 것부터 알려주면 된다:
- 이력서나 자기소개
- GitHub URL
- 개발 환경 (장비, OS, 도구)
- 진행 중인 프로젝트
- 건강이나 알레르기
- 관심사나 취미

하나만 알려줘도 시작할 수 있고, 대화하면서 자연스럽게 쌓을 수도 있다.

## 스킬

| 스킬 | 설명 |
|------|------|
| `/context` | 질문에 맞는 맥락을 그래프에서 찾아 답변에 반영 |
| `/save` | 대화에서 개념과 관계를 추출하여 그래프에 저장 |
| `/visualize` | 인터랙티브 그래프 뷰를 브라우저에서 열기 |

## 동작 원리

```
질문 입력
  → 키워드 추출
  → 개인 그래프에서 BFS 탐색
  → 관련 서브그래프를 프롬프트 맥락으로 조립
  → LLM이 나의 맥락을 반영하여 답변
```

노드는 원자적 개념 (React Native, Docker, 맥미니).
엣지는 개념 사이의 관계 (스킬, 스펙, 위치, 동의어).
모든 데이터는 로컬 `~/.synapse/synapse.db`에 저장.

## CLI 사용법

```bash
# 맥락 자동 주입 + 질문
./synapse "이력서 만들어줘"

# 그래프 관리
python3 scripts/list_nodes.py nodes          # 노드 목록
python3 scripts/list_nodes.py edges          # 엣지 목록
python3 scripts/list_nodes.py domains        # 도메인 목록
python3 scripts/add_nodes.py '<json>'        # 노드/엣지 추가
python3 scripts/update_node.py <명령> <인자>  # 수정/삭제
python3 scripts/visualize.py                 # 그래프 뷰 열기
```

## 데이터 위치

| 파일 | 경로 |
|------|------|
| 데이터베이스 | `~/.synapse/synapse.db` |
| 그래프 뷰 | `~/.synapse/graph.html` |

`SYNAPSE_DATA_DIR` 환경변수로 경로 변경 가능.

## 요구사항

- Python 3.10+
- SQLite (기본 내장)
- Claude Code

## 라이선스

MIT
