#!/bin/bash
# 태스크별 개별 LoRA 파인튜닝
# 실행: bash archive/finetune/train_all_tasks.sh

VENV="/tmp/mlx-venv/bin/python"
MODEL="unsloth/gemma-4-E2B-it-UD-MLX-4bit"
DATA_BASE="archive/finetune/data/tasks"
ADAPTER_BASE="archive/finetune/models/tasks"

mkdir -p "$ADAPTER_BASE"

run_task() {
  local TASK=$1
  local ITERS_N=$2
  local ADAPTER_PATH="$ADAPTER_BASE/$TASK"
  local LOG_PATH="$ADAPTER_PATH/train.log"

  echo ""
  echo "=========================================="
  echo "[$TASK] 시작 — $ITERS_N iters"
  echo "=========================================="

  mkdir -p "$ADAPTER_PATH"

  $VENV -m mlx_lm lora \
    --model "$MODEL" \
    --train \
    --data "$DATA_BASE/$TASK" \
    --adapter-path "$ADAPTER_PATH" \
    --iters "$ITERS_N" \
    --batch-size 2 \
    --grad-checkpoint \
    --save-every 200 2>&1 | tee "$LOG_PATH"

  echo "[$TASK] 완료"
}

run_task retrieve-filter      670
run_task security-personal   1900
run_task save-pronoun         550
run_task security-org         540
run_task save-state-personal  400
run_task save-state-org       400
run_task security-context     550
run_task retrieve-expand      740
run_task save-subject-org     680
run_task retrieve-expand-org  540
run_task security-access      660
run_task routing              400

echo ""
echo "=========================================="
echo "전체 학습 완료"
echo "=========================================="
