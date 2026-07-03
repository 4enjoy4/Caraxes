# Training Caraxes On Mac Studio

Yes, a Mac Studio with 256 GB unified memory is suitable for local LoRA/QLoRA experiments. Use the Apple Silicon GPU through MLX rather than plain CPU training.

## What Is Realistic

- Good target: LoRA or QLoRA fine-tuning.
- Risky target: full fine-tuning all weights. It may fit with 256 GB on some setups, but it is slow, fragile, and unnecessary for the first Caraxes adapter.
- Current Caraxes model note: `huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated` uses `model_type: qwen3_5`. Test latest `mlx-lm` support before committing a long run.

## Prepare Data

On the project folder:

```bash
python3 scripts/prepare_mlx_lora_data.py
```

This creates:

```text
training/mlx_lora_data/train.jsonl
training/mlx_lora_data/valid.jsonl
training/mlx_lora_data/test.jsonl
```

## Install MLX-LM

```bash
python3 -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install -U pip
python -m pip install "mlx-lm[train]"
```

## Quick Compatibility Test

```bash
python - <<'PY'
from mlx_lm import load
model, tokenizer = load("huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated")
print("loaded")
PY
```

If this fails because `qwen3_5` is unsupported, train a supported Qwen coder model first, or use PyTorch/MPS on the Hugging Face model instead of MLX.

## Start A Conservative LoRA Run

```bash
mlx_lm.lora \
  --model huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated \
  --train \
  --data training/mlx_lora_data \
  --adapter-path training/adapters/caraxes-qwythos-mlx-lora \
  --iters 300 \
  --batch-size 1 \
  --grad-accumulation-steps 8 \
  --num-layers 16 \
  --mask-prompt \
  --grad-checkpoint
```

After a smoke run works, raise `--iters` to `1000` or more.

## Test The Adapter

```bash
mlx_lm.generate \
  --model huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated \
  --adapter-path training/adapters/caraxes-qwythos-mlx-lora \
  --prompt "Create a blue-team triage plan for suspicious PowerShell encoded command activity."
```

## Important

The adapter is a permanent file, but it does not change the original GGUF. To use the trained behavior in Caraxes, we either need to serve the MLX model on the Mac, or export/convert a compatible deployable model and point Caraxes at it.
