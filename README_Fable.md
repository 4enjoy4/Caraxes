# Caraxes: Landing Page + Coder (VS Code-style editor)

This document describes the changes made to turn Caraxes from a single chat page into a
three-page app: a landing page, the existing chat, and a new VS Code-style editor
("Caraxes Coder") that edits real folders on this PC with the local model as a pair
programmer.

## What was added

| Piece | Files | Purpose |
|---|---|---|
| Landing page | `static/home.html`, `static/home.css` | Entry point at `/` with the dragon art, live model status, and two choices: **Chat** and **Coder** |
| Coder page | `static/coder.html`, `static/coder.css`, `static/coder.js` | VS Code-style workbench at `/coder`: file explorer, tabs, Monaco editor, image/PDF preview, AI side panel |
| Coder backend | `app/coder.py` | All `/api/coder/*` endpoints: workspace, file tree, read/save/create/rename/delete, raw file serving, and the editor AI chat |
| Routing | `app/main.py` | `/` now serves the landing page, `/chat` the old chat UI, `/coder` the editor; the coder router is registered next to the existing API |
| Navigation | `static/index.html`, `static/styles.css` | Home / Coder links in the chat sidebar so every page links to the others |
| Vendored editor | `static/vendor/monaco/` | Monaco Editor 0.55.1 (the editor component real VS Code is built on), served locally |
| Vendored icons | `static/vendor/icons/` | 61 SVG file-type icons from Material Icon Theme (what many VS Code users install), served locally |

Both vendored packages are MIT-licensed and stored inside `static/`, so the app keeps
working with **no internet and no CDN** - consistent with Caraxes being a private LAN app.

## Why it was built this way

- **Monaco instead of a homemade highlighter.** The request was "like real VS Code".
  Monaco *is* VS Code's editor: it brings syntax coloring for Python, JavaScript,
  TypeScript, Java, Swift, Objective-C, C/C++, and dozens more, plus find/replace
  (`Ctrl+F`), multi-cursor, code folding, minimap, and a full undo stack for free.
  Reimplementing any of that by hand would be strictly worse.
- **A workspace root as the security boundary.** Like VS Code, you "open a folder".
  Every file API resolves paths against that root and rejects anything that escapes it
  (`..`, absolute paths, etc.). The browser can only touch what you deliberately opened -
  important because other devices on the LAN can reach this server.
- **The GGUF stays untouched.** The coder reuses the same `ModelRuntime` as the chat
  (llama.cpp backend on `127.0.0.1:9901` or embedded llama-cpp-python), so there is one
  model configuration for the whole app.
- **"Edit file" mode has a strict contract.** When you ask the model to change the open
  file, the backend instructs it to answer with a short summary plus *exactly one* fenced
  code block containing the complete updated file. That makes the **Apply to editor**
  button reliable: the UI takes the block and replaces the buffer content. The apply is a
  normal Monaco edit, so `Ctrl+Z` undoes it, and nothing touches disk until you press
  `Ctrl+S` - the model can never silently overwrite a file.
- **Lazy file tree.** Folders load their children only when expanded, so opening a big
  folder (or `.venv` with thousands of files) stays fast.
- **Kind detection before opening.** The backend classifies each file (text / image / pdf /
  binary / too large) so the UI shows an image viewer, an embedded PDF viewer, or a
  download card instead of dumping garbage into the editor. Binary detection is a null-byte
  probe on the first 8 KB - the same trick git uses.

## How the Coder works (tour)

1. Visit `http://localhost:9898/` → landing page → **Coder** (or go to `/coder` directly).
2. An **Open a folder** dialog appears with quick-access buttons (this project, Desktop,
   Documents, Downloads), your recent folders, or any absolute path you type. The chosen
   workspace is remembered in `data/coder_workspace.json` across restarts.
3. **Explorer** (left): real VS Code-style icons per file type, dotted files dimmed,
   lazy-expanding folders. Right-click for **New file / New folder / Rename / Delete /
   Ask AI about this file**. The explorer and AI panel are drag-resizable; sizes persist.
4. **Editor** (center): tabs with dirty-dot indicators, `Ctrl+S` to save, unsaved-changes
   warnings on close, cursor position / language / save state in the ember status bar.
   Images open in a checkered viewer, PDFs in the browser's PDF viewer.
5. **Caraxes AI** (right): two modes.
   - **Ask** - questions about the open file; the file content (and your current editor
     selection, shown as chips) is packed into the prompt automatically. The file chip is
     clickable to exclude it.
   - **Edit file** - describe a change; the model returns the full updated file and the
     code block gets an **Apply to editor** button. Every code block also has **Copy** and
     **Insert at cursor**.

## API reference (`app/coder.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/coder/workspace` | GET / POST | Read or set the current workspace root (+ recents, suggestions) |
| `/api/coder/tree?path=` | GET | List one folder level (dirs first, alphabetical) |
| `/api/coder/file?path=` | GET | Read a file: `{kind: text\|image\|pdf\|binary\|toolarge, content?}` |
| `/api/coder/file` | PUT | Save text content to disk (UTF-8) |
| `/api/coder/raw?path=` | GET | Stream the file bytes (image/PDF preview, downloads) |
| `/api/coder/entry` | POST / DELETE | Create file/folder; delete file/folder |
| `/api/coder/rename` | POST | Rename an entry in place |
| `/api/coder/chat` | POST | AI request with file/selection context and `ask` / `edit` mode |

Limits worth knowing: files over ~1.5 MB open as "too large" (download only); the file
content sent to the model is clipped to 24 000 characters so it fits the 8k context
window; the AI panel keeps the last 12 turns of its (in-memory) conversation.

## What was verified

- `/`, `/chat`, `/coder`, Monaco loader, and icon SVGs all serve 200 locally.
- Full file lifecycle over the API: open workspace → list tree → read `requirements.txt` →
  create `uploads/_coder_test.py` → save content → read back → rename → delete.
- Path traversal (`../../secret.txt`) is rejected with 400; the 5.4 GB GGUF is detected
  as binary instead of being read; PNG raw serving returns `image/png`.
- End-to-end with the real local model (llama.cpp backend on 9901): **Ask** mode answered
  a question about an attached file, and **Edit file** mode returned a correct summary +
  single complete-file code block for "add a docstring", i.e. exactly the format the
  Apply button consumes.

## Round 2 additions

- **Multi-file AI edits.** The model is no longer limited to the open file. Its prompt now
  includes a capped listing of workspace files, and it marks every file it wants written
  with a `### FILE: <relative path>` header followed by the complete content. The AI panel
  renders each of these as a file card with an **Apply to <name>** button (plus **Apply
  all** when there are several); applying writes straight to the correct path - creating
  the file and any missing folders - and refreshes open tabs and the tree. So "create a
  Weak.md describing my project" lands in `Weak.md`, not in whatever file happens to be open.
- **Syntax error checking.** A new `/api/coder/lint` endpoint syntax-checks Python (via
  `ast.parse`) and JSON on the server; the editor calls it ~0.6 s after you stop typing
  and draws red squiggles at the exact line/column. JavaScript and TypeScript are checked
  by Monaco itself. The status bar shows a live "No problems / ⚠ n problems" counter
  (hover it to see the messages).
- **Copy path from the explorer.** Right-click any file or folder → **Copy path**
  (workspace-relative, what the AI understands) or **Copy full path** (absolute Windows
  path). Paste it into a prompt to point the model at an exact file.
- **Right panel scrollbar + responsive sizing.** The AI conversation now has a visible
  themed scrollbar (WebKit + Firefox), long code blocks scroll inside their cards, and the
  panel widths and composer font sizes scale with the window (`~24 vw` default AI panel,
  clamped) so the layout reads the same on a laptop or an ultrawide.
- **Caraxes backgrounds.** The long-necked serpentine dragon (`caraxes-dragon.png` - the
  most House-of-the-Dragon-Caraxes of the two artworks) is now the cinematic backdrop of
  both the chat page and the coder (welcome screen full-bleed; explorer, tabs, and AI
  panel are slightly translucent so it burns through). To change the art everywhere, just
  replace `static/assets/caraxes-dragon.png` with any image - no code edits needed.

## Round 3 additions (multi-user, Auto mode, commands)

- **Each user gets their own workspace.** Every browser now carries a session cookie, and
  the coder stores one workspace per session (`data/coder_workspace.json`, format v2 -
  the old single workspace migrates automatically as the host's). Someone on another
  device no longer sees or changes the folder you have open.
- **Shared folders control what other devices can access.** Requests from the host
  machine (localhost) are the *owner* and can open anything. Other devices can only open
  folders the owner shared: the workspace dialog now has a "Shared with other devices"
  section where the owner shares/unshares folders with one click. Remote users' quick
  access shows only shared folders; opening anything else returns 403, and access is
  re-checked on every file operation (shared folders are read-write by design).
- **Auto mode + command execution.** The AI panel now has Ask / Edit / **Auto**. In Auto,
  the model can also emit `### RUN` blocks with PowerShell commands; the UI executes them
  in the workspace folder, shows exit code + output, and feeds the output back into the
  conversation so the model sees the result. Commands only run from the host machine
  (403 for remote devices; opt-in via `CARAXES_REMOTE_SHELL=1`), have a timeout
  (`CARAXES_RUN_TIMEOUT_SECONDS`, default 120 s), and run with the server's privileges -
  so Auto mode is powerful and should be used with the same care as a terminal.
  In Edit and Auto modes, FILE blocks are saved to the workspace automatically
  (server-side); in Ask mode nothing is ever written.
- **Large files open now.** The editor limit rose from 1.5 MB to **8 MB**
  (`CARAXES_EDITOR_MAX_BYTES` to change it); verified with a 3 MB text file.
- **Queue visibility for two users.** The local model answers one request at a time
  (requests are serialised with a lock, which is also why two simultaneous prompts used
  to feel broken). `/api/status` now reports `busy`, the status pill shows
  "Model answering...", and if you send while the model is busy the thinking indicator
  says your request is *queued* instead of leaving you guessing. The wait itself is
  physics: one 9B model, one request at a time.
- **Real markdown rendering.** Chat and coder replies now render `**bold**`, headings,
  bullet/numbered lists, links, and horizontal rules properly instead of showing raw
  asterisks - the single biggest readability fix for long answers.
- **Web search verified.** The exact query from the bug report ("Browse online for Python
  pathlib documentation") now returns docs.python.org as the first source; earlier
  failures were transient search-engine blocks, and the model falls back gracefully.

## Round 4 additions (accounts, private chats, activity feed)

- **Login / registration** at `/login` (`static/login.html`, backend in `app/accounts.py`).
  Every page and API now requires being signed in; unauthenticated visits redirect to the
  login page. Passwords are salted PBKDF2 hashes in the local SQLite database - accounts
  exist only on this PC. This is home-LAN-grade auth (no HTTPS), so use throwaway passwords.
- **Private per-user chat history.** Chats belong to the account that created them:
  other users cannot list, read, or delete them (they get 404, not even "exists").
  The **first account registered claims all chats created before accounts existed** -
  so register yourself first before giving the address to anyone else.
- **Activity feed at `/activity`** - a messenger-style timeline of who did what and when:
  file saves/creates/renames/deletes, AI-written files, executed commands, workspace opens,
  chat activity (only *that* someone chatted - never the message content), and sign-ins.
  Filter chips (All / Coder / Chat / Sign-ins), auto-refreshes every 5 s, day separators,
  per-user colored avatars. Kept to the latest 5 000 events.
- **"Who did what" in the coder.** Every file operation is logged with the account name,
  and when you open a file the status bar shows "Last edit: <name> · <time>" pulled from
  the log - so two people working in the same shared folder can see whose change is whose.
- Machine-level trust is unchanged and separate from accounts: running commands and
  managing shared folders still requires being on the host machine (localhost), whoever
  is signed in.

## Round 5 additions (personal spaces + uploads)

- **Every user gets "My space"** - a personal folder on the host PC
  (`workspaces/<username>`, auto-created on first open). Remote users see it as the
  first entry in their folder list and can always open it, no sharing needed. This is
  the answer to "the other user cannot use their directory": their files live on their
  device, so they bring them over by uploading into My space.
- **Uploads in the coder.** Two new explorer buttons: *Upload files* and *Upload a whole
  folder* (keeps the folder structure). Also right-click any folder → "Upload files
  here...", and drag & drop files from the desktop straight onto the tree (dropping on a
  folder targets that folder). Up to 1000 files per batch; nested paths are preserved;
  filenames trying to escape the workspace (`../`) are neutralised - verified they cannot
  land outside.
- Every upload is logged in the activity feed ("uploaded 3 files to src").

## Known limits / sensible next steps

- No streaming: replies appear when generation finishes (same as the chat page today).
- One folder at a time (like a single VS Code window); no multi-root workspaces.
- Delete is permanent (no recycle bin) - the UI double-confirms before doing it.
- The AI still does not ingest the whole repository automatically, but it now includes a
  capped workspace listing and locally selected related files based on the prompt, open
  file path, and lightweight content/path scoring. If broader coverage is needed, ask it
  which exact files it needs next.
- Editor AI conversations are not persisted to the database yet; refresh clears them.

## Laptop-only AI improvement guide

For coding, blue team, purple team, and red-team-aware defensive workflows, use:

`README_LAPTOP_IMPROVEMENTS.md`

That guide keeps improvements laptop-realistic: better retrieval, stricter prompts, web/GitHub context, memory notes, large-file workflows, and evaluation prompts instead of slow CPU training.

Applied from that guide:

- Chat now has workflow modes: Auto, Coding, Code review, Secure code, Blue team,
  Incident, Purple team, Detection, Red defense, and Large file.
- Uploaded file chunks now use SQLite FTS plus a lightweight local sparse-vector index
  for better relevant-part retrieval.
- Large files now include a file map in model context: total parts, included parts,
  structural sample parts, high-signal parts, and first/last line previews when available.
- Coder prompts now include workflow-specific instructions and selected related
  workspace files, while keeping Claude's workspace boundary and multi-file apply flow.
