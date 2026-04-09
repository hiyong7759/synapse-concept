"""4B 분해 모델 테스트. 문장 입력하면 노드+엣지 JSON 출력.

Usage:
    HF_HOME=/Volumes/macex/.cache/huggingface python3 finetune/test_decompose.py
"""

import os, sys, json, torch

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from system_prompt import SYSTEM_PROMPT

print("모델 로딩 중...", flush=True)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B")
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-4B", dtype=torch.float16)
model = PeftModel.from_pretrained(model, os.path.join(DIR, "models", "decompose-4b"))
model.eval()
print("준비 완료! 문장을 입력하세요. (종료: q)\n")

while True:
    text = input("입력> ").strip()
    if text.lower() == "q":
        break
    if not text:
        continue

    prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n<think>\n</think>\n\n"
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=512, temperature=0.1, do_sample=True)
    resp = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    try:
        data = json.loads(resp)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except:
        print(resp)
    print()
