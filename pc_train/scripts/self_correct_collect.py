from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "caraxes-code-sandbox:latest"
DEFAULT_API_BASE = os.environ.get("CARAXES_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "http://127.0.0.1:9901/v1"
DEFAULT_MODEL = os.environ.get("CARAXES_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "local-model"


LANGUAGE_DEFAULTS = {
    "python": {
        "main": "solution.py",
        "tests": "tests/test_solution.py",
        "hidden_tests": "hidden_tests/test_hidden.py",
        "test_command": "python -m py_compile $(find . -name '*.py') && python -m pytest -q -p no:cacheprovider tests",
        "test_command_hidden": "python -m py_compile $(find . -name '*.py') && python -m pytest -q -p no:cacheprovider tests hidden_tests",
        "hidden_only_command": "python -m py_compile $(find . -name '*.py') && python -m pytest -q -p no:cacheprovider hidden_tests",
        "no_tests_command": "python -m py_compile $(find . -name '*.py') && python solution.py",
    },
    "javascript": {
        "main": "solution.js",
        "tests": "test.js",
        "hidden_tests": "hidden_test.js",
        "test_command": "node --check solution.js && node test.js",
        "test_command_hidden": "node --check solution.js && node test.js && node hidden_test.js",
        "hidden_only_command": "node --check solution.js && node hidden_test.js",
        "no_tests_command": "node --check solution.js",
    },
    "java": {
        "main": "Solution.java",
        "tests": "TestSolution.java",
        "hidden_tests": "HiddenTestSolution.java",
        "test_command": "javac $(find . -name '*.java') && java TestSolution",
        "test_command_hidden": "javac $(find . -name '*.java') && java TestSolution && java HiddenTestSolution",
        "hidden_only_command": "javac $(find . -name '*.java') && java HiddenTestSolution",
        "no_tests_command": "javac $(find . -name '*.java')",
    },
    "c": {
        "main": "solution.c",
        "tests": "test_solution.c",
        "hidden_tests": "hidden_test_solution.c",
        "test_command": "gcc -Wall -Wextra -std=c17 -O0 $(find . -name '*.c') -o /tmp/solution_test && /tmp/solution_test",
        "test_command_hidden": "gcc -Wall -Wextra -std=c17 -O0 $(find . -name '*.c') -o /tmp/solution_test && /tmp/solution_test",
        "hidden_only_command": "gcc -Wall -Wextra -std=c17 -O0 $(find . -name '*.c') -o /tmp/solution_test && /tmp/solution_test",
        "no_tests_command": "gcc -Wall -Wextra -std=c17 -O0 solution.c -o /tmp/solution && /tmp/solution",
    },
    "cpp": {
        "main": "solution.cpp",
        "tests": "test_solution.cpp",
        "hidden_tests": "hidden_test_solution.cpp",
        "test_command": "g++ -Wall -Wextra -std=c++20 -O0 $(find . -name '*.cpp') -o /tmp/solution_test && /tmp/solution_test",
        "test_command_hidden": "g++ -Wall -Wextra -std=c++20 -O0 $(find . -name '*.cpp') -o /tmp/solution_test && /tmp/solution_test",
        "hidden_only_command": "g++ -Wall -Wextra -std=c++20 -O0 $(find . -name '*.cpp') -o /tmp/solution_test && /tmp/solution_test",
        "no_tests_command": "g++ -Wall -Wextra -std=c++20 -O0 solution.cpp -o /tmp/solution && /tmp/solution",
    },
    "bash": {
        "main": "solution.sh",
        "tests": "test_solution.sh",
        "hidden_tests": "hidden_test_solution.sh",
        "test_command": "bash -n solution.sh && bash test_solution.sh",
        "test_command_hidden": "bash -n solution.sh && bash test_solution.sh && bash hidden_test_solution.sh",
        "hidden_only_command": "bash -n solution.sh && bash hidden_test_solution.sh",
        "no_tests_command": "bash -n solution.sh",
    },
}


@dataclass
class SandboxResult:
    ok: bool
    exit_code: int
    command: str
    stdout: str
    stderr: str
    timed_out: bool = False


def clip(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[clipped {len(text) - limit} chars]"


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    raise SystemExit("Provide --prompt or --prompt-file")


def post_chat(api_base: str, model: str, messages: list[dict[str, str]], temperature: float, max_tokens: int, timeout: int) -> str:
    url = api_base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"model server HTTP {exc.code}: {detail}") from exc
    return payload["choices"][0]["message"]["content"]


def strip_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_model_files(raw: str, language: str) -> list[dict[str, str]]:
    defaults = LANGUAGE_DEFAULTS[language]
    cleaned = strip_fence(raw)
    data: Any | None = None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = None

    if isinstance(data, dict) and isinstance(data.get("files"), list):
        files = []
        for item in data["files"]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or defaults["main"])
            content = str(item.get("content") or "")
            if content.strip():
                files.append({"path": path, "content": content})
        if files:
            return files

    fence_match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\s*(.*?)```", raw, flags=re.DOTALL)
    if fence_match:
        return [{"path": defaults["main"], "content": fence_match.group(1).strip() + "\n"}]

    return [{"path": defaults["main"], "content": raw.strip() + "\n"}]


def safe_relative_path(path_text: str) -> Path:
    normalized = path_text.replace("\\", "/").strip().lstrip("/")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts or normalized.startswith(".git/") or not normalized:
        raise ValueError(f"unsafe generated path: {path_text}")
    return path


def write_text_under(root: Path, relative_path: str, content: str) -> Path:
    path = safe_relative_path(relative_path)
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return target


def write_workspace(workspace: Path, files: list[dict[str, str]], args: argparse.Namespace) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for item in files:
        content = item["content"]
        if len(content) > args.max_file_chars:
            raise ValueError(f"generated file too large: {item['path']}")
        write_text_under(workspace, item["path"], content)

    defaults = LANGUAGE_DEFAULTS[args.language]
    if args.tests_file:
        tests_path = args.tests_path or defaults["tests"]
        write_text_under(workspace, tests_path, Path(args.tests_file).read_text(encoding="utf-8"))
    if args.hidden_tests_file:
        hidden_path = args.hidden_tests_path or defaults["hidden_tests"]
        write_text_under(workspace, hidden_path, Path(args.hidden_tests_file).read_text(encoding="utf-8"))


def build_image(image: str) -> None:
    dockerfile_dir = ROOT / "self_correction"
    subprocess.run(["docker", "build", "-t", image, str(dockerfile_dir)], check=True)


def default_command(args: argparse.Namespace) -> str:
    defaults = LANGUAGE_DEFAULTS[args.language]
    if args.test_command:
        return args.test_command
    if args.tests_file and args.hidden_tests_file:
        return defaults["test_command_hidden"]
    if args.hidden_tests_file:
        return defaults["hidden_only_command"]
    if args.tests_file:
        return defaults["test_command"]
    return defaults["no_tests_command"]


def run_sandbox(workspace: Path, command: str, args: argparse.Namespace) -> SandboxResult:
    mount = f"type=bind,source={workspace.resolve()},target=/workspace"
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        str(args.cpus),
        "--memory",
        args.memory,
        "--pids-limit",
        str(args.pids_limit),
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,size=512m",
        "--tmpfs",
        "/home/sandbox:rw,nosuid,size=64m",
        "--workdir",
        "/workspace",
        "--mount",
        mount,
        args.image,
        "bash",
        "-lc",
        command,
    ]
    try:
        completed = subprocess.run(
            docker_cmd,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
        return SandboxResult(
            ok=completed.returncode == 0,
            exit_code=completed.returncode,
            command=command,
            stdout=clip(completed.stdout),
            stderr=clip(completed.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            ok=False,
            exit_code=124,
            command=command,
            stdout=clip(exc.stdout or ""),
            stderr=clip((exc.stderr or "") + f"\nTimed out after {args.timeout}s"),
            timed_out=True,
        )


def tests_preview(args: argparse.Namespace) -> str:
    if not args.tests_file:
        return "No visible tests were provided."
    text = Path(args.tests_file).read_text(encoding="utf-8")
    return clip(text, 6000)


def system_message(language: str) -> str:
    default_file = LANGUAGE_DEFAULTS[language]["main"]
    return (
        "You are writing code for a local isolated Docker sandbox. "
        "Return strict JSON only, with this shape: "
        '{"files":[{"path":"' + default_file + '","content":"..."}],"notes":"short note"}. '
        "Do not use markdown fences. Do not access the network. Do not read or write outside the current directory. "
        "Do not include destructive commands, persistence, credential handling, or infinite loops. "
        "Prefer simple standard-library code unless the user explicitly provides dependencies."
    )


def initial_user_message(prompt: str, args: argparse.Namespace) -> str:
    defaults = LANGUAGE_DEFAULTS[args.language]
    visible_tests = tests_preview(args)
    hidden_note = "Hidden tests are present and will be run, but their contents are not shown." if args.hidden_tests_file else "No hidden tests are present."
    return (
        f"Language: {args.language}\n"
        f"Default solution file: {defaults['main']}\n"
        f"Task:\n{prompt.strip()}\n\n"
        f"Visible tests:\n{visible_tests}\n\n"
        f"{hidden_note}\n\n"
        "Write the complete solution files now. Return JSON only."
    )


def failure_message(result: SandboxResult) -> str:
    return (
        "The sandbox run failed. Fix the code and return the full replacement files as strict JSON only.\n\n"
        f"Command:\n{result.command}\n\n"
        f"Exit code: {result.exit_code}\n"
        f"Timed out: {result.timed_out}\n\n"
        f"STDOUT:\n{result.stdout}\n\n"
        f"STDERR:\n{result.stderr}\n"
    )


def save_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect self-correction coding traces with Docker execution feedback.")
    parser.add_argument("--language", choices=sorted(LANGUAGE_DEFAULTS), default="python")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--tests-file")
    parser.add_argument("--tests-path")
    parser.add_argument("--hidden-tests-file")
    parser.add_argument("--hidden-tests-path")
    parser.add_argument("--test-command", help="User-provided command to run inside /workspace instead of the language default")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--model-timeout", type=int, default=300)
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--build-image", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--cpus", default="2")
    parser.add_argument("--memory", default="2g")
    parser.add_argument("--pids-limit", type=int, default=256)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "self_correction" / "runs")
    parser.add_argument("--trace-out", type=Path, default=ROOT / "data" / "self_correction_traces.jsonl")
    parser.add_argument("--sft-out", type=Path, default=ROOT / "data" / "self_correction_sft.jsonl")
    parser.add_argument("--save-failures", action="store_true")
    parser.add_argument("--max-file-chars", type=int, default=300_000)
    args = parser.parse_args()

    prompt = read_prompt(args)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    run_dir = args.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.build_image:
        build_image(args.image)

    messages = [
        {"role": "system", "content": system_message(args.language)},
        {"role": "user", "content": initial_user_message(prompt, args)},
    ]
    attempts: list[dict[str, Any]] = []
    final_files: list[dict[str, str]] = []
    success = False
    command = default_command(args)

    for round_index in range(1, args.max_rounds + 1):
        print(f"\n[round {round_index}/{args.max_rounds}] asking model...")
        assistant_raw = post_chat(args.api_base, args.model, messages, args.temperature, args.max_tokens, args.model_timeout)
        messages.append({"role": "assistant", "content": assistant_raw})
        files = parse_model_files(assistant_raw, args.language)

        workspace = run_dir / f"round_{round_index}" / "workspace"
        write_workspace(workspace, files, args)
        print(f"[round {round_index}] running sandbox command: {command}")
        result = run_sandbox(workspace, command, args)
        print(f"[round {round_index}] ok={result.ok} exit={result.exit_code}")
        if result.stdout:
            print(clip(result.stdout, 1500))
        if result.stderr:
            print(clip(result.stderr, 1500))

        attempts.append(
            {
                "round": round_index,
                "assistant_raw": assistant_raw,
                "files": files,
                "workspace": str(workspace),
                "run": result.__dict__,
            }
        )

        if result.ok:
            success = True
            final_files = files
            break

        messages.append({"role": "user", "content": failure_message(result)})

    trace = {
        "id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": args.model,
        "api_base": args.api_base,
        "language": args.language,
        "prompt": prompt,
        "tests_file": args.tests_file,
        "hidden_tests_file": args.hidden_tests_file,
        "command": command,
        "success": success,
        "attempts": attempts,
        "final_files": final_files,
        "messages": messages,
    }

    if success or args.save_failures:
        save_jsonl(args.trace_out, trace)
        sft_row = {
            "messages": messages,
            "source": "self_correction",
            "success": success,
            "trace_id": run_id,
            "language": args.language,
        }
        save_jsonl(args.sft_out, sft_row)
        print(f"\nSaved trace: {args.trace_out}")
        print(f"Saved SFT row: {args.sft_out}")
    else:
        print("\nNo successful solution found; not saved. Use --save-failures to keep failed traces.")

    if not success:
        sys.exit(2)


if __name__ == "__main__":
    main()
