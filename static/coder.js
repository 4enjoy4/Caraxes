/* Caraxes Coder - VS Code style workbench backed by /api/coder and Monaco. */

const state = {
  root: null,
  rootName: null,
  tabs: [],
  activePath: null,
  expandedPaths: new Set(),
  includeFile: true,
  mode: "ask",
  aiHistory: [],
  aiBusy: false,
  editor: null,
  isOwner: true,
  workspaceKind: "server",
  localRootHandle: null,
  localRootName: "",
  canRun: false,
  personalRoot: "",
  userSpaces: [],
  sharedList: [],
  modelBusy: false,
};

/* Every browser gets its own session id so each user has their own workspace. */
function ensureSession() {
  if (!document.cookie.includes("caraxes_sid=")) {
    const sid = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random()}`).replace(/[^a-z0-9]/gi, "");
    document.cookie = `caraxes_sid=${sid}; path=/; max-age=31536000; SameSite=Lax`;
  }
}

const els = {
  shell: document.querySelector("#coderShell"),
  workspaceBtn: document.querySelector("#workspaceBtn"),
  workspaceName: document.querySelector("#workspaceName"),
  statusPulse: document.querySelector("#statusPulse"),
  statusLabel: document.querySelector("#statusLabel"),
  toggleAiBtn: document.querySelector("#toggleAiBtn"),
  tree: document.querySelector("#tree"),
  tabs: document.querySelector("#tabs"),
  monacoHost: document.querySelector("#monacoHost"),
  previewHost: document.querySelector("#previewHost"),
  welcome: document.querySelector("#welcome"),
  welcomeTitle: document.querySelector("#welcomeTitle"),
  newFileBtn: document.querySelector("#newFileBtn"),
  newFolderBtn: document.querySelector("#newFolderBtn"),
  openLocalFolderBtn: document.querySelector("#openLocalFolderBtn"),
  shareLocalFolderBtn: document.querySelector("#shareLocalFolderBtn"),
  localActionOpenBtn: document.querySelector("#localActionOpenBtn"),
  localActionShareBtn: document.querySelector("#localActionShareBtn"),
  downloadWorkspaceBtn: document.querySelector("#downloadWorkspaceBtn"),
  refreshBtn: document.querySelector("#refreshBtn"),
  explorerPane: document.querySelector("#explorerPane"),
  explorerResizer: document.querySelector("#explorerResizer"),
  aiPanel: document.querySelector("#aiPanel"),
  aiResizer: document.querySelector("#aiResizer"),
  aiMessages: document.querySelector("#aiMessages"),
  aiContext: document.querySelector("#aiContext"),
  aiComposer: document.querySelector("#aiComposer"),
  aiInput: document.querySelector("#aiInput"),
  aiSendBtn: document.querySelector("#aiSendBtn"),
  modeAskBtn: document.querySelector("#modeAskBtn"),
  modeEditBtn: document.querySelector("#modeEditBtn"),
  sbWorkspace: document.querySelector("#sbWorkspace"),
  sbFile: document.querySelector("#sbFile"),
  sbProblems: document.querySelector("#sbProblems"),
  sbDirty: document.querySelector("#sbDirty"),
  sbPosition: document.querySelector("#sbPosition"),
  sbLanguage: document.querySelector("#sbLanguage"),
  openOverlay: document.querySelector("#openOverlay"),
  openForm: document.querySelector("#openForm"),
  openPathInput: document.querySelector("#openPathInput"),
  openError: document.querySelector("#openError"),
  openSuggestions: document.querySelector("#openSuggestions"),
  openRecents: document.querySelector("#openRecents"),
  openCancelBtn: document.querySelector("#openCancelBtn"),
  ctxMenu: document.querySelector("#ctxMenu"),
};

const FILE_ICON_BY_EXT = {
  js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "react",
  ts: "typescript", tsx: "react_ts",
  py: "python", pyw: "python",
  java: "java", swift: "swift", m: "objective-c", mm: "objective-c",
  c: "c", h: "h", hpp: "hpp", hh: "hpp", cpp: "cpp", cc: "cpp", cxx: "cpp",
  cs: "csharp", go: "go", rs: "rust", rb: "ruby", php: "php", kt: "kotlin", kts: "kotlin",
  html: "html", htm: "html", css: "css", scss: "sass", sass: "sass",
  json: "json", jsonl: "json", xml: "xml", yml: "yaml", yaml: "yaml", toml: "toml",
  md: "markdown", markdown: "markdown",
  pdf: "pdf", svg: "svg",
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image", bmp: "image", ico: "image", avif: "image",
  db: "database", sqlite: "database", sql: "database",
  csv: "table", tsv: "table", xlsx: "table", xlsm: "table",
  ps1: "powershell", psm1: "powershell", psd1: "powershell",
  bat: "console", cmd: "console", sh: "console",
  ini: "settings", cfg: "settings", conf: "settings",
  txt: "document",
  zip: "zip", gz: "zip", tgz: "zip", rar: "zip", "7z": "zip",
  ttf: "font", otf: "font", woff: "font", woff2: "font",
  lock: "lock", log: "log", gguf: "tune",
};

const FILE_ICON_BY_NAME = {
  "readme.md": "readme",
  ".gitignore": "git",
  ".gitattributes": "git",
  ".gitkeep": "git",
};

const FOLDER_ICON_BY_NAME = {
  src: "folder-src", app: "folder-app", static: "folder-app",
  assets: "folder-images", images: "folder-images", img: "folder-images",
  scripts: "folder-scripts", script: "folder-scripts",
  node_modules: "folder-node",
  ".venv": "folder-python", venv: "folder-python",
  uploads: "folder-upload",
  ".git": "folder-git",
};

const LANGUAGE_BY_EXT = {
  js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
  ts: "typescript", tsx: "typescript",
  py: "python", pyw: "python",
  java: "java", swift: "swift", m: "objective-c", mm: "objective-c",
  c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp", hh: "cpp",
  cs: "csharp", go: "go", rs: "rust", rb: "ruby", php: "php", kt: "kotlin", kts: "kotlin",
  html: "html", htm: "html", css: "css", scss: "scss", less: "less",
  json: "json", jsonl: "json", xml: "xml", svg: "xml",
  yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", cfg: "ini", conf: "ini",
  md: "markdown", markdown: "markdown",
  sql: "sql", sh: "shell", bash: "shell",
  ps1: "powershell", psm1: "powershell", psd1: "powershell",
  bat: "bat", cmd: "bat", dockerfile: "dockerfile",
};

function extOf(name) {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

function fileIcon(name) {
  const byName = FILE_ICON_BY_NAME[name.toLowerCase()];
  const icon = byName || FILE_ICON_BY_EXT[extOf(name)] || "file";
  return `/static/vendor/icons/${icon}.svg`;
}

function folderIcon(name, open) {
  const base = FOLDER_ICON_BY_NAME[name.toLowerCase()] || "folder";
  return `/static/vendor/icons/${base}${open ? "-open" : ""}.svg`;
}

function languageOf(name) {
  if (name.toLowerCase() === "dockerfile") return "dockerfile";
  return LANGUAGE_BY_EXT[extOf(name)] || "plaintext";
}

function parentOf(path) {
  const index = path.lastIndexOf("/");
  return index >= 0 ? path.slice(0, index) : "";
}

function formatSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Not signed in");
  }
  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.json()).detail;
    } catch (error) {
      detail = response.statusText;
    }
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

async function loadUser() {
  try {
    const data = await api("/api/auth/me");
    const label = document.querySelector("#userLabel");
    if (label) label.textContent = data.user.display_name || data.user.username;
  } catch (error) {
    /* the 401 redirect already handled it */
  }
}

function jsonBody(payload) {
  return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineMarkdown(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,;:!?])/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function renderMarkdownBlock(block) {
  const out = [];
  let list = null;
  let para = [];
  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${para.join("<br>")}</p>`);
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`<${list.type}>${list.items.map((item) => `<li>${item}</li>`).join("")}</${list.type}>`);
      list = null;
    }
  };
  for (const rawLine of block.split("\n")) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushPara();
      flushList();
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      flushPara();
      flushList();
      out.push("<hr>");
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      flushPara();
      if (!list || list.type !== "ul") {
        flushList();
        list = { type: "ul", items: [] };
      }
      list.items.push(inlineMarkdown(bullet[1]));
      continue;
    }
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numbered) {
      flushPara();
      if (!list || list.type !== "ol") {
        flushList();
        list = { type: "ol", items: [] };
      }
      list.items.push(inlineMarkdown(numbered[1]));
      continue;
    }
    flushList();
    para.push(inlineMarkdown(line));
  }
  flushPara();
  flushList();
  return out.join("");
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text || "");
  return escaped
    .split(/```/g)
    .map((block, index) => {
      if (index % 2 === 1) {
        const cleaned = block.replace(/^[a-zA-Z0-9_+\-.#]*\n/, "");
        return `<pre><code>${cleaned}</code></pre>`;
      }
      return renderMarkdownBlock(block);
    })
    .join("");
}

/* ---------- model / status pill ---------- */

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    const model = data.model;
    applyModelStatus(model);
  } catch (error) {
    els.statusLabel.textContent = "Server unavailable";
    els.statusPulse.className = "pulse error";
  }
}

function applyModelStatus(model) {
  state.modelBusy = Boolean(model.busy);
  if (model.busy) {
    els.statusLabel.textContent = "Model answering...";
    els.statusPulse.className = "pulse ready";
  } else if (model.openai_base_url) {
    els.statusLabel.textContent = "Model online";
    els.statusPulse.className = "pulse ready";
  } else if (!model.model_exists) {
    els.statusLabel.textContent = "Model missing";
    els.statusPulse.className = "pulse error";
  } else if (!model.llama_cpp_installed) {
    els.statusLabel.textContent = "Runtime missing";
    els.statusPulse.className = "pulse error";
  } else {
    els.statusLabel.textContent = model.loaded ? "Model loaded" : "Model ready";
    els.statusPulse.className = "pulse ready";
  }
}

/* ---------- workspace ---------- */

async function loadWorkspace() {
  const data = await api("/api/coder/workspace");
  state.workspaceKind = "server";
  state.root = data.root;
  state.rootName = data.root_name;
  state.isOwner = data.is_owner !== false;
  state.canRun = Boolean(data.can_run);
  state.personalRoot = data.personal_root || "";
  state.userSpaces = data.user_spaces || [];
  state.sharedList = data.shared || [];
  els.workspaceName.textContent = data.root ? data.root_name : "Open folder...";
  els.sbWorkspace.textContent = data.root || "";
  renderOpenLists(data);
  renderShareSection();
  updateModeButtons();
  if (data.root) {
    els.welcomeTitle.textContent = "Pick a file from the explorer";
    await renderTreeRoot();
  } else {
    els.tree.innerHTML = `
      <div class="tree-empty">
        No folder is open yet.
        <button type="button">Open folder</button>
      </div>`;
    els.tree.querySelector("button").addEventListener("click", showOpenOverlay);
    showOpenOverlay();
  }
}

function renderOpenLists(data) {
  els.openSuggestions.innerHTML = "";
  (data.suggestions || []).forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `${escapeHtml(item.name)}<small>${escapeHtml(item.path)}</small>`;
    button.addEventListener("click", () => openWorkspace(item.path));
    els.openSuggestions.append(button);
  });
  els.openRecents.innerHTML = "";
  (data.recents || []).forEach((path) => {
    const button = document.createElement("button");
    button.type = "button";
    const name = path.split(/[\\/]/).filter(Boolean).pop() || path;
    button.innerHTML = `${escapeHtml(name)}<small>${escapeHtml(path)}</small>`;
    button.addEventListener("click", () => openWorkspace(path));
    els.openRecents.append(button);
  });
  if (!els.openRecents.children.length) {
    els.openRecents.innerHTML = `<small style="color:var(--muted)">Nothing yet</small>`;
  }
}

function renderShareSection() {
  const section = document.querySelector("#shareSection");
  if (!section) return;
  if (state.workspaceKind === "local") {
    section.innerHTML = `<p class="open-label">Local folder on this device</p>
      <p class="share-note">You are editing files through this browser's folder permission. Saves stay on this
      device. Click Share to copy this folder to the Caraxes server so other users can open it.</p>
      <div class="remote-actions">
        <button id="shareLocalFromDialogBtn" type="button">Share local folder to server</button>
      </div>`;
    section.querySelector("#shareLocalFromDialogBtn")?.addEventListener("click", () => shareLocalFolderToServer(""));
    return;
  }
  if (!state.isOwner) {
    section.innerHTML = `<p class="open-label">Access from this device</p>
      <p class="share-note">Use Open local folder to work directly on files that stay on this device. Use Import
      folder to copy a folder into your server-side My space immediately.</p>
      <div class="remote-actions">
        <button id="openLocalFromDialogBtn" type="button"${localFoldersSupported() ? "" : " disabled"}>Open local folder on this device</button>
        <button id="openMySpaceBtn" type="button"${state.personalRoot ? "" : " disabled"}>Open my space</button>
        <button id="uploadLocalFolderBtn" type="button"${state.personalRoot ? "" : " disabled"}>Import folder from this device</button>
      </div>
      <p class="share-note">Host-shared folders appear in Quick access. Direct live sharing from this PC needs a
      Caraxes server or helper running on this PC too.</p>`;
    section.querySelector("#openLocalFromDialogBtn")?.addEventListener("click", openLocalFolder);
    section.querySelector("#openMySpaceBtn")?.addEventListener("click", () => openWorkspace(state.personalRoot));
    section.querySelector("#uploadLocalFolderBtn")?.addEventListener("click", () => {
      uploadTargetPath = "";
      document.querySelector("#uploadFolderInput")?.click();
    });
    return;
  }
  section.innerHTML = `<p class="open-label">Host folders shared with LAN devices</p>
    <p class="share-note">This shares folders from the Caraxes host PC. Other devices import their own folders
    into My space unless they also run a local helper.</p>`;
  if (state.userSpaces.length) {
    const spacesLabel = document.createElement("p");
    spacesLabel.className = "open-label";
    spacesLabel.textContent = "Imported user spaces";
    section.append(spacesLabel);
    const spaces = document.createElement("div");
    spaces.className = "open-buttons";
    state.userSpaces.forEach((space) => {
      const button = document.createElement("button");
      button.type = "button";
      button.innerHTML = `${escapeHtml(space.name)}<small>${escapeHtml(space.path)}</small>`;
      button.addEventListener("click", () => openWorkspace(space.path));
      spaces.append(button);
    });
    section.append(spaces);
  }
  const list = document.createElement("div");
  list.className = "open-buttons";
  if (!state.sharedList.length) {
    list.innerHTML = `<small class="share-note">Nothing is shared - other devices cannot open any folder.</small>`;
  }
  state.sharedList.forEach((path) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "share-row";
    const name = path.split(/[\\/]/).filter(Boolean).pop() || path;
    row.innerHTML = `${escapeHtml(name)}<small>${escapeHtml(path)}</small><span class="share-remove">Unshare</span>`;
    row.title = "Click to stop sharing this folder";
    row.addEventListener("click", () => toggleShare(path, false));
    list.append(row);
  });
  section.append(list);
  if (state.root && !state.sharedList.includes(state.root)) {
    const shareBtn = document.createElement("button");
    shareBtn.type = "button";
    shareBtn.className = "share-current";
    shareBtn.textContent = `Share "${state.rootName}" with other devices`;
    shareBtn.addEventListener("click", () => toggleShare(state.root, true));
    section.append(shareBtn);
  }
}

async function toggleShare(path, shared) {
  try {
    const result = await api("/api/coder/share", { method: "POST", ...jsonBody({ path, shared }) });
    state.sharedList = result.shared || [];
    renderShareSection();
  } catch (error) {
    window.alert(`Could not update sharing: ${error.message}`);
  }
}

function showOpenOverlay() {
  els.openError.textContent = "";
  els.openCancelBtn.style.display = state.root ? "" : "none";
  els.openOverlay.classList.remove("hidden");
  els.openPathInput.focus();
}

function hideOpenOverlay() {
  els.openOverlay.classList.add("hidden");
}

async function openWorkspace(path) {
  if (state.tabs.some(isDirty) && !window.confirm("You have unsaved changes. Switch folder anyway?")) {
    return false;
  }
  els.openError.textContent = "";
  try {
    await api("/api/coder/workspace", { method: "POST", ...jsonBody({ path }) });
  } catch (error) {
    els.openError.textContent = error.message;
    return false;
  }
  state.workspaceKind = "server";
  state.localRootHandle = null;
  state.localRootName = "";
  closeAllTabs(true);
  state.expandedPaths = new Set();
  hideOpenOverlay();
  await loadWorkspace();
  return true;
}

function localFoldersSupported() {
  return typeof window.showDirectoryPicker === "function";
}

async function openLocalFolder() {
  if (!localFoldersSupported()) {
    window.alert("This browser cannot open local folders directly. Use Chrome or Edge, or use Import folder instead.");
    return false;
  }
  if (state.tabs.some(isDirty) && !window.confirm("You have unsaved changes. Switch folder anyway?")) {
    return false;
  }
  let handle;
  try {
    handle = await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (error) {
    if (error?.name !== "AbortError") window.alert(`Could not open local folder: ${error.message}`);
    return false;
  }
  state.workspaceKind = "local";
  state.localRootHandle = handle;
  state.localRootName = handle.name || "Local folder";
  state.root = `[this device] ${state.localRootName}`;
  state.rootName = state.localRootName;
  closeAllTabs(true);
  state.expandedPaths = new Set();
  hideOpenOverlay();
  els.workspaceName.textContent = `Local: ${state.localRootName}`;
  els.sbWorkspace.textContent = `This device: ${state.localRootName}`;
  els.welcomeTitle.textContent = "Pick a local file from the explorer";
  updateModeButtons();
  renderShareSection();
  await renderTreeRoot();
  return true;
}

function localPathParts(path = "") {
  return String(path || "").split("/").filter((part) => part && part !== "." && part !== "..");
}

async function localDirectoryHandle(path = "", options = {}) {
  if (!state.localRootHandle) throw new Error("No local folder is open");
  let handle = state.localRootHandle;
  for (const part of localPathParts(path)) {
    handle = await handle.getDirectoryHandle(part, { create: Boolean(options.create) });
  }
  return handle;
}

async function localParentHandle(path = "", options = {}) {
  const parts = localPathParts(path);
  const name = parts.pop();
  if (!name) throw new Error("Choose a file or folder inside the workspace");
  return { dir: await localDirectoryHandle(parts.join("/"), options), name };
}

async function localEntryHandle(path = "") {
  if (!path) return state.localRootHandle;
  const { dir, name } = await localParentHandle(path);
  try {
    return await dir.getDirectoryHandle(name);
  } catch (error) {
    return await dir.getFileHandle(name);
  }
}

async function listLocalDir(path = "") {
  const dir = await localDirectoryHandle(path);
  const entries = [];
  for await (const [name, handle] of dir.entries()) {
    entries.push({ name, path: path ? `${path}/${name}` : name, is_dir: handle.kind === "directory" });
  }
  entries.sort((a, b) => Number(!a.is_dir) - Number(!b.is_dir) || a.name.localeCompare(b.name));
  return entries;
}

async function localFileInfo(path) {
  const handle = await localEntryHandle(path);
  if (handle.kind !== "file") throw new Error("Not a file");
  const file = await handle.getFile();
  const base = { path, name: file.name, size: file.size, handle, kind: "text", content: "", language: languageOf(file.name) };
  const ext = extOf(file.name);
  if (["png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "avif", "svg"].includes(ext)) {
    return { ...base, kind: "image", objectUrl: URL.createObjectURL(file) };
  }
  if (ext === "pdf") return { ...base, kind: "pdf", objectUrl: URL.createObjectURL(file) };
  const sample = new Uint8Array(await file.slice(0, 8192).arrayBuffer());
  if (sample.includes(0)) return { ...base, kind: "binary", objectUrl: URL.createObjectURL(file) };
  if (file.size > 4_000_000) return { ...base, kind: "toolarge", objectUrl: URL.createObjectURL(file) };
  return { ...base, content: await file.text() };
}

async function writeLocalFile(path, content, createParents = false) {
  const { dir, name } = await localParentHandle(path, { create: createParents });
  const handle = await dir.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(content);
  await writable.close();
  return handle;
}

async function buildLocalWorkspaceListing(limit = 600) {
  const lines = [];
  async function walk(dirHandle, prefix = "", depth = 0) {
    if (lines.length >= limit || depth > 3) return;
    const items = [];
    for await (const [name, handle] of dirHandle.entries()) {
      if (name.startsWith(".") || ["node_modules", "__pycache__", ".venv", "dist", "build"].includes(name)) continue;
      items.push([name, handle]);
    }
    items.sort((a, b) => Number(a[1].kind !== "directory") - Number(b[1].kind !== "directory") || a[0].localeCompare(b[0]));
    for (const [name, handle] of items) {
      if (lines.length >= limit) break;
      const path = prefix ? `${prefix}/${name}` : name;
      lines.push(handle.kind === "directory" ? `${path}/` : path);
      if (handle.kind === "directory") await walk(handle, path, depth + 1);
    }
  }
  if (state.localRootHandle) await walk(state.localRootHandle);
  return lines.join("\n").slice(0, 80_000);
}

async function collectLocalFiles(dirHandle, prefix, files, limit = 1000) {
  for await (const [name, handle] of dirHandle.entries()) {
    if (files.length >= limit) return;
    const path = prefix ? `${prefix}/${name}` : name;
    if (handle.kind === "directory") {
      await collectLocalFiles(handle, path, files, limit);
    } else {
      files.push({ path, file: await handle.getFile() });
    }
  }
}

async function shareLocalFolderToServer(path = "") {
  if (state.workspaceKind !== "local" || !state.localRootHandle) {
    window.alert("Open a local folder on this device first.");
    return;
  }
  const folderHandle = path ? await localDirectoryHandle(path) : state.localRootHandle;
  const folderName = path ? path.split("/").filter(Boolean).pop() : state.localRootName;
  const files = [];
  await collectLocalFiles(folderHandle, "", files);
  if (!files.length) {
    window.alert("This local folder has no files to share.");
    return;
  }
  if (files.length >= 1000) {
    window.alert("Sharing is capped at 1000 files at a time. Share a smaller folder or zip it first.");
    return;
  }
  const banner = document.createElement("div");
  banner.className = "tree-empty";
  banner.textContent = `Sharing ${files.length} file${files.length === 1 ? "" : "s"} to Caraxes...`;
  els.tree.prepend(banner);
  const form = new FormData();
  for (const item of files) form.append("files", item.file, item.path.replaceAll("\\", "/"));
  try {
    const result = await api(`/api/coder/share-local?folder_name=${encodeURIComponent(folderName || "shared-folder")}`, {
      method: "POST",
      body: form,
    });
    const skipped = result.errors?.length ? ` (${result.errors.length} skipped)` : "";
    window.alert(`Shared ${result.saved.length} file(s) to the server${skipped}.\nHost can open: ${result.relative_root}`);
  } catch (error) {
    window.alert(`Share failed: ${error.message}`);
  } finally {
    banner.remove();
  }
}

/* ---------- explorer tree ---------- */

async function renderTreeRoot() {
  els.tree.innerHTML = "";
  const box = document.createElement("div");
  els.tree.append(box);
  await renderDirInto(box, "", 0);
  markActiveNode();
}

async function renderDirInto(container, dirPath, depth) {
  let entries;
  try {
    entries = state.workspaceKind === "local"
      ? await listLocalDir(dirPath)
      : await api(`/api/coder/tree?path=${encodeURIComponent(dirPath)}`);
  } catch (error) {
    container.innerHTML = `<div class="tree-empty">${escapeHtml(error.message)}</div>`;
    return;
  }
  container.innerHTML = "";
  for (const entry of entries) {
    container.append(buildNode(entry, depth));
    if (entry.is_dir && state.expandedPaths.has(entry.path)) {
      const last = container.lastElementChild;
      await toggleDir(last, entry, depth, true);
    }
  }
}

function buildNode(entry, depth) {
  const wrap = document.createElement("div");
  const node = document.createElement("div");
  node.className = "node";
  node.dataset.path = entry.path;
  node.dataset.dir = entry.is_dir ? "1" : "0";
  node.style.paddingLeft = `${8 + depth * 14}px`;
  if (entry.name.startsWith(".")) node.classList.add("dim");

  const twist = document.createElement("span");
  twist.className = "twist";
  twist.textContent = entry.is_dir ? "▸" : "";
  const icon = document.createElement("img");
  icon.src = entry.is_dir ? folderIcon(entry.name, false) : fileIcon(entry.name);
  icon.alt = "";
  const label = document.createElement("span");
  label.className = "label";
  label.textContent = entry.name;

  node.append(twist, icon, label);
  wrap.append(node);

  if (entry.is_dir) {
    node.addEventListener("click", () => toggleDir(wrap, entry, depth, false));
  } else {
    node.addEventListener("click", () => openFile(entry.path));
  }
  node.addEventListener("contextmenu", (event) => showContextMenu(event, entry));
  return wrap;
}

async function toggleDir(wrap, entry, depth, forceOpen) {
  const node = wrap.querySelector(".node");
  const icon = node.querySelector("img");
  let children = wrap.querySelector(":scope > .children");
  const isOpen = node.classList.contains("expanded");

  if (isOpen && !forceOpen) {
    node.classList.remove("expanded");
    icon.src = folderIcon(entry.name, false);
    state.expandedPaths.delete(entry.path);
    if (children) children.remove();
    return;
  }
  if (node.classList.contains("expanded")) return;

  node.classList.add("expanded");
  icon.src = folderIcon(entry.name, true);
  state.expandedPaths.add(entry.path);
  children = document.createElement("div");
  children.className = "children";
  wrap.append(children);
  await renderDirInto(children, entry.path, depth + 1);
  markActiveNode();
}

function markActiveNode() {
  els.tree.querySelectorAll(".node.active").forEach((node) => node.classList.remove("active"));
  if (!state.activePath) return;
  const active = els.tree.querySelector(`.node[data-path="${CSS.escape(state.activePath)}"]`);
  if (active) active.classList.add("active");
}

/* ---------- context menu / file operations ---------- */

let ctxTarget = null;

function showContextMenu(event, entry) {
  event.preventDefault();
  event.stopPropagation();
  ctxTarget = entry;
  const items = [];
  if (!entry.is_dir) {
    items.push({ label: "Open", action: () => openFile(entry.path) });
    items.push({ label: "Ask AI about this file", action: () => askAboutFile(entry.path) });
    items.push({ hr: true });
  }
  items.push({ label: "Copy path", action: () => copyText(entry.path) });
  items.push({ label: "Copy full path", action: () => copyText(absolutePathOf(entry.path)) });
  if (state.workspaceKind === "local") {
    items.push({ label: entry.is_dir ? "Share this folder to server" : "Download file", action: () => entry.is_dir ? shareLocalFolderToServer(entry.path) : downloadEntry(entry.path) });
  } else {
    items.push({ label: entry.is_dir ? "Download folder (.zip)" : "Download file", action: () => downloadEntry(entry.path) });
  }
  items.push({ hr: true });
  if (entry.is_dir && state.workspaceKind === "server") {
    items.push({
      label: "Upload files here...",
      action: () => {
        uploadTargetPath = entry.path;
        document.querySelector("#uploadFilesInput").click();
      },
    });
  }
  items.push({ label: "New file...", action: () => createEntryPrompt(entry, "file") });
  items.push({ label: "New folder...", action: () => createEntryPrompt(entry, "folder") });
  items.push({ hr: true });
  items.push({ label: "Rename...", action: () => renamePrompt(entry) });
  items.push({ label: "Delete", danger: true, action: () => deleteEntry(entry) });
  renderContextMenu(event.clientX, event.clientY, items);
}

function showTreeBackgroundMenu(event) {
  if (event.target.closest(".node")) return;
  if (!state.root) return;
  event.preventDefault();
  const rootEntry = { path: "", name: state.rootName, is_dir: true };
  const items = state.workspaceKind === "local"
    ? [
      { label: "Share local folder to server", action: () => shareLocalFolderToServer("") },
      { hr: true },
      { label: "New file...", action: () => createEntryPrompt(rootEntry, "file") },
      { label: "New folder...", action: () => createEntryPrompt(rootEntry, "folder") },
      { label: "Refresh", action: renderTreeRoot },
    ]
    : [
    { label: "Download workspace (.zip)", action: () => downloadEntry("") },
    { hr: true },
    { label: "New file...", action: () => createEntryPrompt(rootEntry, "file") },
    { label: "New folder...", action: () => createEntryPrompt(rootEntry, "folder") },
    { label: "Refresh", action: renderTreeRoot },
  ];
  renderContextMenu(event.clientX, event.clientY, items);
}

function renderContextMenu(x, y, items) {
  els.ctxMenu.innerHTML = "";
  items.forEach((item) => {
    if (item.hr) {
      els.ctxMenu.append(document.createElement("hr"));
      return;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.label;
    if (item.danger) button.classList.add("danger");
    button.addEventListener("click", () => {
      hideContextMenu();
      item.action();
    });
    els.ctxMenu.append(button);
  });
  els.ctxMenu.classList.remove("hidden");
  const rect = els.ctxMenu.getBoundingClientRect();
  els.ctxMenu.style.left = `${Math.min(x, window.innerWidth - rect.width - 8)}px`;
  els.ctxMenu.style.top = `${Math.min(y, window.innerHeight - rect.height - 8)}px`;
}

function hideContextMenu() {
  els.ctxMenu.classList.add("hidden");
}

function absolutePathOf(relPath) {
  if (state.workspaceKind === "local") {
    return relPath ? `[this device]/${state.localRootName}/${relPath}` : `[this device]/${state.localRootName}`;
  }
  const root = (state.root || "").replace(/[\\/]+$/, "");
  if (!relPath) return root;
  return `${root}\\${relPath.replaceAll("/", "\\")}`;
}

function downloadEntry(path = "") {
  if (!state.root) {
    window.alert("Open a workspace first.");
    return;
  }
  if (state.workspaceKind === "local") {
    if (!path) {
      window.alert("The folder is already on this device. Use Share to server if you want other users to access it.");
      return;
    }
    localFileInfo(path).then((info) => {
      if (!info.objectUrl && info.kind === "text") {
        const blob = new Blob([info.content], { type: "text/plain" });
        info.objectUrl = URL.createObjectURL(blob);
      }
      if (!info.objectUrl) return;
      const link = document.createElement("a");
      link.href = info.objectUrl;
      link.download = info.name;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(info.objectUrl), 3000);
    }).catch((error) => window.alert(`Download failed: ${error.message}`));
    return;
  }
  const link = document.createElement("a");
  link.href = `/api/coder/download?path=${encodeURIComponent(path || "")}`;
  link.download = "";
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    window.prompt("Copy the path:", text);
  }
}

async function createEntryPrompt(entry, kind) {
  const base = entry.is_dir ? entry.path : parentOf(entry.path);
  const name = window.prompt(kind === "file" ? "New file name:" : "New folder name:");
  if (!name || !name.trim()) return;
  const path = base ? `${base}/${name.trim()}` : name.trim();
  if (state.workspaceKind === "local") {
    try {
      const { dir, name: entryName } = await localParentHandle(path, { create: true });
      if (kind === "folder") {
        await dir.getDirectoryHandle(entryName, { create: true });
      } else {
        const handle = await dir.getFileHandle(entryName, { create: true });
        const writable = await handle.createWritable();
        await writable.write("");
        await writable.close();
      }
      if (base) state.expandedPaths.add(base);
      await renderTreeRoot();
      if (kind === "file") await openFile(path);
    } catch (error) {
      window.alert(`Could not create locally: ${error.message}`);
    }
    return;
  }
  try {
    const created = await api("/api/coder/entry", { method: "POST", ...jsonBody({ path, kind }) });
    if (base) state.expandedPaths.add(base);
    await renderTreeRoot();
    if (kind === "file") await openFile(created.path);
  } catch (error) {
    window.alert(`Could not create: ${error.message}`);
  }
}

async function renamePrompt(entry) {
  if (state.workspaceKind === "local") {
    window.alert("Browser-local folders do not support rename here yet. Rename it in Finder/File Explorer, then refresh.");
    return;
  }
  const name = window.prompt("New name:", entry.name);
  if (!name || name.trim() === entry.name) return;
  try {
    const renamed = await api("/api/coder/rename", { method: "POST", ...jsonBody({ path: entry.path, new_name: name.trim() }) });
    const open = state.tabs.find((tab) => tab.path === entry.path);
    if (open) {
      open.path = renamed.path;
      open.name = renamed.name;
      if (open.path === state.activePath) state.activePath = renamed.path;
    }
    await renderTreeRoot();
    renderTabs();
    updateStatusBar();
  } catch (error) {
    window.alert(`Could not rename: ${error.message}`);
  }
}

/* ---------- uploads (files, folders, drag-and-drop) ---------- */

let uploadTargetPath = "";

async function uploadFileList(targetPath, fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  if (state.workspaceKind === "local") {
    window.alert("This workspace is opened directly on this device. Add files with Finder/File Explorer, then refresh.");
    return;
  }
  if (!state.root) {
    if (!state.personalRoot) {
      window.alert("Open a workspace first, or sign in so Caraxes can create your My space.");
      return;
    }
    const opened = await openWorkspace(state.personalRoot);
    if (!opened || !state.root) return;
  }
  const form = new FormData();
  for (const file of files.slice(0, 1000)) {
    form.append("files", file, (file.webkitRelativePath || file.name).replaceAll("\\", "/"));
  }
  const banner = document.createElement("div");
  banner.className = "tree-empty";
  banner.textContent = `Uploading ${files.length} file${files.length === 1 ? "" : "s"}...`;
  els.tree.prepend(banner);
  try {
    const result = await api(`/api/coder/upload?target=${encodeURIComponent(targetPath || "")}`, {
      method: "POST",
      body: form,
    });
    if (targetPath) state.expandedPaths.add(targetPath);
    await renderTreeRoot();
    if (result.errors?.length) {
      window.alert(
        `Uploaded ${result.saved.length} file(s), but some were skipped:\n${result.errors.slice(0, 6).join("\n")}`
      );
    }
  } catch (error) {
    window.alert(`Upload failed: ${error.message}`);
  } finally {
    banner.remove();
  }
}

async function deleteEntry(entry) {
  const label = entry.is_dir ? `folder "${entry.name}" and everything inside it` : `"${entry.name}"`;
  if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;
  if (state.workspaceKind === "local") {
    try {
      const { dir, name } = await localParentHandle(entry.path);
      await dir.removeEntry(name, { recursive: entry.is_dir });
      state.tabs
        .filter((tab) => tab.path === entry.path || tab.path.startsWith(`${entry.path}/`))
        .forEach((tab) => closeTab(tab.path, true));
      await renderTreeRoot();
    } catch (error) {
      window.alert(`Could not delete locally: ${error.message}`);
    }
    return;
  }
  try {
    await api(`/api/coder/entry?path=${encodeURIComponent(entry.path)}`, { method: "DELETE" });
    state.tabs
      .filter((tab) => tab.path === entry.path || tab.path.startsWith(`${entry.path}/`))
      .forEach((tab) => closeTab(tab.path, true));
    await renderTreeRoot();
  } catch (error) {
    window.alert(`Could not delete: ${error.message}`);
  }
}

/* ---------- tabs and editor ---------- */

function activeTab() {
  return state.tabs.find((tab) => tab.path === state.activePath) || null;
}

async function openFile(path) {
  const existing = state.tabs.find((tab) => tab.path === path);
  if (existing) {
    activateTab(path);
    return;
  }
  let info;
  try {
    info = state.workspaceKind === "local"
      ? await localFileInfo(path)
      : await api(`/api/coder/file?path=${encodeURIComponent(path)}`);
  } catch (error) {
    window.alert(`Could not open file: ${error.message}`);
    return;
  }
  const tab = {
    path: info.path,
    name: info.name,
    kind: info.kind,
    size: info.size,
    lastEdit: info.last_edit || null,
    model: null,
    objectUrl: info.objectUrl || null,
    source: state.workspaceKind,
    viewState: null,
    savedVersionId: null,
    language: languageOf(info.name),
  };
  if (info.kind === "text") {
    tab.model = monaco.editor.createModel(info.content, tab.language);
    tab.savedVersionId = tab.model.getAlternativeVersionId();
    tab.model.onDidChangeContent(() => {
      renderTabs();
      updateStatusBar();
      scheduleLint();
    });
  }
  state.tabs.push(tab);
  activateTab(tab.path);
}

function activateTab(path) {
  const current = activeTab();
  if (current && current.model && state.editor.getModel() === current.model) {
    current.viewState = state.editor.saveViewState();
  }
  state.activePath = path;
  const tab = activeTab();
  renderTabs();
  markActiveNode();

  els.welcome.style.display = "none";
  if (tab.kind === "text") {
    els.previewHost.style.display = "none";
    els.previewHost.className = "preview-host";
    els.monacoHost.style.display = "block";
    state.editor.setModel(tab.model);
    if (tab.viewState) state.editor.restoreViewState(tab.viewState);
    state.editor.focus();
  } else {
    els.monacoHost.style.display = "none";
    renderPreview(tab);
  }
  updateStatusBar();
  renderAiContext();
  scheduleLint();
  updateProblemsBadge();
}

function renderPreview(tab) {
  const raw = tab.source === "local" && tab.objectUrl
    ? tab.objectUrl
    : `/api/coder/raw?path=${encodeURIComponent(tab.path)}`;
  els.previewHost.style.display = "block";
  els.previewHost.className = "preview-host";
  if (tab.kind === "image") {
    els.previewHost.classList.add("image-mode");
    els.previewHost.innerHTML = `<img src="${raw}" alt="${escapeHtml(tab.name)}" />`;
  } else if (tab.kind === "pdf") {
    els.previewHost.classList.add("pdf-mode");
    els.previewHost.innerHTML = `<embed src="${raw}" type="application/pdf" />`;
  } else {
    const reason = tab.kind === "toolarge" ? "This file is too large for the editor." : "This is a binary file.";
    els.previewHost.innerHTML = `
      <div class="binary-note">
        <strong>${escapeHtml(tab.name)}</strong>
        <span>${reason} ${escapeHtml(formatSize(tab.size))}</span>
        <span><a href="${raw}" download style="color:var(--teal)">Download</a></span>
      </div>`;
  }
}

function isDirty(tab) {
  return Boolean(tab.model && tab.savedVersionId !== tab.model.getAlternativeVersionId());
}

function renderTabs() {
  els.tabs.innerHTML = "";
  state.tabs.forEach((tab) => {
    const node = document.createElement("div");
    node.className = `tab${tab.path === state.activePath ? " active" : ""}${isDirty(tab) ? " dirty" : ""}`;
    node.title = tab.path;
    node.innerHTML = `
      <img src="${fileIcon(tab.name)}" alt="" />
      <span class="tab-name">${escapeHtml(tab.name)}</span>
      <button class="close" type="button" aria-label="Close tab"><span class="dot"></span><span class="x">&times;</span></button>
    `;
    node.addEventListener("click", () => activateTab(tab.path));
    node.addEventListener("auxclick", (event) => {
      if (event.button === 1) closeTab(tab.path);
    });
    node.querySelector(".close").addEventListener("click", (event) => {
      event.stopPropagation();
      closeTab(tab.path);
    });
    els.tabs.append(node);
  });
}

function closeTab(path, force = false) {
  const index = state.tabs.findIndex((tab) => tab.path === path);
  if (index < 0) return;
  const tab = state.tabs[index];
  if (!force && isDirty(tab) && !window.confirm(`"${tab.name}" has unsaved changes. Close anyway?`)) {
    return;
  }
  if (tab.model) tab.model.dispose();
  if (tab.objectUrl) URL.revokeObjectURL(tab.objectUrl);
  state.tabs.splice(index, 1);
  if (state.activePath === path) {
    const next = state.tabs[index] || state.tabs[index - 1];
    if (next) {
      state.activePath = null;
      activateTab(next.path);
      return;
    }
    state.activePath = null;
    state.editor.setModel(null);
    els.monacoHost.style.display = "none";
    els.previewHost.style.display = "none";
    els.welcome.style.display = "grid";
  }
  renderTabs();
  markActiveNode();
  updateStatusBar();
  renderAiContext();
}

function closeAllTabs(force = false) {
  [...state.tabs.map((tab) => tab.path)].forEach((path) => closeTab(path, force));
}

async function saveActiveTab() {
  const tab = activeTab();
  if (!tab || tab.kind !== "text" || !isDirty(tab)) return;
  try {
    if (tab.source === "local" || state.workspaceKind === "local") {
      await writeLocalFile(tab.path, tab.model.getValue(), true);
    } else {
      await api("/api/coder/file", { method: "PUT", ...jsonBody({ path: tab.path, content: tab.model.getValue() }) });
    }
    tab.savedVersionId = tab.model.getAlternativeVersionId();
    renderTabs();
    updateStatusBar();
  } catch (error) {
    window.alert(`Could not save: ${error.message}`);
  }
}

/* ---------- status bar ---------- */

function updateStatusBar() {
  const tab = activeTab();
  els.sbFile.textContent = tab ? tab.path : "";
  els.sbLanguage.textContent = tab && tab.kind === "text" ? tab.language : tab ? tab.kind : "";
  const lastEditEl = document.querySelector("#sbLastEdit");
  if (lastEditEl) {
    lastEditEl.textContent = tab?.lastEdit
      ? `Last edit: ${tab.lastEdit.username} · ${new Date(tab.lastEdit.created_at).toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        })}`
      : "";
  }
  if (tab && tab.kind === "text") {
    els.sbDirty.textContent = isDirty(tab) ? "● Unsaved (Ctrl+S)" : "Saved";
    els.sbDirty.classList.toggle("dirty", isDirty(tab));
  } else {
    els.sbDirty.textContent = "";
    els.sbDirty.classList.remove("dirty");
  }
}

/* ---------- syntax checking ---------- */

const LINTABLE_LANGUAGES = new Set(["python", "json"]);
let lintTimer = null;
let lintSeq = 0;

function scheduleLint() {
  const tab = activeTab();
  if (!tab || tab.kind !== "text") return;
  window.clearTimeout(lintTimer);
  lintTimer = window.setTimeout(() => runLint(tab), 600);
}

async function runLint(tab) {
  if (!tab.model || tab.model.isDisposed()) return;
  if (!LINTABLE_LANGUAGES.has(tab.language)) return;
  const seq = ++lintSeq;
  try {
    const result = await api("/api/coder/lint", {
      method: "POST",
      ...jsonBody({ language: tab.language, content: tab.model.getValue() }),
    });
    if (seq !== lintSeq || tab.model.isDisposed()) return;
    const markers = (result.markers || []).map((marker) => ({
      severity: marker.severity === "warning" ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
      message: marker.message,
      startLineNumber: marker.line,
      startColumn: marker.column,
      endLineNumber: marker.endLine || marker.line,
      endColumn: marker.endColumn || marker.column + 1,
    }));
    monaco.editor.setModelMarkers(tab.model, "caraxes-lint", markers);
    updateProblemsBadge();
  } catch (error) {
    /* linting must never break editing */
  }
}

function updateProblemsBadge() {
  const tab = activeTab();
  if (!tab || !tab.model) {
    els.sbProblems.textContent = "";
    els.sbProblems.classList.remove("has-problems");
    return;
  }
  const markers = monaco.editor
    .getModelMarkers({ resource: tab.model.uri })
    .filter((marker) => marker.severity >= monaco.MarkerSeverity.Warning);
  if (!markers.length) {
    els.sbProblems.textContent = "No problems";
    els.sbProblems.classList.remove("has-problems");
  } else {
    els.sbProblems.textContent = `⚠ ${markers.length} problem${markers.length === 1 ? "" : "s"}`;
    els.sbProblems.classList.add("has-problems");
    els.sbProblems.title = markers.map((m) => `Ln ${m.startLineNumber}: ${m.message}`).join("\n");
  }
}

function updateCursorPosition() {
  const position = state.editor.getPosition();
  const tab = activeTab();
  if (position && tab && tab.kind === "text") {
    els.sbPosition.textContent = `Ln ${position.lineNumber}, Col ${position.column}`;
  } else {
    els.sbPosition.textContent = "";
  }
}

/* ---------- AI panel ---------- */

function currentSelectionText() {
  const tab = activeTab();
  if (!tab || tab.kind !== "text") return "";
  const selection = state.editor.getSelection();
  if (!selection || selection.isEmpty()) return "";
  return tab.model.getValueInRange(selection);
}

function renderAiContext() {
  const tab = activeTab();
  els.aiContext.innerHTML = "";
  if (tab && tab.kind === "text") {
    const chip = document.createElement("span");
    chip.className = `ctx-chip${state.includeFile ? "" : " off"}`;
    chip.title = "Click to include or exclude the open file from the prompt";
    chip.innerHTML = `<img src="${fileIcon(tab.name)}" alt="" />${escapeHtml(tab.name)}`;
    chip.addEventListener("click", () => {
      state.includeFile = !state.includeFile;
      renderAiContext();
    });
    els.aiContext.append(chip);
  }
  const selection = currentSelectionText();
  if (selection) {
    const lines = selection.split("\n").length;
    const chip = document.createElement("span");
    chip.className = "ctx-chip";
    chip.textContent = `Selection: ${lines} line${lines === 1 ? "" : "s"}`;
    els.aiContext.append(chip);
  }
  if (state.mode === "edit" && (!tab || tab.kind !== "text")) {
    const chip = document.createElement("span");
    chip.className = "ctx-chip";
    chip.textContent = "Can create files from prompt";
    els.aiContext.append(chip);
  }
}

function updateModeButtons() {
  const autoBtn = document.querySelector("#modeAutoBtn");
  if (autoBtn) {
    autoBtn.title = state.workspaceKind === "local"
      ? "Local browser folders can be edited, but commands only run in server workspaces"
      : state.canRun
      ? "The model edits files AND runs PowerShell commands automatically"
      : "Auto mode applies files automatically; commands run only on the host machine";
  }
  if (els.openLocalFolderBtn) {
    els.openLocalFolderBtn.disabled = !localFoldersSupported();
  }
  if (els.shareLocalFolderBtn) {
    els.shareLocalFolderBtn.disabled = state.workspaceKind !== "local";
  }
  if (els.localActionOpenBtn) {
    els.localActionOpenBtn.disabled = !localFoldersSupported();
    els.localActionOpenBtn.textContent = state.workspaceKind === "local" ? "Switch local folder" : "Open local folder";
  }
  if (els.localActionShareBtn) {
    els.localActionShareBtn.disabled = state.workspaceKind !== "local";
    els.localActionShareBtn.textContent = state.workspaceKind === "local" ? "Share to server" : "Open local first";
  }
  if (els.downloadWorkspaceBtn) {
    els.downloadWorkspaceBtn.disabled = !state.root || state.workspaceKind === "local";
  }
}

function setMode(mode) {
  state.mode = mode;
  els.modeAskBtn.classList.toggle("active", mode === "ask");
  els.modeEditBtn.classList.toggle("active", mode === "edit");
  const autoBtn = document.querySelector("#modeAutoBtn");
  if (autoBtn) autoBtn.classList.toggle("active", mode === "auto");
  els.aiInput.placeholder =
    mode === "edit"
      ? "Create files or describe changes to apply..."
      : mode === "auto"
        ? "Describe the task - I will edit files and run commands..."
        : "Ask Caraxes about your code...";
  renderAiContext();
}

function appendAiMessage(role, contentHtml) {
  const empty = els.aiMessages.querySelector(".ai-empty");
  if (empty) empty.remove();
  const node = document.createElement("div");
  node.className = `ai-msg ${role}`;
  node.innerHTML = `<div class="who">${role === "user" ? "You" : "Caraxes"}</div><div class="body">${contentHtml}</div>`;
  els.aiMessages.append(node);
  els.aiMessages.scrollTop = els.aiMessages.scrollHeight;
  return node;
}

function appendThinking() {
  const queued = state.modelBusy;
  const node = appendAiMessage("assistant", `
    <div class="thinking-row">
      <span class="spark"></span>
      <small>${queued
        ? "The model is answering another request - yours is queued and will start automatically..."
        : "Generating locally..."}</small>
    </div>`);
  node.classList.add("thinking");
  return node;
}

function decorateCodeBlocks(node, emphasizeApply) {
  node.querySelectorAll("pre").forEach((pre) => {
    const code = pre.querySelector("code")?.textContent ?? "";
    const bar = document.createElement("div");
    bar.className = "code-actions";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(code);
      copyBtn.textContent = "Copied";
      setTimeout(() => (copyBtn.textContent = "Copy"), 1200);
    });

    const insertBtn = document.createElement("button");
    insertBtn.type = "button";
    insertBtn.textContent = "Insert at cursor";
    insertBtn.addEventListener("click", () => applyCode(code, false));

    const replaceBtn = document.createElement("button");
    replaceBtn.type = "button";
    replaceBtn.textContent = emphasizeApply ? "Apply to editor" : "Replace file content";
    if (emphasizeApply) replaceBtn.classList.add("primary");
    replaceBtn.addEventListener("click", () => applyCode(code, true));

    bar.append(copyBtn, insertBtn, replaceBtn);
    pre.after(bar);
  });
}

/* Multi-file replies: the model marks files with "### FILE: path" + one fenced block,
   and commands with "### RUN" + one fenced block. */
const FILE_BLOCK_RE = /#{2,4}\s*FILE:\s*([^\n`]+?)\s*\n+```[a-zA-Z0-9_+\-.#]*\n([\s\S]*?)```/g;
const ACTION_BLOCK_RE = /#{2,4}\s*(FILE|RUN)\b\s*:?\s*([^\n`]*?)\s*\n+```[a-zA-Z0-9_+\-.#]*\n([\s\S]*?)```/g;

function normalizeRelPath(raw) {
  return raw
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "")
    .replaceAll("\\", "/")
    .replace(/^\.?\//, "")
    .replace(/^\/+/, "");
}

function parseAssistantReply(text) {
  const segments = [];
  let last = 0;
  for (const match of text.matchAll(ACTION_BLOCK_RE)) {
    if (match.index > last) segments.push({ kind: "text", text: text.slice(last, match.index) });
    if (match[1].toUpperCase() === "RUN") {
      segments.push({ kind: "run", command: match[3].trim() });
    } else {
      segments.push({ kind: "file", path: normalizeRelPath(match[2]), code: match[3] });
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

function buildFileCard(segment, appliedInfo = null) {
  const card = document.createElement("div");
  card.className = "file-card";
  const name = segment.path.split("/").pop() || segment.path;
  card.innerHTML = `
    <div class="file-card-head">
      <img src="${fileIcon(name)}" alt="" />
      <span class="file-card-path" title="${escapeHtml(segment.path)}">${escapeHtml(segment.path)}</span>
    </div>
    <pre><code>${escapeHtml(segment.code)}</code></pre>
    <div class="code-actions"></div>`;
  const actions = card.querySelector(".code-actions");

  const applyBtn = document.createElement("button");
  applyBtn.type = "button";
  applyBtn.className = "primary";
  if (appliedInfo?.ok) {
    applyBtn.textContent = appliedInfo.created ? "Created" : "Saved";
    applyBtn.disabled = true;
  } else if (appliedInfo && !appliedInfo.ok) {
    applyBtn.textContent = "Save failed";
    applyBtn.title = appliedInfo.error || "Could not save this file";
  } else {
    applyBtn.textContent = `Apply to ${name}`;
    applyBtn.addEventListener("click", () => applyFileBlock(segment.path, segment.code, applyBtn));
  }

  const openBtn = document.createElement("button");
  openBtn.type = "button";
  openBtn.textContent = "Open file";
  openBtn.addEventListener("click", () => openFile(segment.path));

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.textContent = "Copy";
  copyBtn.addEventListener("click", async () => {
    await copyText(segment.code);
    copyBtn.textContent = "Copied";
    setTimeout(() => (copyBtn.textContent = "Copy"), 1200);
  });

  actions.append(applyBtn, openBtn, copyBtn);
  return card;
}

function buildRunCard(segment) {
  const card = document.createElement("div");
  card.className = "run-card";
  card.innerHTML = `
    <div class="file-card-head">
      <img src="/static/vendor/icons/powershell.svg" alt="" />
      <span class="file-card-path">PowerShell - runs in the workspace folder</span>
    </div>
    <pre><code>${escapeHtml(segment.command)}</code></pre>
    <div class="code-actions"></div>
    <div class="run-output"></div>`;
  const actions = card.querySelector(".code-actions");

  const runBtn = document.createElement("button");
  runBtn.type = "button";
  runBtn.className = "primary run-btn";
  if (!state.canRun) {
    runBtn.textContent = "Run (host machine only)";
    runBtn.disabled = true;
    runBtn.title = "Commands can only be executed from the host machine";
  } else {
    runBtn.textContent = "Run command";
    runBtn.addEventListener("click", () => executeRunCard(segment, card, runBtn));
  }

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.textContent = "Copy";
  copyBtn.addEventListener("click", async () => {
    await copyText(segment.command);
    copyBtn.textContent = "Copied";
    setTimeout(() => (copyBtn.textContent = "Copy"), 1200);
  });

  actions.append(runBtn, copyBtn);
  return card;
}

async function executeRunCard(segment, card, button) {
  const output = card.querySelector(".run-output");
  if (button) {
    button.disabled = true;
    button.textContent = "Running...";
  }
  output.innerHTML = `<div class="thinking-row"><span class="spark"></span><small>Running in the workspace...</small></div>`;
  try {
    const result = await api("/api/coder/run", {
      method: "POST",
      ...jsonBody({ command: segment.command, shell: "powershell" }),
    });
    const ok = !result.timed_out && result.exit_code === 0;
    const text = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    output.innerHTML = `
      <div class="run-exit ${ok ? "ok" : "bad"}">${result.timed_out ? "Timed out" : `exit ${result.exit_code}`} · ${(result.duration_ms / 1000).toFixed(1)}s</div>
      <pre><code>${escapeHtml(text || "[no output]")}</code></pre>`;
    if (button) {
      button.textContent = ok ? "Ran ✓" : "Run again";
      button.disabled = ok;
    }
    state.aiHistory.push({
      role: "user",
      content:
        `[Command executed in the workspace]\n${segment.command}\n` +
        `Exit: ${result.timed_out ? "timeout" : result.exit_code}\nOutput:\n${(text || "[no output]").slice(0, 4000)}`,
    });
    await renderTreeRoot();
    return result;
  } catch (error) {
    output.innerHTML = `<div class="run-exit bad">failed</div><pre><code>${escapeHtml(error.message)}</code></pre>`;
    if (button) {
      button.disabled = false;
      button.textContent = "Run command";
    }
    return null;
  }
}

async function applyFileBlock(path, code, button) {
  if (state.workspaceKind === "local") {
    try {
      await writeLocalFile(path, code, true);
      const tab = state.tabs.find((item) => item.path === path);
      if (tab && tab.model) {
        if (tab.model.getValue() !== code) {
          tab.model.pushEditOperations([], [{ range: tab.model.getFullModelRange(), text: code }], () => null);
        }
        tab.savedVersionId = tab.model.getAlternativeVersionId();
        renderTabs();
        updateStatusBar();
      }
      await renderTreeRoot();
      if (button) {
        button.textContent = "Saved locally";
        button.disabled = true;
      }
      return true;
    } catch (error) {
      window.alert(`Could not write local file ${path}: ${error.message}`);
      return false;
    }
  }
  try {
    const result = await api("/api/coder/file", {
      method: "PUT",
      ...jsonBody({ path, content: code, create_parents: true }),
    });
    const tab = state.tabs.find((item) => item.path === path);
    if (tab && tab.model) {
      if (tab.model.getValue() !== code) {
        tab.model.pushEditOperations([], [{ range: tab.model.getFullModelRange(), text: code }], () => null);
      }
      tab.savedVersionId = tab.model.getAlternativeVersionId();
      renderTabs();
      updateStatusBar();
    }
    await renderTreeRoot();
    if (button) {
      button.textContent = result.created ? "Created" : "Saved";
      button.disabled = true;
    }
    return true;
  } catch (error) {
    window.alert(`Could not write ${path}: ${error.message}`);
    return false;
  }
}

function syncAppliedFileTabs(reply, appliedFiles) {
  const okPaths = new Set((appliedFiles || []).filter((item) => item.ok).map((item) => normalizeRelPath(item.path)));
  if (!okPaths.size) return;
  const codeByPath = new Map(
    parseAssistantReply(reply)
      .filter((segment) => segment.kind === "file")
      .map((segment) => [segment.path, segment.code])
  );
  for (const path of okPaths) {
    const tab = state.tabs.find((item) => item.path === path);
    const code = codeByPath.get(path);
    if (tab?.model && code != null) {
      if (tab.model.getValue() !== code) {
        tab.model.pushEditOperations([], [{ range: tab.model.getFullModelRange(), text: code }], () => null);
      }
      tab.savedVersionId = tab.model.getAlternativeVersionId();
    }
  }
  renderTabs();
  updateStatusBar();
  renderTreeRoot();
}

function appendResearchSources(body, sources = []) {
  if (!sources.length) return;
  const wrap = document.createElement("div");
  wrap.className = "research-sources";
  const title = document.createElement("div");
  title.className = "research-sources-title";
  title.textContent = "Sources searched";
  wrap.append(title);
  sources.slice(0, 8).forEach((source) => {
    if (!source.url) return;
    const link = document.createElement("a");
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `${source.kind === "github" ? "GitHub" : "Web"}: ${source.name || source.url}`;
    wrap.append(link);
  });
  body.append(wrap);
}

function renderAssistantMessage(reply, appliedFiles = [], researchSources = []) {
  const node = appendAiMessage("assistant", "");
  const body = node.querySelector(".body");
  body.innerHTML = "";
  const fileBlocks = [];
  const runCards = [];
  const appliedByPath = new Map((appliedFiles || []).map((item) => [normalizeRelPath(item.path), item]));
  parseAssistantReply(reply).forEach((segment) => {
    if (segment.kind === "text") {
      if (!segment.text.trim()) return;
      const div = document.createElement("div");
      div.innerHTML = renderMarkdown(segment.text);
      decorateCodeBlocks(div, state.mode !== "ask" && !reply.match(FILE_BLOCK_RE));
      body.append(div);
    } else if (segment.kind === "run") {
      const card = buildRunCard(segment);
      body.append(card);
      runCards.push({ segment, card });
    } else {
      body.append(buildFileCard(segment, appliedByPath.get(segment.path)));
      fileBlocks.push(segment);
    }
  });
  if (state.workspaceKind === "server" && state.mode === "auto" && state.canRun && runCards.length) {
    (async () => {
      for (const item of runCards) {
        await executeRunCard(item.segment, item.card, item.card.querySelector(".run-btn"));
      }
    })();
  }
  const fenceCount = (reply.match(/```/g) || []).length;
  if (fenceCount % 2 === 1) {
    const warn = document.createElement("div");
    warn.className = "auto-save-note error";
    warn.textContent =
      "This reply hit the token limit and was cut off mid-code-block. The incomplete block was NOT saved - " +
      'reply "continue" to finish it, or ask for a shorter version.';
    body.append(warn);
  }
  const savedCount = (appliedFiles || []).filter((item) => item.ok).length;
  const failedCount = (appliedFiles || []).filter((item) => !item.ok).length;
  if (savedCount || failedCount) {
    const note = document.createElement("div");
    note.className = `auto-save-note${failedCount ? " error" : ""}`;
    note.textContent = failedCount
      ? `Auto-save finished with ${failedCount} error${failedCount === 1 ? "" : "s"}.`
      : `Auto-saved ${savedCount} file${savedCount === 1 ? "" : "s"} to the workspace.`;
    body.append(note);
  }
  const unappliedBlocks = fileBlocks.filter((segment) => !appliedByPath.get(segment.path)?.ok);
  if (unappliedBlocks.length > 1) {
    const bar = document.createElement("div");
    bar.className = "code-actions";
    const allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "primary";
    allBtn.textContent = `Apply all ${unappliedBlocks.length} files`;
    allBtn.addEventListener("click", async () => {
      let ok = true;
      for (const segment of unappliedBlocks) {
        ok = (await applyFileBlock(segment.path, segment.code, null)) && ok;
      }
      if (ok) {
        allBtn.textContent = "All applied";
        allBtn.disabled = true;
      }
    });
    bar.append(allBtn);
    body.append(bar);
  }
  appendResearchSources(body, researchSources);
  els.aiMessages.scrollTop = els.aiMessages.scrollHeight;
  return node;
}

function applyCode(code, replaceWholeFile) {
  const tab = activeTab();
  if (!tab || tab.kind !== "text") {
    window.alert("Open a text file first, then apply the code.");
    return;
  }
  const model = tab.model;
  if (replaceWholeFile) {
    state.editor.pushUndoStop();
    state.editor.executeEdits("caraxes-ai", [{ range: model.getFullModelRange(), text: code }]);
    state.editor.pushUndoStop();
  } else {
    const selection = state.editor.getSelection();
    state.editor.executeEdits("caraxes-ai", [{ range: selection, text: code }]);
  }
  state.editor.focus();
  renderTabs();
  updateStatusBar();
}

function askAboutFile(path) {
  openFile(path).then(() => {
    state.includeFile = true;
    els.shell.classList.remove("ai-hidden");
    renderAiContext();
    els.aiInput.value = "Explain what this file does and point out any problems.";
    els.aiInput.focus();
  });
}

async function sendAi(event) {
  event.preventDefault();
  if (state.aiBusy) return;
  const prompt = els.aiInput.value.trim();
  if (!prompt) return;

  const tab = activeTab();
  const payload = {
    prompt,
    history: state.aiHistory.slice(-12),
    mode: state.mode === "ask" ? "ask" : "edit",
    client_workspace: state.workspaceKind,
    can_run: state.workspaceKind === "server" && state.mode === "auto" && state.canRun,
    temperature: 0.4,
    max_tokens: state.mode === "ask" ? 1600 : 3072,
  };
  if (state.workspaceKind === "local") {
    payload.workspace_listing = await buildLocalWorkspaceListing();
  }
  if (tab && tab.kind === "text" && state.includeFile) {
    payload.file_path = tab.path;
    payload.file_content = tab.model.getValue();
    payload.language = tab.language;
  }
  const selection = currentSelectionText();
  if (selection) payload.selection = selection;

  appendAiMessage("user", renderMarkdown(prompt));
  state.aiHistory.push({ role: "user", content: prompt });
  els.aiInput.value = "";
  els.aiInput.style.height = "auto";
  state.aiBusy = true;
  els.aiSendBtn.disabled = true;
  const thinking = appendThinking();

  try {
    const result = await api("/api/coder/chat", { method: "POST", ...jsonBody(payload) });
    thinking.remove();
    renderAssistantMessage(result.reply, result.applied_files || [], result.research_sources || []);
    syncAppliedFileTabs(result.reply, result.applied_files || []);
    state.aiHistory.push({ role: "assistant", content: result.reply });
    if (result.model_status) applyModelStatus(result.model_status);
  } catch (error) {
    thinking.remove();
    appendAiMessage("assistant", renderMarkdown(`Request failed: ${error.message}`));
  } finally {
    state.aiBusy = false;
    els.aiSendBtn.disabled = false;
    els.aiMessages.scrollTop = els.aiMessages.scrollHeight;
  }
}

/* ---------- layout: resizers and AI toggle ---------- */

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function setupResizers() {
  // Defaults scale with the screen so the layout looks the same on any monitor.
  const defaultExplorer = Math.round(window.innerWidth * 0.15);
  const defaultAi = Math.round(window.innerWidth * 0.24);
  const explorerWidth = clamp(Number(localStorage.getItem("caraxes.coder.explorerWidth") || defaultExplorer), 200, 560);
  const aiWidth = clamp(Number(localStorage.getItem("caraxes.coder.aiWidth") || defaultAi), 300, 760);
  document.documentElement.style.setProperty("--explorer-width", `${explorerWidth}px`);
  document.documentElement.style.setProperty("--ai-width", `${aiWidth}px`);
  if (localStorage.getItem("caraxes.coder.aiHidden") === "true") {
    els.shell.classList.add("ai-hidden");
  }

  let dragging = null;
  const stop = () => {
    dragging = null;
    document.body.classList.remove("resizing");
  };
  window.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    if (dragging === "explorer") {
      const width = clamp(event.clientX, 200, 560);
      document.documentElement.style.setProperty("--explorer-width", `${width}px`);
      localStorage.setItem("caraxes.coder.explorerWidth", String(width));
    } else {
      const width = clamp(window.innerWidth - event.clientX, 300, 760);
      document.documentElement.style.setProperty("--ai-width", `${width}px`);
      localStorage.setItem("caraxes.coder.aiWidth", String(width));
    }
  });
  window.addEventListener("pointerup", stop);
  window.addEventListener("pointercancel", stop);
  els.explorerResizer.addEventListener("pointerdown", (event) => {
    dragging = "explorer";
    document.body.classList.add("resizing");
    event.preventDefault();
  });
  els.aiResizer.addEventListener("pointerdown", (event) => {
    dragging = "ai";
    document.body.classList.add("resizing");
    event.preventDefault();
  });

  els.toggleAiBtn.addEventListener("click", () => {
    const hidden = els.shell.classList.toggle("ai-hidden");
    localStorage.setItem("caraxes.coder.aiHidden", String(hidden));
  });

  const logoutBtn = document.querySelector("#logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
  }
}

/* ---------- boot ---------- */

function setupEvents() {
  els.workspaceBtn.addEventListener("click", showOpenOverlay);
  els.openCancelBtn.addEventListener("click", hideOpenOverlay);
  els.openForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const path = els.openPathInput.value.trim();
    if (path) openWorkspace(path);
  });
  els.refreshBtn.addEventListener("click", renderTreeRoot);
  els.newFileBtn.addEventListener("click", () => {
    if (state.root) createEntryPrompt({ path: "", name: state.rootName, is_dir: true }, "file");
  });
  els.newFolderBtn.addEventListener("click", () => {
    if (state.root) createEntryPrompt({ path: "", name: state.rootName, is_dir: true }, "folder");
  });
  els.openLocalFolderBtn.addEventListener("click", openLocalFolder);
  els.shareLocalFolderBtn.addEventListener("click", () => shareLocalFolderToServer(""));
  els.localActionOpenBtn.addEventListener("click", openLocalFolder);
  els.localActionShareBtn.addEventListener("click", () => shareLocalFolderToServer(""));
  els.downloadWorkspaceBtn.addEventListener("click", () => downloadEntry(""));
  els.tree.addEventListener("contextmenu", showTreeBackgroundMenu);

  const uploadFilesInput = document.querySelector("#uploadFilesInput");
  const uploadFolderInput = document.querySelector("#uploadFolderInput");
  document.querySelector("#uploadFilesBtn").addEventListener("click", () => {
    if (!state.root) return;
    uploadTargetPath = "";
    uploadFilesInput.click();
  });
  document.querySelector("#uploadFolderBtn").addEventListener("click", () => {
    if (!state.root) return;
    uploadTargetPath = "";
    uploadFolderInput.click();
  });
  uploadFilesInput.addEventListener("change", () => {
    uploadFileList(uploadTargetPath, uploadFilesInput.files);
    uploadFilesInput.value = "";
  });
  uploadFolderInput.addEventListener("change", () => {
    uploadFileList(uploadTargetPath, uploadFolderInput.files);
    uploadFolderInput.value = "";
  });
  els.tree.addEventListener("dragover", (event) => {
    if (!state.root) return;
    event.preventDefault();
  });
  els.tree.addEventListener("drop", (event) => {
    if (!state.root) return;
    event.preventDefault();
    const node = event.target.closest ? event.target.closest(".node") : null;
    const target = node && node.dataset.dir === "1" ? node.dataset.path : "";
    if (event.dataTransfer?.files?.length) uploadFileList(target, event.dataTransfer.files);
  });

  window.addEventListener("click", hideContextMenu);
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideContextMenu();
      if (state.root) hideOpenOverlay();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveActiveTab();
    }
  });

  els.modeAskBtn.addEventListener("click", () => setMode("ask"));
  els.modeEditBtn.addEventListener("click", () => setMode("edit"));
  const autoBtn = document.querySelector("#modeAutoBtn");
  if (autoBtn) autoBtn.addEventListener("click", () => setMode("auto"));
  els.aiComposer.addEventListener("submit", sendAi);
  els.aiInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.aiComposer.requestSubmit();
    }
  });
  els.aiInput.addEventListener("input", () => {
    els.aiInput.style.height = "auto";
    els.aiInput.style.height = `${Math.min(160, els.aiInput.scrollHeight)}px`;
  });

  window.addEventListener("beforeunload", (event) => {
    if (state.tabs.some(isDirty)) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
}

require.config({ paths: { vs: "/static/vendor/monaco/vs" } });
require(["vs/editor/editor.main"], () => {
  monaco.editor.defineTheme("caraxes", {
    base: "vs-dark",
    inherit: true,
    rules: [],
    colors: {
      "editor.background": "#121118",
      "editor.lineHighlightBackground": "#1a1822",
      "editorLineNumber.foreground": "#5c5560",
      "editorLineNumber.activeForeground": "#eeb85f",
      "editorCursor.foreground": "#ff5d2e",
      "editor.selectionBackground": "#3d2a2244",
      "editorIndentGuide.background1": "#232029",
    },
  });
  state.editor = monaco.editor.create(els.monacoHost, {
    model: null,
    theme: "caraxes",
    automaticLayout: true,
    fontSize: 13.5,
    fontFamily: '"Cascadia Code", Consolas, "Liberation Mono", monospace',
    minimap: { enabled: true, scale: 1 },
    scrollBeyondLastLine: false,
    renderWhitespace: "selection",
    smoothScrolling: true,
    tabSize: 4,
  });
  state.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveActiveTab);
  state.editor.onDidChangeCursorPosition(updateCursorPosition);
  state.editor.onDidChangeCursorSelection(() => renderAiContext());
  monaco.editor.onDidChangeMarkers(() => updateProblemsBadge());

  ensureSession();
  setupResizers();
  setupEvents();
  setMode("ask");
  loadUser();
  refreshStatus();
  window.setInterval(refreshStatus, 10000);
  loadWorkspace().catch((error) => {
    els.tree.innerHTML = `<div class="tree-empty">${escapeHtml(error.message)}</div>`;
  });
});
