# Caraxes Self-Correction Data Collector

This collector creates the kind of training examples where a model writes code, runs it in a sandbox, sees the error, fixes it, and saves the successful repair path.

It does not train the model by itself. It creates JSONL data that you can later mix into SFT training.

## Build The Sandbox

Docker must be installed and running.

```bash
docker build -t caraxes-code-sandbox:latest pc_train/self_correction
```

The runtime container is launched with no network, CPU/memory limits, dropped capabilities, no-new-privileges, read-only root filesystem, and a temporary writable `/tmp`.

## Run An Example

Point the script at your local OpenAI-compatible model server. For Caraxes this is usually the llama.cpp or MLX endpoint.

```bash
python pc_train/scripts/self_correct_collect.py \
  --language python \
  --prompt-file pc_train/self_correction/examples/two_sum_prompt.txt \
  --tests-file pc_train/self_correction/examples/test_two_sum.py \
  --api-base http://127.0.0.1:9901/v1 \
  --model local-model \
  --max-rounds 5 \
  --build-image
```

On Windows PowerShell:

```powershell
python pc_train\scripts\self_correct_collect.py `
  --language python `
  --prompt-file pc_train\self_correction\examples\two_sum_prompt.txt `
  --tests-file pc_train\self_correction\examples\test_two_sum.py `
  --api-base http://127.0.0.1:9901/v1 `
  --model local-model `
  --max-rounds 5 `
  --build-image
```

## Outputs

Successful runs append to:

- `pc_train/data/self_correction_traces.jsonl` - full attempts, errors, final files.
- `pc_train/data/self_correction_sft.jsonl` - chat-format messages ready to mix into SFT.

Each run also writes temporary workspaces under `pc_train/self_correction/runs/`, which is ignored by git.

## How To Use It Well

Start with small tasks that have reliable tests. The model should not see hidden tests; pass those with `--hidden-tests-file` if you want stronger examples.

Good prompts:

- Implement a function with edge cases.
- Fix a bug in a short file.
- Write a parser with unit tests.
- Implement an algorithm in Python, JavaScript, Java, C, or C++.

Bad prompts:

- Anything needing internet access.
- Anything requiring secrets, credentials, or real system access.
- Offensive security tasks that create malware, persistence, credential theft, evasion, or unauthorized exploitation.

For blue/purple team training, use prompts like log parsing, secure code review, IOC extraction, defensive detection rules, and vulnerable-code repair.
