#!/usr/bin/env python3
"""잘못 라벨링된 95건 빈 nodes 레코드를 직접 재라벨링.

실측 결과 (eval_extract_core.py + 빈 nodes 분류):
- 빈 nodes 143건 중 "기타 95건"은 실제 노드가 있어야 할 일상 문장이 빈 배열로 라벨됨
- 이것이 "daily → 빈 nodes" 과적합의 직접 원인

이 스크립트는 각 문장에 올바른 nodes/retention/category를 직접 매핑.
A 타입(상태변경 11건), B 타입(인사 37건)은 그대로 유지.
"""
from __future__ import annotations
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finetune" / "tasks" / "extract-core"

# user 문장 → (retention, [(name, category), ...])
# drop 대상(진짜 대화체)은 값 None
RELABEL: dict[str, tuple[str, list[tuple[str, str]]] | None] = {
    "머리 아파서 두통약 먹었어": ("daily", [("머리", "BOD.part"), ("두통약", "BOD.medical")]),
    "2026-03-14 날씨 좋다": ("daily", [("2026-03-14", "NAT.weather")]),
    "2026-02-19 09:10에 산책 다녀왔어": ("daily", [("2026-02-19", "HOB.outdoor"), ("09:10", "HOB.outdoor"), ("산책", "HOB.outdoor")]),
    "2026-02-13 좀 쌀쌀하네": ("daily", [("2026-02-13", "NAT.weather")]),
    "아 머리 아파 2026-01-22": ("daily", [("머리", "BOD.part"), ("2026-01-22", "BOD.part")]),
    "2026-04-07 날씨 좋다": ("daily", [("2026-04-07", "NAT.weather")]),
    "산책 좀 하고 왔어": ("daily", [("산책", "HOB.outdoor")]),
    "뉴스 보니까 좀 우울하네": ("daily", [("뉴스", "SOC.news"), ("우울", "MND.emotion")]),
    "2026-01-08 회의 길었다": ("daily", [("2026-01-08", "WRK.workplace"), ("회의", "WRK.workplace")]),
    "뭐 먹을까 고민 중이야": ("daily", [("고민", "MND.emotion")]),
    "아 2026-02-05 너무 피곤해": ("daily", [("2026-02-05", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "머리 좀 아파서 타이레놀 먹었어": ("daily", [("머리", "BOD.part"), ("타이레놀", "BOD.medical")]),
    "아 2026-01-19 기분 좀 별로야": ("daily", [("2026-01-19", "MND.emotion"), ("기분", "MND.emotion")]),
    "밖에 비 엄청 온다 우산 챙겨": ("daily", [("비", "NAT.weather"), ("우산", "LIV.supply")]),
    "아 2026-02-23 좀 피곤하다": ("daily", [("2026-02-23", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "2026-03-02 날씨 진짜 좋다": ("daily", [("2026-03-02", "NAT.weather")]),
    "2026-04-02 뉴스 좀 봤어": ("daily", [("2026-04-02", "SOC.news"), ("뉴스", "SOC.news")]),
    "2026-01-15 비 오니까 기분이 좀 가라앉네": ("daily", [("2026-01-15", "NAT.weather"), ("비", "NAT.weather"), ("기분", "MND.emotion")]),
    "아 진짜 졸려 커피 마셔야겠다": ("daily", [("졸려", "BOD.sleep"), ("커피", "FOD.drink")]),
    "아 피곤해 좀 쉬고 싶다": ("daily", [("피곤", "BOD.sleep")]),
    "좋은 아침이에요": None,  # 인사
    "시험 끝나서 너무 홀가분하다": ("daily", [("시험", "EDU.exam"), ("홀가분", "MND.emotion")]),
    "2026-01-03 넷플릭스로 영화 한 편 봤어": ("daily", [("2026-01-03", "CUL.media"), ("넷플릭스", "CUL.media"), ("영화", "CUL.film")]),
    "날씨 좋아서 기분 좋다": ("daily", [("기분", "MND.emotion")]),
    "적금 깨고 전세 대출 갚았어": ("memory", [("적금", "MON.saving"), ("전세 대출", "MON.loan")]),
    "잘 잤어 2026-01-12 컨디션 좋아": ("daily", [("2026-01-12", "BOD.sleep"), ("컨디션", "BOD.sleep")]),
    "주식 2026-04-12 좀 빠졌네 짜증나": ("daily", [("주식", "MON.invest"), ("2026-04-12", "MON.invest"), ("짜증", "MND.emotion")]),
    "2026-04-05 14:15에 산책하고 왔어 날씨 좋다": ("daily", [("2026-04-05", "HOB.outdoor"), ("14:15", "HOB.outdoor"), ("산책", "HOB.outdoor")]),
    "나 우울증 완치 판정 받았어": ("memory", [("나", "PER.individual"), ("우울증", "MND.mental"), ("완치 판정", "BOD.medical")]),
    "아 월요일 출근하기 싫다": ("daily", [("월요일", "WRK.workplace"), ("출근", "WRK.workplace")]),
    "점심에 카페에서 공부했어": ("daily", [("점심", "FOD.recipe"), ("카페", "FOD.restaurant"), ("공부", "EDU.academic")]),
    "2026-01-24 좀 피곤하네": ("daily", [("2026-01-24", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "시험 공부 하기 싫다 놀고 싶어": ("daily", [("시험", "EDU.exam"), ("공부", "EDU.academic")]),
    "2026-03-20 12:00에 두통약 먹었어": ("daily", [("2026-03-20", "BOD.medical"), ("12:00", "BOD.medical"), ("두통약", "BOD.medical")]),
    "나 대출 다 갚았어": ("memory", [("나", "PER.individual"), ("대출", "MON.loan")]),
    "퇴근하고 싶다": ("daily", [("퇴근", "WRK.workplace")]),
    "2026-02-08 기분 좀 괜찮다": ("daily", [("2026-02-08", "MND.emotion"), ("기분", "MND.emotion")]),
    "회의 너무 길었어 지친다": ("daily", [("회의", "WRK.workplace")]),
    "2026-02-18 커피 세 잔이나 마셨네": ("daily", [("2026-02-18", "FOD.drink"), ("커피", "FOD.drink"), ("세 잔", "FOD.drink")]),
    "2026-03-04 회의 너무 길었다": ("daily", [("2026-03-04", "WRK.workplace"), ("회의", "WRK.workplace")]),
    "수고하셨습니다 퇴근하세요": None,  # 인사
    "2026-03-03 친구 만나서 카페에서 수다 떨었어": ("daily", [("2026-03-03", "PER.friend"), ("친구", "PER.friend"), ("카페", "FOD.restaurant"), ("수다", "REL.comm")]),
    "머리가 좀 아프네": ("daily", [("머리", "BOD.part")]),
    "2026-01-20 하루도 수고했어": ("daily", [("2026-01-20", "WRK.workplace")]),
    "2026-02-06 14:50에 산책 좀 했더니 기분이 좋아졌어": ("daily", [("2026-02-06", "HOB.outdoor"), ("14:50", "HOB.outdoor"), ("산책", "HOB.outdoor"), ("기분", "MND.emotion")]),
    "2026-02-23 14:40에 산책하고 왔어 기분 좋다": ("daily", [("2026-02-23", "HOB.outdoor"), ("14:40", "HOB.outdoor"), ("산책", "HOB.outdoor"), ("기분", "MND.emotion")]),
    "아 2026-04-14 좀 피곤하네": ("daily", [("2026-04-14", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "아 배고프다": ("daily", [("배고픔", "BOD.nutrition")]),
    "아 배불러 죽겠다": ("daily", [("배부름", "BOD.nutrition")]),
    "2026-02-22 회의 진짜 길었다": ("daily", [("2026-02-22", "WRK.workplace"), ("회의", "WRK.workplace")]),
    "점심 먹고 산책 좀 했어": ("daily", [("점심", "FOD.recipe"), ("산책", "HOB.outdoor")]),
    "아 머리 아파 두통약 먹어야겠다": ("daily", [("머리", "BOD.part"), ("두통약", "BOD.medical")]),
    "2026-01-28 18:30에 산책 다녀왔어 날씨 좋다": ("daily", [("2026-01-28", "HOB.outdoor"), ("18:30", "HOB.outdoor"), ("산책", "HOB.outdoor")]),
    "밥 먹었어": ("daily", [("밥", "FOD.recipe")]),
    "아 머리 아파": ("daily", [("머리", "BOD.part")]),
    "아 2026-02-13 좀 짜증나네": ("daily", [("2026-02-13", "MND.emotion"), ("짜증", "MND.emotion")]),
    "2026-01-22 날씨 좋아서 한강 갔다 왔어": ("daily", [("2026-01-22", "TRV.domestic"), ("한강", "TRV.domestic")]),
    "점심 뭐 먹지": ("daily", [("점심", "FOD.recipe")]),
    "아 공부하기 싫다": ("daily", [("공부", "EDU.academic")]),
    "퇴근하고 코딩 테스트 문제 좀 풀었어": ("daily", [("퇴근", "WRK.workplace"), ("코딩 테스트", "TEC.sw"), ("문제", "EDU.exam")]),
    "산책하다가 벚꽃 봤는데 예쁘더라": ("daily", [("산책", "HOB.outdoor"), ("벚꽃", "NAT.plant")]),
    "수고하셨습니다 좋은 하루 되세요": None,  # 인사
    "점심에 팀원들이랑 커피 마셨어": ("daily", [("점심", "FOD.recipe"), ("팀원", "PER.colleague"), ("커피", "FOD.drink")]),
    "아 2026-03-09 진짜 피곤하다": ("daily", [("2026-03-09", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "2026-04-13 야근했어 힘들다": ("daily", [("2026-04-13", "WRK.workplace"), ("야근", "WRK.workplace")]),
    "그래 됐어": None,  # 인사
    "알겠어 다음에 또 물어볼게": None,  # 인사
    "응 알았어 다음에 또 물어볼게": None,  # 인사
    "주말에 전시회 가볼까 생각 중이야": ("daily", [("주말", "CUL.show"), ("전시회", "CUL.show")]),
    "2026-01-08 09:00에 산책하고 왔어 날씨 좋더라": ("daily", [("2026-01-08", "HOB.outdoor"), ("09:00", "HOB.outdoor"), ("산책", "HOB.outdoor")]),
    "퇴근했다 수고했어": ("daily", [("퇴근", "WRK.workplace")]),
    "2026-04-06 너무 지치고 번아웃 온 것 같아": ("daily", [("2026-04-06", "MND.mental"), ("번아웃", "MND.mental")]),
    "아 힘들다 2026-01-19도 야근이네": ("daily", [("2026-01-19", "WRK.workplace"), ("야근", "WRK.workplace")]),
    "아 2026-03-15 너무 피곤하다": ("daily", [("2026-03-15", "BOD.sleep"), ("피곤", "BOD.sleep")]),
    "점심에 김치찌개 먹었는데 완전 맛있었어": ("daily", [("점심", "FOD.recipe"), ("김치찌개", "FOD.recipe")]),
    "산책하다가 날씨 좋아서 기분 좋네": ("daily", [("산책", "HOB.outdoor"), ("기분", "MND.emotion")]),
    "수고했어 2026-03-23 보자": ("daily", [("2026-03-23", "WRK.workplace")]),
    "2026-03-19 기분 좋다": ("daily", [("2026-03-19", "MND.emotion"), ("기분", "MND.emotion")]),
    "2026-01-28 점심 뭐 먹지": ("daily", [("2026-01-28", "FOD.recipe"), ("점심", "FOD.recipe")]),
    "2026-02-05 넷플릭스 뭐 볼까": ("daily", [("2026-02-05", "CUL.media"), ("넷플릭스", "CUL.media")]),
    "뭐 먹을까 고민이야": ("daily", [("고민", "MND.emotion")]),
    "야 수고했어": None,  # 인사
    "2026-01-02 날씨 좋아서 산책했어": ("daily", [("2026-01-02", "HOB.outdoor"), ("산책", "HOB.outdoor")]),
    "밖에 비 엄청 온다": ("daily", [("비", "NAT.weather")]),
    "점심에 만원짜리 김치찌개 먹었는데 비싸다": ("daily", [("점심", "FOD.recipe"), ("만원", "MON.spending"), ("김치찌개", "FOD.recipe")]),
    "2026-04-19 좀 우울하다": ("daily", [("2026-04-19", "MND.emotion"), ("우울", "MND.emotion")]),
    "점심 뭐 먹지 고민된다": ("daily", [("점심", "FOD.recipe"), ("고민", "MND.emotion")]),
    "2026-02-25 좀 우울하네": ("daily", [("2026-02-25", "MND.emotion"), ("우울", "MND.emotion")]),
    "아 배고프다 점심 뭐 먹지": ("daily", [("점심", "FOD.recipe")]),
    "점심에 회사 앞 국밥집 갔다왔어": ("daily", [("점심", "FOD.recipe"), ("회사", "WRK.workplace"), ("국밥집", "FOD.restaurant")]),
    "아버지 당뇨 없어지고 고혈압만 남았어": ("memory", [("아버지", "PER.family"), ("당뇨", "BOD.disease"), ("고혈압", "BOD.disease")]),
    "2026-04-06 회사에서 야근했어 진짜 힘들다": ("daily", [("2026-04-06", "WRK.workplace"), ("회사", "WRK.workplace"), ("야근", "WRK.workplace")]),
    "수고하셨습니다 좋은 밤 되세요": None,  # 인사
    "잘 잤어 기분 좋아": ("daily", [("기분", "MND.emotion")]),
    "머리 좀 아파": ("daily", [("머리", "BOD.part")]),
}


def build_assistant(retention: str, nodes: list[tuple[str, str]]) -> str:
    return json.dumps({
        "retention": retention,
        "nodes": [{"name": n, "category": c} for n, c in nodes],
    }, ensure_ascii=False)


def process(src: Path, dst: Path) -> dict:
    stats = {"input": 0, "kept": 0, "relabeled": 0, "dropped": 0, "unchanged_empty": 0, "unmatched": 0}
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            stats["input"] += 1
            rec = json.loads(line)
            asst_raw = rec["messages"][2]["content"]
            try:
                asst = json.loads(asst_raw)
            except json.JSONDecodeError:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats["kept"] += 1
                continue
            if asst.get("nodes"):
                # 비어있지 않은 레코드는 그대로
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats["kept"] += 1
                continue
            user = rec["messages"][1]["content"]
            if user in RELABEL:
                mapping = RELABEL[user]
                if mapping is None:
                    stats["dropped"] += 1
                    continue
                retention, nodes = mapping
                new_asst = build_assistant(retention, nodes)
                rec["messages"][2]["content"] = new_asst
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats["relabeled"] += 1
            else:
                # A 타입(상태변경) or B 타입(대화) — 기존 빈 nodes 유지
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stats["unchanged_empty"] += 1
    return stats


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    for name in ("train.jsonl", "valid.jsonl"):
        src = DATA_DIR / name
        tmp = DATA_DIR / f"{name}.relabeled"
        if not src.exists():
            continue
        stats = process(src, tmp)
        print(f"{name}: {stats}")
        if args.apply:
            tmp.replace(src)
            print(f"  -> applied")
        else:
            print(f"  -> tmp: {tmp}")


if __name__ == "__main__":
    main()
