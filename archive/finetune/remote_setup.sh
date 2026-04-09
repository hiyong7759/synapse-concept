#!/bin/bash
# Synapse fine-tuning 환경 세팅 — WSL2 RTX 3080
# 사용: scp 후 WSL에서 bash remote_setup.sh

set -e

echo "=== Synapse Fine-tuning 환경 세팅 ==="

# mlagents-env (Python 3.10) 과 별도 venv 생성
# Unsloth는 Python 3.10+ 필요
VENV_DIR=~/synapse-ft-env

if [ -d "$VENV_DIR" ]; then
    echo "venv already exists: $VENV_DIR"
else
    echo "Creating venv (Python 3.10)..."
    python3.10 -m venv $VENV_DIR
fi

source $VENV_DIR/bin/activate

echo "Python: $(python --version)"
echo "pip: $(pip --version)"

# PyTorch (CUDA 12.1 — 기존 환경과 동일)
echo "Installing PyTorch..."
pip install --upgrade pip
pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cu121

# Unsloth (4bit quantization + LoRA, VRAM 절약 핵심)
echo "Installing Unsloth..."
pip install "unsloth[cu121-torch241] @ git+https://github.com/unslothai/unsloth.git"

# 추가 의존성
echo "Installing dependencies..."
pip install transformers datasets peft bitsandbytes accelerate trl sentencepiece protobuf

echo ""
echo "=== 설치 완료 ==="
echo "venv: $VENV_DIR"
echo "활성화: source $VENV_DIR/bin/activate"
echo ""
echo "VRAM 예상 사용량 (RTX 3080 10GB):"
echo "  Qwen 2.5 7B 4bit: ~5GB + LoRA ~1.5GB = ~6.5GB OK"
echo "  Llama 3.1 8B 4bit: ~6GB + LoRA ~1.5GB = ~7.5GB OK"
