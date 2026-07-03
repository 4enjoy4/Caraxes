# Caraxes Local AI

Caraxes is a local ChatGPT-style web UI for a GGUF model. It stores chat history, accepts file uploads, extracts readable context from code/text files, PDFs, spreadsheets, CSVs, and images, then sends that context to the local model.

Default model:

`huihui-ai/Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-GGUF`

Default quantization:

`Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-Q4_K.gguf`

## Setup

From this folder:

```powershell
winget install llama.cpp
scripts\download_model.ps1
scripts\start_all.ps1
```

The app is now reachable at:

```text
http://localhost:9898
```

Other devices on the same network can use:

```text
http://YOUR-PC-IP:9898
```

To stop both the UI and model backend:

```powershell
scripts\stop.ps1
```

## Notes

- First answer can be slow because the GGUF loads into memory on demand.
- `scripts\start_all.ps1` runs the model through an OpenAI-compatible llama.cpp backend on `127.0.0.1:9901` and keeps this UI on port `9898`.
- `scripts\start.ps1` can run the UI alone. It also tries the embedded `llama-cpp-python` path, but the official `llama.cpp` server route is the safer Windows default.
- The model server starts with reasoning disabled by default (`CARAXES_REASONING=off`, `CARAXES_REASONING_BUDGET=0`) so normal answers do not spend the whole token budget on hidden thinking.
- The default context is `8192`. You can raise it with `CARAXES_N_CTX`, but long context needs much more RAM.
- Image uploads are read through metadata and OCR. OCR needs the Tesseract application installed on Windows.
- Large extracted files are split into numbered chunks. Each prompt includes the most relevant parts that fit the context window, and you can ask for specific parts such as `chunks 4-7`.
- Very large text/log files are streamed into chunks instead of being loaded into memory all at once. Caraxes stores line counts, first/last lines, and common log signal counts.
- File chunks are indexed with SQLite FTS when available, so prompts can retrieve relevant parts from huge logs and docs.
- Caraxes keeps rolling chat memory and explicit user memory notes. Say `remember: ...` in chat to save a long-term note.
- Web research is enabled by default with `CARAXES_ENABLE_WEB=1`. It can fetch public URLs and run a free best-effort web search when you ask for current docs, downloads, installs, or internet research.
- GitHub repository URLs are pulled in read-only: Caraxes fetches repo metadata, README, file tree, and selected relevant source/config/docs files for analysis. It does not clone, install, execute, or modify internet code.
- To try a larger quant, run `scripts\download_model.ps1 --filename Huihui-Qwythos-9B-Claude-Mythos-5-1M-abliterated-Q6_K.gguf` and set `CARAXES_MODEL_PATH` to that file before starting.
- Training/fine-tuning uses LoRA/QLoRA against the non-GGUF model repo. Export local chat examples with `.\.venv\Scripts\python.exe scripts\export_training_data.py`, then build the larger coding + defensive cyber corpus with `.\.venv\Scripts\python.exe scripts\build_hf_training_corpus.py`. Follow `training\README.md` for the free Colab/Kaggle route.
- Laptop-only improvement instructions for coding, blue team, purple team, and red-team-aware defensive workflows are in `README_LAPTOP_IMPROVEMENTS.md`.
