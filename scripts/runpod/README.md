# RunPod 통합 학습

시냅스 + gabjil 어댑터를 FP16 베이스(`google/gemma-4-E2B-it`)에서 일괄 학습.
MLX 4bit 양자화 불일치 문제 해결.

## 왜 RunPod?

MLX 4bit에서 학습한 LoRA를 GGUF(Q4_K_M)에 적용하면 양자화 불일치로 출력 깨짐.
FP16에서 학습하면 어떤 양자화 GGUF에도 호환.

## 사용법

### 1. RunPod 환경 세팅

```bash
pip install unsloth peft transformers datasets accelerate bitsandbytes trl
git clone https://github.com/ggml-org/llama.cpp /tmp/llama.cpp  # GGUF 변환용
```

### 2. 데이터 업로드

```bash
# 시냅스 데이터
scp -r archive/finetune/data/ runpod:/workspace/synapse/data/

# gabjil 데이터
scp -r ../gabjil/finetune/datasets/ runpod:/workspace/synapse/gabjil-data/
```

### 3. 학습 실행

```bash
# 전체 (시냅스 18개 + gabjil 6개)
python train_all.py \
  --synapse-data /workspace/synapse/data \
  --gabjil-data /workspace/synapse/gabjil-data \
  --output /workspace/synapse/adapters

# 시냅스만
python train_all.py --synapse-only

# gabjil만
python train_all.py --gabjil-only

# 특정 태스크
python train_all.py --tasks extract save-pronoun gabjil-extract-a

# dry-run (설정 확인만)
python train_all.py --dry-run
```

### 4. GGUF 변환 (학습 후)

```bash
# 학습과 동시에 변환
python train_all.py --convert-gguf

# 또는 학습 후 별도 변환
python ../convert_mlx_to_gguf.py --all --base-model google/gemma-4-E2B-it
```

### 5. 결과 다운로드

```bash
# PEFT 어댑터
scp -r runpod:/workspace/synapse/adapters/ ./runpod_output/

# GGUF 어댑터
scp -r runpod:/workspace/synapse/gguf/ ./runpod_output/gguf/
```

## 태스크 목록

### 시냅스 (13 + 1)
| 태스크 | 데이터 | iters | 용도 |
|--------|--------|-------|------|
| extract | 1,798 | 2000 | 노드/엣지/카테고리 추출 |
| save-pronoun | 580 | 1500 | 대명사/날짜 치환 |
| retrieve-filter | 1,269 | 1500 | BFS 관련성 필터 |
| retrieve-expand | 363 | 1000 | 검색 키워드 확장 |
| retrieve-expand-org | 270 | 1000 | 조직 검색 확장 |
| routing | 265 | 800 | personal/org 분기 |
| save-state-personal | 438 | 1000 | 상태 변경 감지 |
| save-state-org | 366 | 1000 | 조직 상태 변경 |
| save-subject-org | 358 | 1000 | 조직 주어 특정 |
| security-access | 269 | 800 | 접근 제어 |
| security-context | 365 | 1000 | 맥락 보안 |
| security-org | 447 | 1000 | 조직 보안 |
| security-personal | 495 | 1000 | 개인 보안 |

### gabjil (1 + 5)
| 태스크 | 데이터 | iters | 용도 |
|--------|--------|-------|------|
| gabjil-extract-a | 255 | 800 | 통합 추출 |
| gabjil-extract-weakness | 255 | 800 | 약점 추출 |
| gabjil-extract-strength | 255 | 800 | 강점 추출 |
| gabjil-extract-trait | 255 | 800 | 특성 추출 |
| gabjil-extract-feeling | 255 | 800 | 감정 추출 |
| gabjil-extract-episode | 255 | 800 | 에피소드 추출 |

## 출력 구조

```
runpod_output/
├── adapters/
│   ├── extract/                 ← PEFT 어댑터 (HF 포맷)
│   │   ├── adapter_model.safetensors
│   │   └── adapter_config.json
│   ├── save-pronoun/
│   ├── retrieve-filter/
│   ├── gabjil-extract-a/
│   ├── gabjil-extract-weakness/
│   └── ...
├── gguf/                        ← GGUF LoRA (--convert-gguf 사용 시)
│   ├── extract.gguf
│   ├── gabjil-extract-a.gguf
│   └── ...
└── training_results.json
```

## 주의사항

- `load_in_4bit=False` — FP16 학습 필수. 4bit 학습하면 같은 양자화 불일치 문제 재발.
- `per_layer_input_gate`, `per_layer_projection` — Gemma 4 PLE 레이어. target_modules에 반드시 포함.
- 학습 후 나오는 어댑터는 HF PEFT 포맷 → convert_lora_to_gguf.py로 GGUF 변환 (중간 변환 불필요).
