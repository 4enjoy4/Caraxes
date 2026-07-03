"""Caraxes Coder: workspace file APIs and the editor AI endpoint.

The coder page works on one "workspace" (a folder the user opened, like VS Code).
Every file operation resolves against that root and refuses paths that escape it,
so the browser UI can only touch the folder the user explicitly opened.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import accounts

router = APIRouter(prefix="/api/coder")

_runtime: Any = None
_workspace_file: Path | None = None
_default_suggestions: list[Path] = []
_memory_provider: Any = None
_external_context_provider: Any = None
_user_spaces_dir: Path | None = None

MAX_UPLOAD_FILES = 1000

# Each browser session gets its own workspace. Requests from the host machine
# (localhost) are the "owner" and can open anything; other devices on the LAN
# may only open folders the owner explicitly shared.
_session_ctx: ContextVar[dict[str, Any] | None] = ContextVar("caraxes_coder_session", default=None)
OWNER_HOSTS = {"127.0.0.1", "::1", "localhost"}
MAX_REMOTE_SESSIONS = 40

MAX_EDITOR_FILE_BYTES = int(os.environ.get("CARAXES_EDITOR_MAX_BYTES", str(8 * 1024 * 1024)))
RUN_TIMEOUT_SECONDS = int(os.environ.get("CARAXES_RUN_TIMEOUT_SECONDS", "120"))
ALLOW_REMOTE_RUN = os.environ.get("CARAXES_REMOTE_SHELL", "0").lower() in {"1", "true", "yes", "on"}
MAX_RUN_OUTPUT_CHARS = 20_000
MAX_PROMPT_FILE_CHARS = 24_000
MAX_PROMPT_HISTORY_MESSAGES = 12
MAX_PROMPT_HISTORY_CHARS = 6_000
MAX_RECENT_WORKSPACES = 6
MAX_EXTERNAL_CONTEXT_CHARS = 5_000

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg", ".avif"}

CODER_SYSTEM_PROMPT = """You are Caraxes Coder, a local AI pair programmer living inside a code editor on the user's machine.
The user can share the currently open file, and sometimes a selected region of it, as context.
A partial listing of the workspace files may also be provided; use it to pick correct paths.
Selected related workspace files may be provided. Use them as supporting evidence, but do not pretend you saw files not included.
Be direct and practical. Prefer small, concrete changes over rewrites unless asked.
When you show code, always use fenced code blocks with a language tag.
For code review, lead with severity-ordered findings and concrete paths. For security review, use defensive CWE/OWASP/MITRE-style reasoning without exploit code or harmful operational steps.

You can create or rewrite ANY file in the workspace, not only the open one.
If the user asks to create, write, save, or name a file, return a FILE block for that file immediately; never ask the user to create or open a placeholder file first.
If the user gives an exact filename or relative path, use that exact workspace-relative path unless it is unsafe.
For every file you want written to disk, output this exact pattern:
### FILE: relative/path/from/workspace/root.ext
```language
<the complete file content>
```
Use one "### FILE:" header per file, each followed by exactly one fenced block with the FULL file content.
Never split one file across several FILE blocks or "parts" - a file is always exactly one complete block.
If the requested content is too long to finish in one reply, write a complete but shorter version of the file
and say what you left out, instead of stopping mid-file.
Use it for new files too (for example a new markdown document). Never use absolute paths.
If you are only explaining or showing a snippet that should NOT be saved, use a plain fenced block without a FILE header.
Never invent files or APIs you have not seen; say what you would need to look at instead."""

RUN_PROTOCOL = """
You may also run Windows commands inside the workspace folder when the task needs it
(installing dependencies, running tests or scripts, listing detailed file info).
To run a command, output this exact pattern:
### RUN
```powershell
<one PowerShell command or a short script>
```
Each RUN block is executed in the workspace folder and its output is shown to the user and to you.
Use RUN blocks sparingly, one logical step per block. Never run destructive or system-wide commands
(deleting outside the workspace, changing system settings, downloading and executing programs)
unless the user explicitly asked for exactly that."""

EDIT_MODE_INSTRUCTION = (
    "Apply the requested change. For EVERY file you create or modify, output a '### FILE: <workspace-relative path>' "
    "header followed by exactly one fenced code block containing the complete file content. "
    "If the change only affects the open file, use the open file's path. "
    "If no open file is provided and the request asks to create/write/save a file, choose the filename from the request "
    "or a sensible workspace-relative path, then output a complete FILE block for that new file. "
    "Do not tell the user to create a .txt, .md, .js, .py, or other placeholder first. "
    "Never split a file into multiple FILE blocks; each file appears exactly once, complete. "
    "If the content would be too long, write a complete shorter version rather than cutting off mid-file. "
    "Do not omit unchanged parts and do not add commentary after the last code block."
)

LIST_IGNORED_DIR_NAMES = {"node_modules", "__pycache__", "dist", "build"}
MAX_LISTED_FILES = 200
MAX_LIST_DEPTH = 3
MAX_LIST_CHARS = 3_000
MAX_RELATED_FILES = 5
MAX_RELATED_FILE_CHARS = 4_500
MAX_RELATED_SCAN_FILES = 900
REQUESTED_FILE_PATH_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_. -]+(?:[/\\][A-Za-z0-9_. -]+)*\.[A-Za-z0-9]{1,12})\b"
)
REQUESTED_QUOTED_TYPED_FILE_RE = re.compile(
    r"\b(?P<kind>txt|text|md|markdown|js|javascript|py|python|java|json|html|css|csv|sql|yaml|yml|ts|typescript|sh|bash|ps1|bat|cmd|c|cpp|cxx|h|hpp|rs|rust|go|php|rb|ruby)\s+file\s+"
    r"(?:named|called|name it|save(?: it)? as|as)\s+(?P<quote>['\"`])(?P<name>[^'\"`\r\n]+)(?P=quote)",
    re.IGNORECASE,
)
REQUESTED_UNQUOTED_TYPED_FILE_RE = re.compile(
    r"\b(?P<kind>txt|text|md|markdown|js|javascript|py|python|java|json|html|css|csv|sql|yaml|yml|ts|typescript|sh|bash|ps1|bat|cmd|c|cpp|cxx|h|hpp|rs|rust|go|php|rb|ruby)\s+file\s+"
    r"(?:named|called|name it|save(?: it)? as|as)\s+(?P<name>[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
REQUESTED_FILE_LABEL_RE = re.compile(
    r"\b(?:named|called|name it|save(?: it)? as|write to|write into|create as)\s+['\"`]?([^'\"`\r\n]+)",
    re.IGNORECASE,
)
FILE_BLOCK_RE = re.compile(
    r"#{2,4}\s*FILE:\s*([^\n`]+?)\s*\n+```[a-zA-Z0-9_+\-.#]*\n([\s\S]*?)```",
    re.MULTILINE,
)
FILE_KIND_EXTENSIONS = {
    "txt": ".txt",
    "text": ".txt",
    "md": ".md",
    "markdown": ".md",
    "js": ".js",
    "javascript": ".js",
    "py": ".py",
    "python": ".py",
    "java": ".java",
    "json": ".json",
    "html": ".html",
    "css": ".css",
    "csv": ".csv",
    "sql": ".sql",
    "yaml": ".yaml",
    "yml": ".yml",
    "ts": ".ts",
    "typescript": ".ts",
    "sh": ".sh",
    "bash": ".sh",
    "ps1": ".ps1",
    "bat": ".bat",
    "cmd": ".cmd",
    "c": ".c",
    "cpp": ".cpp",
    "cxx": ".cpp",
    "h": ".h",
    "hpp": ".hpp",
    "rs": ".rs",
    "rust": ".rs",
    "go": ".go",
    "php": ".php",
    "rb": ".rb",
    "ruby": ".rb",
}
RELATED_SUFFIXES = {
    ".asm",
    ".bat",
    ".c",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".s",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IMPORTANT_RELATED_NAMES = {
    "readme.md",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "tsconfig.json",
    "vite.config.js",
    "vite.config.ts",
    "dockerfile",
    "docker-compose.yml",
    "go.mod",
    "cargo.toml",
    "pom.xml",
}


def _normalise_requested_file_path(raw: str) -> str | None:
    rel = (raw or "").strip().strip("'\"`.,;:()[]{}").replace("\\", "/").lstrip("/")
    rel = re.sub(r"\s+", " ", rel)
    if not rel or rel.startswith("../") or "/../" in rel or rel == "..":
        return None
    if ":" in rel:
        return None
    if not REQUESTED_FILE_PATH_RE.fullmatch(rel):
        return None
    return rel


def _requested_file_paths(prompt: str) -> list[str]:
    paths: list[str] = []

    def add(raw: str) -> None:
        rel = _normalise_requested_file_path(raw)
        if rel and rel not in paths:
            paths.append(rel)

    def add_typed(kind: str, name: str) -> None:
        clean = (name or "").strip().strip("'\"`.,;:()[]{}")
        if not clean:
            return
        suffix = FILE_KIND_EXTENSIONS.get(kind.lower(), "")
        if suffix and "." not in Path(clean.replace("\\", "/")).name:
            clean = f"{clean}{suffix}"
        add(clean)

    for pattern in (REQUESTED_QUOTED_TYPED_FILE_RE, REQUESTED_UNQUOTED_TYPED_FILE_RE):
        for match in pattern.finditer(prompt or ""):
            add_typed(match.group("kind"), match.group("name"))

    for match in REQUESTED_FILE_LABEL_RE.finditer(prompt or ""):
        nested = REQUESTED_FILE_PATH_RE.search(match.group(1))
        if nested:
            add(nested.group("path"))

    for match in re.finditer(r"['\"`]([^'\"`\r\n]+\.[A-Za-z0-9]{1,12})['\"`]", prompt or ""):
        nested = REQUESTED_FILE_PATH_RE.search(match.group(1))
        if nested:
            add(nested.group("path"))

    return paths[:5]


def _parse_file_blocks(reply: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for match in FILE_BLOCK_RE.finditer(reply or ""):
        rel = _normalise_requested_file_path(match.group(1))
        if rel:
            blocks.append((rel, match.group(2)))
    return blocks


def _write_generated_file(rel_path: str, content: str) -> dict[str, Any]:
    target = _resolve(rel_path)
    if target.is_dir():
        raise HTTPException(status_code=400, detail=f"Target is a folder: {rel_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    created = not target.exists()
    target.write_text(content, encoding="utf-8", newline="")
    return {"path": _rel_to_root(target), "size": target.stat().st_size, "created": created}


def _auto_apply_file_blocks(reply: str, session: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    # If the model splits a file into several blocks despite instructions,
    # keep the longest version per path so a stub never clobbers a fuller one.
    best: dict[str, str] = {}
    for rel_path, content in _parse_file_blocks(reply):
        if rel_path not in best or len(content) > len(best[rel_path]):
            best[rel_path] = content
    applied: list[dict[str, Any]] = []
    for rel_path, content in best.items():
        try:
            info = _write_generated_file(rel_path, content)
            info["ok"] = True
            applied.append(info)
            if session is not None:
                _log(session, "coder.ai_write", f"AI wrote {info['path']} for them", path=info["path"])
        except Exception as exc:
            applied.append({"path": rel_path, "ok": False, "error": str(exc)})
    return applied


def init(
    runtime: Any,
    data_dir: Path,
    project_root: Path,
    memory_provider: Any = None,
    external_context_provider: Any = None,
) -> None:
    global _runtime, _workspace_file, _default_suggestions, _memory_provider, _external_context_provider, _user_spaces_dir
    _runtime = runtime
    _memory_provider = memory_provider
    _external_context_provider = external_context_provider
    _workspace_file = data_dir / "coder_workspace.json"
    _user_spaces_dir = project_root / "workspaces"
    home = Path.home()
    _default_suggestions = [
        project_root,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
    ]


def _client_host(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def _bind(request: Request) -> dict[str, Any]:
    """Resolve who is calling and remember it for the rest of this request's thread."""
    host = _client_host(request)
    sid = re.sub(r"[^A-Za-z0-9_-]", "", request.cookies.get("caraxes_sid") or "")[:64]
    info = {
        "is_owner": host in OWNER_HOSTS,
        "sid": sid or f"ip-{host or 'unknown'}",
        "host": host,
        "user": accounts.current_user(request),
    }
    _session_ctx.set(info)
    return info


def _log(info: dict[str, Any], kind: str, detail: str, path: str | None = None) -> None:
    try:
        workspace = str(_current_root().resolve())
    except HTTPException:
        workspace = None
    accounts.log_activity(info.get("user"), kind, detail, path=path, workspace=workspace)


def _session_info() -> dict[str, Any]:
    info = _session_ctx.get()
    if info is None:
        raise HTTPException(status_code=500, detail="Session not bound")
    return info


def _load_state() -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if _workspace_file and _workspace_file.exists():
        try:
            raw = json.loads(_workspace_file.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    if raw.get("version") == 2:
        raw.setdefault("owner", {"root": None, "recents": []})
        raw.setdefault("sessions", {})
        raw.setdefault("shared", [])
        return raw
    # Migrate the old single-workspace format: it belonged to the owner.
    return {
        "version": 2,
        "owner": {"root": raw.get("root"), "recents": raw.get("recents", [])},
        "sessions": {},
        "shared": [],
    }


def _save_state(state: dict[str, Any]) -> None:
    if _workspace_file:
        _workspace_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _session_slot(state: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    if info["is_owner"]:
        return state["owner"]
    sessions: dict[str, Any] = state["sessions"]
    slot = sessions.setdefault(info["sid"], {"root": None, "recents": []})
    slot["updated_at"] = time.time()
    if len(sessions) > MAX_REMOTE_SESSIONS:
        oldest = sorted(sessions.items(), key=lambda item: item[1].get("updated_at", 0))
        for key, _ in oldest[: len(sessions) - MAX_REMOTE_SESSIONS]:
            if key != info["sid"]:
                sessions.pop(key, None)
    return slot


def _shared_roots(state: dict[str, Any]) -> list[Path]:
    roots = []
    for item in state.get("shared", []):
        path = Path(item)
        if path.is_dir():
            roots.append(path.resolve())
    return roots


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _personal_root(info: dict[str, Any]) -> Path | None:
    """Every signed-in user gets a personal folder on this PC to upload and work in."""
    user = info.get("user")
    if not user or _user_spaces_dir is None:
        return None
    safe = re.sub(r"[^a-z0-9_-]", "", (user.get("username") or "").lower())[:32]
    if not safe:
        return None
    return (_user_spaces_dir / safe).resolve()


def _user_space_suggestions(current_user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if _user_spaces_dir is None:
        return []
    current_username = ((current_user or {}).get("username") or "").lower()
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for user in accounts.list_users():
        username = (user.get("username") or "").lower()
        safe = re.sub(r"[^a-z0-9_-]", "", username)[:32]
        if not safe:
            continue
        path = (_user_spaces_dir / safe).resolve()
        if not path.is_dir():
            continue
        seen.add(safe)
        display = user.get("display_name") or user.get("username") or safe
        label = f"My space ({display})" if username == current_username else f"{display}'s uploaded space"
        suggestions.append({"path": str(path), "name": label, "username": username})
    if _user_spaces_dir.is_dir():
        for child in sorted(_user_spaces_dir.iterdir(), key=lambda item: item.name.lower()):
            safe = child.name.lower()
            if child.is_dir() and safe not in seen:
                suggestions.append({"path": str(child.resolve()), "name": f"{child.name}'s uploaded space", "username": child.name})
    return suggestions


def _remote_allowed(root: Path, info: dict[str, Any], state: dict[str, Any]) -> bool:
    personal = _personal_root(info)
    if personal is not None and _is_within(root, personal):
        return True
    return any(_is_within(root, shared) for shared in _shared_roots(state))


def _current_root() -> Path:
    info = _session_info()
    state = _load_state()
    slot = state["owner"] if info["is_owner"] else state["sessions"].get(info["sid"], {})
    root_value = slot.get("root")
    if not root_value:
        raise HTTPException(status_code=400, detail="No workspace is open. Open a folder first.")
    root = Path(root_value)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Workspace folder no longer exists: {root}")
    if not info["is_owner"] and not _remote_allowed(root.resolve(), info, state):
        raise HTTPException(
            status_code=403,
            detail="This folder is no longer shared by the host. Ask the host to share it again.",
        )
    return root


def _resolve(rel_path: str) -> Path:
    root = _current_root().resolve()
    rel = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    candidate = (root / rel).resolve() if rel else root
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path escapes the workspace")
    return candidate


def _rel_to_root(path: Path) -> str:
    root = _current_root().resolve()
    return path.resolve().relative_to(root).as_posix() if path.resolve() != root else ""


def _entry_info(path: Path) -> dict[str, Any]:
    is_dir = path.is_dir()
    info: dict[str, Any] = {
        "name": path.name,
        "path": _rel_to_root(path),
        "is_dir": is_dir,
    }
    if not is_dir:
        try:
            info["size"] = path.stat().st_size
        except OSError:
            info["size"] = None
        info["ext"] = path.suffix.lower().lstrip(".")
    return info


def _looks_binary(sample: bytes) -> bool:
    return b"\x00" in sample


class WorkspaceOpen(BaseModel):
    path: str = Field(min_length=1)


class FileSave(BaseModel):
    path: str = Field(min_length=1)
    content: str = Field(max_length=4_000_000)
    create_parents: bool = False


class LintIn(BaseModel):
    language: str = Field(default="", max_length=40)
    content: str = Field(default="", max_length=2_000_000)


class EntryCreate(BaseModel):
    path: str = Field(min_length=1)
    kind: str = Field(pattern="^(file|folder)$")


class EntryRename(BaseModel):
    path: str = Field(min_length=1)
    new_name: str = Field(min_length=1, max_length=255)


class CoderChatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=60_000)
    history: list[dict[str, str]] = Field(default_factory=list)
    mode: str = Field(default="ask", pattern="^(ask|edit)$")
    client_workspace: str = Field(default="server", pattern="^(server|local)$")
    workspace_listing: str | None = Field(default=None, max_length=80_000)
    can_run: bool = False
    file_path: str | None = None
    file_content: str | None = Field(default=None, max_length=2_000_000)
    language: str | None = None
    selection: str | None = Field(default=None, max_length=120_000)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1400, ge=64, le=4096)


@router.get("/workspace")
def get_workspace(request: Request) -> dict[str, Any]:
    info = _bind(request)
    state = _load_state()
    slot = _session_slot(state, info)
    shared = [str(path) for path in _shared_roots(state)]
    personal = _personal_root(info)
    user_spaces = _user_space_suggestions(info.get("user")) if info["is_owner"] else []
    if info["is_owner"]:
        suggestions = []
        if personal is not None:
            username = (info.get("user") or {}).get("display_name") or (info.get("user") or {}).get("username") or "you"
            suggestions.append({"path": str(personal), "name": f"My space ({username})"})
        suggestions.extend(
            {"path": str(path), "name": path.name or str(path)}
            for path in _default_suggestions
            if path.is_dir()
        )
        suggestions.extend(
            space for space in user_spaces
            if all(space["path"] != existing["path"] for existing in suggestions)
        )
    else:
        suggestions = []
        if personal is not None:
            username = (info.get("user") or {}).get("display_name") or (info.get("user") or {}).get("username") or "you"
            suggestions.append({"path": str(personal), "name": f"My space ({username})"})
        suggestions.extend({"path": item, "name": Path(item).name or item} for item in shared)
    root_value = slot.get("root")
    if root_value and not Path(root_value).is_dir():
        root_value = None
    return {
        "root": root_value,
        "root_name": Path(root_value).name if root_value else None,
        "recents": [item for item in slot.get("recents", []) if Path(item).is_dir()],
        "suggestions": suggestions,
        "is_owner": info["is_owner"],
        "personal_root": str(personal) if personal is not None else None,
        "user_spaces": user_spaces,
        "shared": shared,
        "can_run": info["is_owner"] or ALLOW_REMOTE_RUN,
    }


@router.post("/workspace")
def open_workspace(payload: WorkspaceOpen, request: Request) -> dict[str, Any]:
    info = _bind(request)
    root = Path(payload.path.strip()).expanduser()
    if not root.is_absolute():
        raise HTTPException(status_code=400, detail="Use an absolute folder path, for example C:\\Users\\you\\project")
    if not root.is_dir():
        personal = _personal_root(info)
        if personal is not None and _is_within(root.resolve(), personal):
            root.resolve().mkdir(parents=True, exist_ok=True)
        elif not info["is_owner"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Remote browsers cannot open a folder path from their own PC directly. "
                    "Open My space, then use Upload folder to copy that device's files into Caraxes."
                ),
            )
        else:
            raise HTTPException(status_code=400, detail=f"Not a folder: {root}")
    root = root.resolve()
    state = _load_state()
    if not info["is_owner"] and not _remote_allowed(root, info, state):
        raise HTTPException(
            status_code=403,
            detail=(
                "Only your personal space and folders shared by the host can be opened from other devices. "
                "To work with a folder from this device, open My space and upload the folder."
            ),
        )
    slot = _session_slot(state, info)
    slot["root"] = str(root)
    slot["recents"] = [str(root)] + [item for item in slot.get("recents", []) if item != str(root)]
    slot["recents"] = slot["recents"][:MAX_RECENT_WORKSPACES]
    _save_state(state)
    accounts.log_activity(info.get("user"), "coder.workspace", f'opened folder "{root.name or root}"', workspace=str(root))
    return {"root": str(root), "root_name": root.name or str(root)}


class SharePayload(BaseModel):
    path: str = Field(min_length=1)
    shared: bool


@router.post("/share")
def set_shared(payload: SharePayload, request: Request) -> dict[str, Any]:
    info = _bind(request)
    if not info["is_owner"]:
        raise HTTPException(status_code=403, detail="Only the host machine can manage shared folders")
    target = Path(payload.path.strip()).expanduser()
    if not target.is_absolute() or not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a folder: {target}")
    target = target.resolve()
    state = _load_state()
    shared = [item for item in state.get("shared", []) if Path(item).resolve() != target]
    if payload.shared:
        shared.append(str(target))
    state["shared"] = shared
    _save_state(state)
    return {"shared": shared}


class RunIn(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    shell: str = Field(default="powershell", pattern="^(powershell|cmd)$")


@router.post("/run")
def run_command(payload: RunIn, request: Request) -> dict[str, Any]:
    info = _bind(request)
    if not info["is_owner"] and not ALLOW_REMOTE_RUN:
        raise HTTPException(
            status_code=403,
            detail="Running commands is only allowed from the host machine (set CARAXES_REMOTE_SHELL=1 to change this).",
        )
    root = _current_root()
    if payload.shell == "cmd":
        args = ["cmd", "/d", "/c", payload.command]
    else:
        args = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", payload.command]
    _log(info, "coder.run", f"ran command: {payload.command[:160]}")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            cwd=str(root),
            capture_output=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "timed_out": True,
            "stdout": (exc.stdout or b"").decode("utf-8", errors="replace")[-MAX_RUN_OUTPUT_CHARS:],
            "stderr": f"Command timed out after {RUN_TIMEOUT_SECONDS} seconds.",
            "duration_ms": int((time.monotonic() - started) * 1000),
            "cwd": str(root),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start the command: {exc}")
    return {
        "exit_code": completed.returncode,
        "timed_out": False,
        "stdout": completed.stdout.decode("utf-8", errors="replace")[-MAX_RUN_OUTPUT_CHARS:],
        "stderr": completed.stderr.decode("utf-8", errors="replace")[-MAX_RUN_OUTPUT_CHARS:],
        "duration_ms": int((time.monotonic() - started) * 1000),
        "cwd": str(root),
    }


@router.get("/tree")
def list_dir(request: Request, path: str = Query(default="")) -> list[dict[str, Any]]:
    _bind(request)
    target = _resolve(path)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Not a folder")
    try:
        children = list(target.iterdir())
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    entries = [_entry_info(child) for child in children]
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return entries


@router.get("/file")
def read_file(request: Request, path: str = Query(min_length=1)) -> dict[str, Any]:
    _bind(request)
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    size = target.stat().st_size
    suffix = target.suffix.lower()
    base = {"path": _rel_to_root(target), "name": target.name, "size": size}

    if suffix in IMAGE_SUFFIXES:
        return {**base, "kind": "image"}
    if suffix == ".pdf":
        return {**base, "kind": "pdf"}

    with target.open("rb") as handle:
        sample = handle.read(8192)
    if _looks_binary(sample):
        return {**base, "kind": "binary"}
    if size > MAX_EDITOR_FILE_BYTES:
        return {**base, "kind": "toolarge"}

    content = target.read_text(encoding="utf-8", errors="replace")
    try:
        last_edit = accounts.last_edit_for_path(base["path"], str(_current_root().resolve()))
    except Exception:
        last_edit = None
    return {**base, "kind": "text", "content": content, "last_edit": last_edit}


@router.get("/raw")
def raw_file(request: Request, path: str = Query(min_length=1)) -> FileResponse:
    _bind(request)
    target = _resolve(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


def _safe_download_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", (name or "").strip()).strip(" .")
    return cleaned or fallback


def _cleanup_temp_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


@router.get("/download")
def download_entry(request: Request, path: str = Query(default="")) -> FileResponse:
    info = _bind(request)
    target = _resolve(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    rel = _rel_to_root(target)
    if target.is_file():
        _log(info, "coder.download", f"downloaded {rel}", path=rel)
        return FileResponse(target, filename=target.name, media_type="application/octet-stream")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Can only download files or folders")

    root_name = _safe_download_name(target.name or _current_root().name, "workspace")
    handle = tempfile.NamedTemporaryFile(prefix="caraxes-download-", suffix=".zip", delete=False)
    zip_path = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for current, dirs, files in os.walk(target, followlinks=False):
                current_path = Path(current)
                dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
                rel_dir = current_path.relative_to(target).as_posix()
                archive_dir = root_name if rel_dir == "." else f"{root_name}/{rel_dir}"
                if not files and not dirs:
                    archive.writestr(f"{archive_dir}/", "")
                for file_name in files:
                    file_path = current_path / file_name
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    rel_file = file_path.relative_to(target).as_posix()
                    archive.write(file_path, f"{root_name}/{rel_file}")
    except Exception as exc:
        _cleanup_temp_file(str(zip_path))
        raise HTTPException(status_code=500, detail=f"Could not prepare download: {exc}")

    label = rel or _current_root().name or "workspace"
    _log(info, "coder.download", f"downloaded folder {label}", path=rel or None)
    return FileResponse(
        zip_path,
        filename=f"{root_name}.zip",
        media_type="application/zip",
        background=BackgroundTask(_cleanup_temp_file, str(zip_path)),
    )


@router.put("/file")
def save_file(payload: FileSave, request: Request) -> dict[str, Any]:
    info = _bind(request)
    target = _resolve(payload.path)
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Target is a folder")
    if not target.parent.is_dir():
        if payload.create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        else:
            raise HTTPException(status_code=400, detail="Parent folder does not exist")
    created = not target.exists()
    target.write_text(payload.content, encoding="utf-8", newline="")
    rel = _rel_to_root(target)
    _log(info, "coder.create" if created else "coder.save", f"{'created' if created else 'saved'} {rel}", path=rel)
    return {"ok": True, "path": rel, "size": target.stat().st_size, "created": created}


@router.post("/upload")
def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    target: str = Query(default=""),
) -> dict[str, Any]:
    info = _bind(request)
    base = _resolve(target)
    if not base.is_dir():
        raise HTTPException(status_code=400, detail="Upload target is not a folder")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files at once (max {MAX_UPLOAD_FILES})")
    root = _current_root().resolve()
    saved: list[dict[str, Any]] = []
    errors: list[str] = []
    for upload in files:
        # Folder uploads send the relative path as the filename; keep the structure.
        raw_name = (upload.filename or "upload.bin").replace("\\", "/")
        rel = "/".join(part for part in raw_name.split("/") if part not in ("", ".", ".."))
        if not rel:
            errors.append(f"Skipped a file with an unusable name: {upload.filename}")
            continue
        dest = (base / rel).resolve()
        if dest != root and root not in dest.parents:
            errors.append(f"Skipped (escapes the workspace): {raw_name}")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            saved.append({"path": dest.relative_to(root).as_posix(), "size": dest.stat().st_size})
        except OSError as exc:
            errors.append(f"{raw_name}: {exc}")
    target_rel = _rel_to_root(base)
    _log(
        info,
        "coder.upload",
        f"uploaded {len(saved)} file{'s' if len(saved) != 1 else ''} to {target_rel or 'the workspace root'}",
        path=target_rel or None,
    )
    return {"saved": saved, "errors": errors}


@router.post("/share-local")
def share_local_folder(
    request: Request,
    files: list[UploadFile] = File(...),
    folder_name: str = Query(default="shared-folder", max_length=120),
) -> dict[str, Any]:
    info = _bind(request)
    personal = _personal_root(info)
    if personal is None:
        raise HTTPException(status_code=401, detail="Sign in before sharing a local folder")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files at once (max {MAX_UPLOAD_FILES})")
    personal.mkdir(parents=True, exist_ok=True)
    target_name = _safe_download_name(folder_name, "shared-folder")
    base = (personal / "shared_from_device" / target_name).resolve()
    if not _is_within(base, personal.resolve()):
        raise HTTPException(status_code=400, detail="Share target escapes your personal space")
    if base.exists():
        if base.is_dir():
            shutil.rmtree(base)
        else:
            base.unlink()
    base.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, Any]] = []
    errors: list[str] = []
    for upload in files:
        raw_name = (upload.filename or "upload.bin").replace("\\", "/")
        rel = "/".join(part for part in raw_name.split("/") if part not in ("", ".", ".."))
        if not rel:
            errors.append(f"Skipped a file with an unusable name: {upload.filename}")
            continue
        dest = (base / rel).resolve()
        if dest != base and base not in dest.parents:
            errors.append(f"Skipped (escapes the share folder): {raw_name}")
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
            saved.append({"path": dest.relative_to(base).as_posix(), "size": dest.stat().st_size})
        except OSError as exc:
            errors.append(f"{raw_name}: {exc}")

    _log(
        info,
        "coder.share_local",
        f"shared local folder {target_name} to their server space ({len(saved)} files)",
        path=f"shared_from_device/{target_name}",
    )
    return {
        "root": str(base),
        "name": target_name,
        "relative_root": base.relative_to(personal).as_posix(),
        "saved": saved,
        "errors": errors,
    }


@router.post("/lint")
def lint_code(payload: LintIn) -> dict[str, Any]:
    """Syntax-check code the editor sends. Python via ast, JSON via json.loads;
    other languages rely on Monaco's built-in validation and return no markers."""
    markers: list[dict[str, Any]] = []
    if payload.language == "python":
        try:
            ast.parse(payload.content)
        except SyntaxError as exc:
            line = exc.lineno or 1
            column = exc.offset or 1
            markers.append(
                {
                    "line": line,
                    "column": column,
                    "endLine": exc.end_lineno or line,
                    "endColumn": exc.end_offset or column + 1,
                    "message": f"SyntaxError: {exc.msg}",
                    "severity": "error",
                }
            )
        except Exception as exc:
            markers.append(
                {"line": 1, "column": 1, "endLine": 1, "endColumn": 2, "message": str(exc), "severity": "error"}
            )
    elif payload.language == "json":
        try:
            json.loads(payload.content or "null")
        except json.JSONDecodeError as exc:
            markers.append(
                {
                    "line": exc.lineno,
                    "column": exc.colno,
                    "endLine": exc.lineno,
                    "endColumn": exc.colno + 1,
                    "message": exc.msg,
                    "severity": "error",
                }
            )
    return {"markers": markers}


@router.post("/entry")
def create_entry(payload: EntryCreate, request: Request) -> dict[str, Any]:
    info = _bind(request)
    target = _resolve(payload.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="Already exists")
    if not target.parent.is_dir():
        raise HTTPException(status_code=400, detail="Parent folder does not exist")
    if payload.kind == "folder":
        target.mkdir()
    else:
        target.touch()
    entry = _entry_info(target)
    _log(info, "coder.create", f"created {payload.kind} {entry['path']}", path=entry["path"])
    return entry


@router.post("/rename")
def rename_entry(payload: EntryRename, request: Request) -> dict[str, Any]:
    _bind(request)
    target = _resolve(payload.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target == _current_root().resolve():
        raise HTTPException(status_code=400, detail="Cannot rename the workspace root")
    new_name = payload.new_name.strip()
    if any(sep in new_name for sep in ("/", "\\")) or new_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid name")
    destination = target.with_name(new_name)
    if destination.exists():
        raise HTTPException(status_code=409, detail="A file or folder with that name already exists")
    old_rel = _rel_to_root(target)
    target.rename(destination)
    entry = _entry_info(destination)
    _log(_session_info(), "coder.rename", f"renamed {old_rel} to {entry['path']}", path=entry["path"])
    return entry


@router.delete("/entry")
def delete_entry(request: Request, path: str = Query(min_length=1)) -> dict[str, bool]:
    info = _bind(request)
    target = _resolve(path)
    if target == _current_root().resolve():
        raise HTTPException(status_code=400, detail="Cannot delete the workspace root")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Not found")
    rel = _rel_to_root(target)
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    _log(info, "coder.delete", f"deleted {rel}", path=rel)
    return {"ok": True}


def _workspace_file_list() -> str:
    """A shallow, capped listing of workspace files for the model's context."""
    try:
        root = _current_root().resolve()
    except HTTPException:
        return ""
    lines: list[str] = []
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue and len(lines) < MAX_LISTED_FILES:
        folder, depth = queue.pop(0)
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            continue
        for child in children:
            if len(lines) >= MAX_LISTED_FILES:
                break
            name = child.name
            if child.is_dir():
                if name.startswith(".") or name.lower() in LIST_IGNORED_DIR_NAMES:
                    continue
                rel = child.relative_to(root).as_posix()
                lines.append(f"{rel}/")
                if depth + 1 < MAX_LIST_DEPTH:
                    queue.append((child, depth + 1))
            else:
                lines.append(child.relative_to(root).as_posix())
    text = "\n".join(lines)
    return text[:MAX_LIST_CHARS]


def _prompt_terms(text: str) -> list[str]:
    terms = re.findall(r"[a-zA-Z0-9_.$#-]{3,}", (text or "").lower())
    stop = {"the", "and", "for", "with", "this", "that", "file", "code", "what", "how", "why", "you", "about"}
    return [term for term in terms if term not in stop]


def _iter_candidate_files() -> list[Path]:
    root = _current_root().resolve()
    files: list[Path] = []
    queue: list[Path] = [root]
    while queue and len(files) < MAX_RELATED_SCAN_FILES:
        folder = queue.pop(0)
        try:
            children = sorted(folder.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
        except OSError:
            continue
        for child in children:
            name = child.name
            if child.is_dir():
                if name.startswith(".") or name.lower() in LIST_IGNORED_DIR_NAMES:
                    continue
                queue.append(child)
                continue
            suffix = child.suffix.lower()
            if suffix in RELATED_SUFFIXES or name.lower() in IMPORTANT_RELATED_NAMES:
                files.append(child)
                if len(files) >= MAX_RELATED_SCAN_FILES:
                    break
    return files


def _safe_read_text(path: Path, limit: int) -> str:
    try:
        if path.stat().st_size > 300_000:
            return ""
        with path.open("rb") as handle:
            sample = handle.read(8192)
        if _looks_binary(sample):
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _related_file_score(path: Path, prompt: str, open_file: str | None, terms: list[str]) -> int:
    root = _current_root().resolve()
    rel = path.resolve().relative_to(root).as_posix().lower()
    name = path.name.lower()
    score = 0
    if name in IMPORTANT_RELATED_NAMES:
        score += 35
    if rel.startswith(("src/", "app/", "lib/", "tests/", "test/", "docs/", ".github/workflows/", "scripts/")):
        score += 8
    if open_file:
        open_parent = Path(open_file).parent.as_posix().lower()
        if open_parent and rel.startswith(open_parent + "/"):
            score += 18
        stem = Path(open_file).stem.lower()
        if stem and stem in rel:
            score += 15
    for term in terms:
        if term in rel:
            score += 12
    sample = _safe_read_text(path, 2000).lower()
    for term in terms[:20]:
        score += min(sample.count(term), 3) * 4
    if any(word in (prompt or "").lower() for word in ("test", "bug", "review", "security", "vulnerability")):
        if "test" in rel or "spec" in rel:
            score += 14
    return score


def _workflow_instruction(prompt: str) -> str:
    lower = (prompt or "").lower()
    if any(word in lower for word in ("siem", "edr", "incident", "timeline", "alert", "blue team")):
        return (
            "### Workflow mode\n"
            "Blue-team triage: summarize evidence, timeline, suspicious entities, MITRE mapping, containment, "
            "detection improvements, and exact missing evidence. Separate facts from hypotheses."
        )
    if any(word in lower for word in ("purple", "att&ck", "emulation", "detection rule", "sigma", "yara")):
        return (
            "### Workflow mode\n"
            "Purple/detection engineering: use TTP-level red-team knowledge for authorized validation, then focus on "
            "telemetry, detections, false positives, hardening, and test cases."
        )
    if any(word in lower for word in ("security", "vulnerability", "cwe", "owasp", "secure")):
        return (
            "### Workflow mode\n"
            "Secure-code review: lead with severity-ordered findings, explain impact defensively, map to CWE/OWASP where useful, "
            "and provide safe fixes and abuse-case tests."
        )
    if any(word in lower for word in ("review", "bug", "refactor", "test", "explain")):
        return (
            "### Workflow mode\n"
            "Coding review: explain the relevant code path, list findings by severity, suggest the smallest safe change, "
            "and name tests or commands to verify."
        )
    return ""


def _related_workspace_context(payload: CoderChatIn) -> str:
    try:
        root = _current_root().resolve()
    except HTTPException:
        return ""
    terms = _prompt_terms(payload.prompt)
    candidates = _iter_candidate_files()
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        rel = path.resolve().relative_to(root).as_posix()
        if payload.file_path and rel == payload.file_path:
            continue
        score = _related_file_score(path, payload.prompt, payload.file_path, terms)
        if score > 0:
            scored.append((score, path))
    scored.sort(reverse=True, key=lambda item: item[0])
    selected = scored[:MAX_RELATED_FILES]
    if not selected:
        return ""
    blocks = [
        "### Related workspace files selected locally\n"
        "These files were selected by path/content scoring. Use them as context, and ask for more files if needed."
    ]
    for score, path in selected:
        rel = path.resolve().relative_to(root).as_posix()
        text = _safe_read_text(path, MAX_RELATED_FILE_CHARS)
        if not text.strip():
            continue
        blocks.append(f"--- Related file: {rel} (score {score}) ---\n{text}")
    return "\n\n".join(blocks)[: MAX_RELATED_FILE_CHARS * (MAX_RELATED_FILES + 1)]


def _build_coder_messages(payload: CoderChatIn, research_sources: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    system_parts = [CODER_SYSTEM_PROMPT]
    if payload.can_run:
        system_parts.append(RUN_PROTOCOL)
    if _memory_provider is not None:
        try:
            memory_context = _memory_provider()
        except Exception:
            memory_context = ""
        if memory_context:
            system_parts.append(memory_context)
    messages: list[dict[str, str]] = [{"role": "system", "content": "\n\n".join(system_parts)}]

    budget = MAX_PROMPT_HISTORY_CHARS
    for item in payload.history[-MAX_PROMPT_HISTORY_MESSAGES:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in {"user", "assistant"} and content and budget > 0:
            clipped = content[-budget:]
            messages.append({"role": role, "content": clipped})
            budget -= len(clipped)

    context_blocks: list[str] = []
    if payload.client_workspace == "local":
        context_blocks.append(
            "### Workspace location\n"
            "The user is editing a browser-local folder on their own device. The server cannot access that folder directly. "
            "If you output FILE blocks, the browser will apply them locally only when the user clicks Apply. "
            "Do not claim that files were saved on the server unless the user explicitly shares/uploads the folder."
        )
    workflow = _workflow_instruction(payload.prompt)
    if workflow:
        context_blocks.append(workflow)
    if _external_context_provider is not None:
        try:
            external = _external_context_provider(payload.prompt)
        except Exception as exc:
            external = {"context": f"### External research\nWeb/GitHub lookup failed: {exc}", "sources": []}
        if isinstance(external, dict):
            external_context = (external.get("context") or "").strip()
            if external_context:
                if len(external_context) > MAX_EXTERNAL_CONTEXT_CHARS:
                    external_context = (
                        external_context[:MAX_EXTERNAL_CONTEXT_CHARS].rstrip()
                        + "\n\n[External research clipped locally to fit the model context.]"
                    )
                context_blocks.append(external_context)
            if research_sources is not None:
                research_sources.extend(external.get("sources") or [])
        elif isinstance(external, str) and external.strip():
            context_blocks.append(external.strip())
    requested_paths = _requested_file_paths(payload.prompt)
    if requested_paths:
        context_blocks.append(
            "### Exact file target(s) named by the user\n"
            "When creating or writing files for this request, use these exact workspace-relative path(s) in FILE headers. "
            "Do not add a parent folder unless it is already shown here:\n"
            + "\n".join(f"- {path}" for path in requested_paths)
        )
    if payload.workspace_listing:
        context_blocks.append(
            "### Browser-local workspace files (partial listing; use these relative paths in FILE headers)\n"
            + payload.workspace_listing
        )
    elif payload.client_workspace == "server":
        file_list = _workspace_file_list()
        if file_list:
            context_blocks.append(
                "### Workspace files (partial listing; use these relative paths in FILE headers)\n" + file_list
            )
        related = _related_workspace_context(payload)
        if related:
            context_blocks.append(related)
    if payload.file_content is not None and payload.file_path:
        language = payload.language or ""
        content = payload.file_content
        clipped_note = ""
        if len(content) > MAX_PROMPT_FILE_CHARS:
            content = content[:MAX_PROMPT_FILE_CHARS]
            clipped_note = f"\n[File clipped to the first {MAX_PROMPT_FILE_CHARS} characters.]"
        context_blocks.append(
            f"### Open file: {payload.file_path}\n```{language}\n{content}\n```{clipped_note}"
        )
    if payload.selection and payload.selection.strip():
        context_blocks.append(
            f"### Currently selected in the editor\n```{payload.language or ''}\n{payload.selection}\n```"
        )

    user_text = payload.prompt
    if payload.mode == "edit":
        user_text = f"{EDIT_MODE_INSTRUCTION}\n\nRequested change:\n{payload.prompt}"
    else:
        user_text = (
            "Answer the request directly. Do not output '### FILE:' headers or complete-file write blocks unless "
            "the user explicitly asks you to create, save, or modify files.\n\n"
            f"Request:\n{payload.prompt}"
        )
    if context_blocks:
        user_text = "\n\n".join(context_blocks) + f"\n\n### Request\n{user_text}"
    messages.append({"role": "user", "content": user_text})
    return messages


@router.post("/chat")
def coder_chat(payload: CoderChatIn, request: Request) -> dict[str, Any]:
    info = _bind(request)
    if _runtime is None:
        raise HTTPException(status_code=503, detail="Model runtime is not initialised")
    if payload.can_run and not (info["is_owner"] or ALLOW_REMOTE_RUN):
        payload.can_run = False
    research_sources: list[dict[str, Any]] = []
    messages = _build_coder_messages(payload, research_sources)
    applied_files: list[dict[str, Any]] = []
    try:
        reply = _runtime.chat(messages, payload.temperature, payload.max_tokens)
    except Exception as exc:
        if _runtime.openai_base_url:
            reply = (
                "I could not reach the local model backend.\n\n"
                f"Reason: {exc}\n\n"
                f"The editor keeps working; check that the llama.cpp server is still running at "
                f"`{_runtime.openai_base_url}`."
            )
        else:
            reply = (
                "I could not run the local model yet.\n\n"
                f"Reason: {exc}\n\n"
                "Run `scripts\\download_model.ps1`, install `requirements-llm.txt`, and restart the server."
            )
    else:
        if payload.mode == "edit" and payload.client_workspace != "local":
            applied_files = _auto_apply_file_blocks(reply, info)
    return {
        "reply": reply,
        "model_status": _runtime.status(),
        "applied_files": applied_files,
        "research_sources": research_sources,
    }
