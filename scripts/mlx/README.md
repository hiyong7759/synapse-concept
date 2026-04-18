# MLX 학습/증강 스크립트

## 학습

```bash
python scripts/mlx/train_all.py                         # 전체 14개 태스크
python scripts/mlx/train_all.py --only save-pronoun     # 하나만
python scripts/mlx/train_all.py --iters 100             # 스모크
```

태스크별 전용 config 사용 시 직접 mlx_lm 호출:
```bash
python -m mlx_lm lora -c configs/mlx/save-pronoun.yaml
```

## 데이터 증강 (준비만, 실행은 수동)

### retrieve-expand — 질문 유형별 균등 증강
```bash
python scripts/mlx/augment_retrieve_expand.py classify          # 시드를 7유형으로 분류
python scripts/mlx/augment_retrieve_expand.py generate --per-type 100
# 생성물: data/finetune/aug/retrieve-expand/aug_raw.jsonl
# 수동 검증 → aug_verified.jsonl
python scripts/mlx/augment_retrieve_expand.py merge
```

### security-access — (권한 × result) 교차 보강
```bash
python scripts/mlx/augment_security_access.py audit                   # 현재 교차표
python scripts/mlx/augment_security_access.py generate --target-per-cell 15
# 생성물: data/finetune/aug/security-access/aug_raw.jsonl
# 수동 검증 → aug_verified.jsonl
python scripts/mlx/augment_security_access.py merge
```

## 증강 원칙

- **시드 유형 분류 우선**: 단순 바리에이션은 표면만 달라져 구조적 다양성 없음
- **유형/조합별 균등**: 부족한 셀을 명시적으로 채움
- **수동 검증 필수**: LLM 생성 raw → 사람 검토 → verified → merge
- **입력 다양화 시 출력 일관성 확인**: 출력 포맷·품질 흔들리면 역효과

## 실험 기록 원칙

하이퍼파라미터는 **한 번에 하나씩** 변경. 각 실험에서 val loss와 바꾼 변수 짝지어 기록.

## 디렉토리

```
configs/mlx/_base.yaml            # 전 태스크 공용 기본값
configs/mlx/<task>.yaml           # 태스크별 오버라이드 (필요 시)
runpod_output/mlx_adapters/<task>/   # 학습된 어댑터
runpod_output/mlx_logs/<task>.log    # 학습 로그
data/finetune/aug/<task>/         # 증강 임시 파일 (raw → verified)
```
