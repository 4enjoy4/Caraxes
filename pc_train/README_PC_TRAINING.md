# Caraxes PC Training Kit

This folder is meant to travel with the project to the big training PC. It prepares data, model choices, and Axolotl QLoRA configs from a terminal panel so you can start training without rebuilding the plan by hand.

## Important Truths

The current Qwythos model is a 9B abliterated model. The Mac experiment depth-upscaled it to roughly 12B/13B-shaped weights, but that does not make it a true 13B model with native 13B knowledge. A 9B model also cannot be "retrained up to 70B" by fine-tuning. To train a real 70B-class model, start from a real 70B/72B base model and fine-tune it.

Use the old 9B/13B-upscaled model as an experiment. For the serious PC run, prefer:

- `Qwen/Qwen2.5-Coder-32B-Instruct` for best coding quality per hardware cost.
- `Qwen/Qwen2.5-72B-Instruct` if you insist on 70B-class scale.
- `meta-llama/Llama-3.3-70B-Instruct` only if you have accepted the gated license and want that family.

Because the starting 9B model is abliterated, the first training stage should make it less abliterated: restore helpful/harmless behavior, refusal boundaries, secure-code defaults, and defensive framing for red-team topics. Do not start with raw exploit or offensive cyber data.

## Folder Layout

- `datasets/catalog.json` - curated Hugging Face dataset list with downloads/likes snapshot.
- `models/model_catalog.json` - candidate base models.
- `scripts/refresh_hf_metadata.py` - refreshes Hugging Face download/like metadata.
- `scripts/build_sft_dataset.py` - converts selected datasets into chat-style JSONL.
- `scripts/make_axolotl_config.py` - writes an Axolotl QLoRA config.
- `panel.py` - terminal panel to select datasets/model and run the scripts.
- `data/`, `cache/`, `outputs/`, `adapters/` - generated locally and ignored by git.

## Setup On The Training PC

Use Linux if possible. Native Windows can work for some pieces, but multi-GPU training is much smoother under Linux or WSL2 with CUDA.

```powershell
cd C:\path\to\Caraxes
python -m venv .venv-train
.venv-train\Scripts\activate
python -m pip install -U pip
pip install -r pc_train\requirements-pc-train.txt
huggingface-cli login
python pc_train\panel.py
```

Linux/macOS equivalent:

```bash
cd /path/to/Caraxes
python3 -m venv .venv-train
source .venv-train/bin/activate
python -m pip install -U pip
pip install -r pc_train/requirements-pc-train.txt
huggingface-cli login
python pc_train/panel.py
```

## Recommended Training Order

1. Smoke test with small data.

Use defaults in the panel and cap each dataset at 500-1000 rows. Generate a config for `qwen2_5_coder_32b` first, sequence length `4096` or `8192`, then train for a tiny run. This proves CUDA, downloads, tokenization, packing, and checkpoint saving.

2. De-abliteration repair.

Keep `pku_saferlhf_10k`, `anthropic_hh_rlhf`, `securecode`, and `securecode_web` selected. This stage teaches the model to be useful without being reckless, and to answer dual-use cybersecurity questions with authorization checks, lab framing, detection, mitigation, and safe alternatives.

3. Coding reasoning SFT.

Add `opencodeinstruct`, `opencodereasoning`, `magicoder_oss`, and `magicoder_evol`. Start with 50K-200K rows per large dataset. Increase only after evaluation improves.

4. Long-context specialist pass.

Use longer sequence lengths only after the normal run is stable. Move from `8192` to `16384`, then `32768` if memory and speed are acceptable. This helps with large documentation and logs, but the real solution for 500-page PDFs or 2M-line logs is still chunking plus retrieval in the app, not stuffing everything into model weights.

5. Optional cyber/purple-team pass.

Use `trendyol_cybersecurity`, `cybernative_code_security_dpo`, or other cyber datasets only after manual inspection. Keep it defensive, authorized, and lab-scoped. The goal is red-team literacy for blue/purple work, not a model that blindly produces operational abuse.

## Manual Commands

Refresh dataset popularity metadata:

```bash
python pc_train/scripts/refresh_hf_metadata.py
```

Build a first training file:

```bash
python pc_train/scripts/build_sft_dataset.py \
  --datasets pku_saferlhf_10k,anthropic_hh_rlhf,securecode,securecode_web,magicoder_oss,magicoder_evol,opencodereasoning \
  --max-per-dataset 50000 \
  --streaming \
  --out pc_train/data/merged_code_sft.jsonl
```

Generate an Axolotl config:

```bash
python pc_train/scripts/make_axolotl_config.py \
  --model qwen2_5_coder_32b \
  --sequence-len 8192 \
  --dataset pc_train/data/merged_code_sft.jsonl \
  --out pc_train/configs/axolotl_qlora.yaml
```

Train:

```bash
accelerate launch -m axolotl.cli.train pc_train/configs/axolotl_qlora.yaml
```

## Dataset Policy

Prefer high-signal instruction/reasoning data over giant raw dumps. Raw code corpora such as The Stack are useful for continued pretraining experiments, not as normal chat SFT. Blindly dumping the internet into weights usually makes the model noisier, not smarter.

The defaults are intentionally conservative:

- Safety repair: `PKU-Alignment/PKU-SafeRLHF-10K`, `Anthropic/hh-rlhf`.
- Secure coding: `scthornton/securecode`, `scthornton/securecode-web`.
- Coding reasoning: NVIDIA OpenCode and Magicoder datasets.

Use non-default cyber datasets only after sampling rows and checking that the answers match your blue/purple-team goal.

## Evaluation Before Replacing The Model

Do not replace the production model just because a training run completed. Compare base versus fine-tuned model on:

- Python, Java, JavaScript, C/C++, assembly, and shell coding prompts.
- Secure code review: SQL injection, auth bugs, deserialization, path traversal, unsafe crypto.
- Defensive cyber reasoning: logs, incident timeline, suspicious process trees, MITRE ATT&CK mapping.
- Long-file behavior: chunked project review, 500-page PDF summary, 2M-line log triage.
- Refusal behavior: requests for unauthorized intrusion, malware deployment, credential theft, persistence, evasion.

Keep the run only if it improves useful coding and defensive security while becoming less reckless than the abliterated base.

## Notes For The Future 70B Run

With two large RTX workstation GPUs, QLoRA on a 70B/72B model is plausible. Full fine-tuning is still much heavier and usually not worth it unless you have a distributed training stack and a carefully deduplicated corpus.

Start with QLoRA. If the result is good, merge the adapter for serving. If it is not good, fix the dataset mix before increasing model size.
