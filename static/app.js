const state = {
  chats: [],
  currentChatId: null,
  attachments: [],
  busy: false,
  uploading: false,
  thinkingNode: null,
  thinkingTimer: null,
  thinkingStartedAt: 0,
};

const els = {
  appShell: document.querySelector("#appShell"),
  chatList: document.querySelector("#chatList"),
  newChatBtn: document.querySelector("#newChatBtn"),
  chatTitle: document.querySelector("#chatTitle"),
  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  messageInput: document.querySelector("#messageInput"),
  fileInput: document.querySelector("#fileInput"),
  attachmentTray: document.querySelector("#attachmentTray"),
  sendBtn: document.querySelector("#sendBtn"),
  statusTitle: document.querySelector("#statusTitle"),
  statusText: document.querySelector("#statusText"),
  pulse: document.querySelector(".pulse"),
  taskMode: document.querySelector("#taskMode"),
  temperature: document.querySelector("#temperature"),
  maxTokens: document.querySelector("#maxTokens"),
  sidebarToggle: document.querySelector("#sidebarToggle"),
  sidebarResizer: document.querySelector("#sidebarResizer"),
  scrollBottomBtn: document.querySelector("#scrollBottomBtn"),
};

const thinkingPhases = [
  [0, "Preparing prompt", "Packing chat history and selected file parts"],
  [4, "Reading context", "The model is looking through the attached context"],
  [10, "Generating locally", "Still working on this machine"],
  [30, "Long reply running", "Large prompts can take a bit; the server is still waiting"],
  [60, "Still generating", "The backend has not returned yet"],
];

const queuedThinkingPhases = [
  [0, "Queued behind another request", "The local model answers one request at a time; yours starts automatically"],
  [20, "Still waiting in the queue", "The other request is taking a while; yours is next"],
  [60, "Working through the queue", "The backend has not returned yet"],
];

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Not signed in");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

async function loadUser() {
  const row = document.querySelector("#userRow");
  if (!row) return;
  try {
    const data = await api("/api/auth/me");
    const name = data.user.display_name || data.user.username;
    row.innerHTML = `
      <span class="user-name" title="Signed in as ${escapeHtml(data.user.username)}">${escapeHtml(name)}</span>
      <a href="/activity" title="Who did what">Activity</a>
      <a href="/login" title="Sign in or create another local account">Switch</a>
      <button id="logoutBtn" type="button" title="Log out">Log out</button>`;
    row.querySelector("#logoutBtn").addEventListener("click", async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
  } catch (error) {
    /* the 401 redirect already handled it */
  }
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

function isNearBottom() {
  return els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 180;
}

function scrollToBottom(force = false) {
  if (force || isNearBottom()) {
    els.messages.scrollTop = els.messages.scrollHeight;
  }
  updateScrollButton();
}

function updateScrollButton() {
  const show = els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight > 260;
  els.scrollBottomBtn.classList.toggle("visible", show);
}

function statusCopy(model) {
  if (model.busy) {
    return ["Model answering...", "one request runs at a time; new ones wait in line"];
  }
  if (model.openai_base_url) {
    return ["External backend", model.openai_base_url];
  }
  if (!model.model_exists) {
    return ["Model missing", "Run scripts\\download_model.ps1"];
  }
  if (!model.llama_cpp_installed) {
    return ["Runtime missing", "Install requirements-llm.txt"];
  }
  if (model.loaded) {
    return ["Model loaded", `${model.model_size_gb} GB - ctx ${model.n_ctx}`];
  }
  return ["Ready to load", `${model.model_size_gb} GB - first reply may take a moment`];
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    state.modelBusy = Boolean(data.model.busy);
    const [title, text] = statusCopy(data.model);
    els.statusTitle.textContent = title;
    els.statusText.textContent = text;
    els.pulse.classList.toggle("ready", data.model.model_exists && data.model.llama_cpp_installed);
    els.pulse.classList.toggle("error", !data.model.model_exists || !data.model.llama_cpp_installed);
  } catch (error) {
    els.statusTitle.textContent = "Server unavailable";
    els.statusText.textContent = error.message;
    els.pulse.classList.add("error");
  }
}

function renderChatList() {
  els.chatList.innerHTML = "";
  state.chats.forEach((chat) => {
    const button = document.createElement("button");
    button.className = `chat-item${chat.id === state.currentChatId ? " active" : ""}`;
    button.type = "button";
    button.textContent = chat.title || "New chat";
    button.addEventListener("click", () => loadChat(chat.id));
    els.chatList.append(button);
  });
}

function renderEmpty() {
  els.messages.innerHTML = `
    <div class="empty-state">
      <img src="/static/assets/caraxes-dragon-v2.png" alt="" />
      <div>
        <p class="eyebrow">Ask, inspect, revise</p>
        <h3>Drop code, PDFs, spreadsheets, or screenshots into the chat.</h3>
        <p>Caraxes keeps your history here and runs from this machine once the GGUF is installed.</p>
      </div>
    </div>
  `;
  updateScrollButton();
}

function createMessageNode(message, extraClass = "") {
  const node = document.createElement("article");
  node.className = `message ${message.role}${extraClass ? ` ${extraClass}` : ""}`;
  const attachments = message.attachments?.length
    ? `<div class="attachments">${message.attachments
        .map((item) => {
          const label = item.kind === "web" || item.kind === "github"
            ? `${item.kind === "github" ? "GitHub" : "Web"}: ${item.name || item.url || "source"}`
            : item.name || item.original_name || "file";
          if (item.url) {
            return `<a class="chip source-chip" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
          }
          return `<span class="chip">${escapeHtml(label)}</span>`;
        })
        .join("")}</div>`
    : "";
  node.innerHTML = `
    <div class="role">${escapeHtml(message.role)}</div>
    <div class="bubble">${renderMarkdown(message.content)}${attachments}</div>
  `;
  return node;
}

function appendMessage(message, options = {}) {
  const node = createMessageNode(message);
  els.messages.append(node);
  scrollToBottom(options.forceScroll ?? true);
  return node;
}

function renderMessages(messages) {
  els.messages.innerHTML = "";
  if (!messages.length) {
    renderEmpty();
    return;
  }
  messages.forEach((message) => appendMessage(message, { forceScroll: false }));
  scrollToBottom(true);
}

function updateThinkingMessage() {
  if (!state.thinkingNode) return;
  const elapsed = Math.floor((Date.now() - state.thinkingStartedAt) / 1000);
  const phases = state.thinkingQueued ? queuedThinkingPhases : thinkingPhases;
  const phase = phases.reduce((current, candidate) => (elapsed >= candidate[0] ? candidate : current));
  const title = state.thinkingNode.querySelector(".thinking-title");
  const detail = state.thinkingNode.querySelector(".thinking-detail");
  if (title) title.textContent = `${phase[1]} - ${elapsed}s`;
  if (detail) detail.textContent = phase[2];
}

function appendThinkingMessage() {
  clearThinkingMessage();
  state.thinkingStartedAt = Date.now();
  state.thinkingQueued = state.modelBusy;
  const firstPhase = state.thinkingQueued ? queuedThinkingPhases[0] : thinkingPhases[0];
  const node = document.createElement("article");
  node.className = "message assistant thinking";
  node.innerHTML = `
    <div class="role">assistant</div>
    <div class="bubble">
      <div class="thinking-row">
        <span class="spark"></span>
        <span class="thinking-copy">
          <strong class="thinking-title">${firstPhase[1]} - 0s</strong>
          <small class="thinking-detail">${firstPhase[2]}</small>
        </span>
      </div>
    </div>
  `;
  state.thinkingNode = node;
  els.messages.append(node);
  state.thinkingTimer = window.setInterval(updateThinkingMessage, 1000);
  scrollToBottom(true);
}

function clearThinkingMessage() {
  if (state.thinkingTimer) {
    window.clearInterval(state.thinkingTimer);
    state.thinkingTimer = null;
  }
  if (state.thinkingNode?.isConnected) {
    state.thinkingNode.remove();
  }
  state.thinkingNode = null;
}

function replaceThinkingMessage(message) {
  if (state.thinkingTimer) {
    window.clearInterval(state.thinkingTimer);
    state.thinkingTimer = null;
  }
  const replacement = createMessageNode(message);
  if (state.thinkingNode?.isConnected) {
    state.thinkingNode.replaceWith(replacement);
  } else {
    els.messages.append(replacement);
  }
  state.thinkingNode = null;
  scrollToBottom(true);
}

async function refreshChats() {
  state.chats = await api("/api/chats");
  renderChatList();
}

async function newChat() {
  const chat = await api("/api/chats", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New chat" }),
  });
  state.currentChatId = chat.id;
  await refreshChats();
  await loadChat(chat.id);
}

async function loadChat(chatId) {
  const chat = await api(`/api/chats/${chatId}`);
  state.currentChatId = chat.id;
  els.chatTitle.textContent = chat.title || "New chat";
  clearThinkingMessage();
  renderMessages(chat.messages || []);
  renderChatList();
}

function renderAttachments() {
  els.attachmentTray.innerHTML = "";
  if (state.uploading) {
    const loading = document.createElement("span");
    loading.className = "attachment-chip";
    loading.textContent = "Reading files...";
    els.attachmentTray.append(loading);
  }
  state.attachments.forEach((file) => {
    const parts = file.meta?.chunk_count > 1 ? ` - ${file.meta.chunk_count} parts` : "";
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    chip.innerHTML = `${escapeHtml(file.original_name)}${escapeHtml(parts)} <button type="button" aria-label="Remove">x</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      state.attachments = state.attachments.filter((item) => item.id !== file.id);
      renderAttachments();
    });
    els.attachmentTray.append(chip);
  });
}

async function uploadSelectedFiles() {
  const files = Array.from(els.fileInput.files || []);
  if (!files.length) return;
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  els.fileInput.value = "";
  state.uploading = true;
  renderAttachments();
  try {
    const uploaded = await api("/api/files", { method: "POST", body: form });
    state.attachments.push(...uploaded);
  } catch (error) {
    appendMessage({ role: "assistant", content: `File upload failed: ${error.message}`, attachments: [] });
  } finally {
    state.uploading = false;
    renderAttachments();
  }
}

function setBusy(value) {
  state.busy = value;
  els.sendBtn.disabled = value;
  els.sendBtn.textContent = value ? "Thinking" : "Send";
}

async function sendMessage(event) {
  event.preventDefault();
  if (state.busy) return;
  if (!state.currentChatId) {
    await newChat();
  }
  const content = els.messageInput.value.trim();
  const attachmentIds = state.attachments.map((item) => item.id);
  if (!content && !attachmentIds.length) return;

  const localUserMessage = {
    role: "user",
    content: content || "[Attached files]",
    attachments: state.attachments.map((item) => ({ name: item.original_name })),
  };
  if (els.messages.querySelector(".empty-state")) {
    els.messages.innerHTML = "";
  }
  appendMessage(localUserMessage);
  els.messageInput.value = "";
  els.messageInput.style.height = "auto";
  state.attachments = [];
  renderAttachments();
  setBusy(true);
  appendThinkingMessage();

  try {
    const result = await api(`/api/chats/${state.currentChatId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        attachment_ids: attachmentIds,
        mode: els.taskMode.value || "auto",
        temperature: Number(els.temperature.value || 0.7),
        max_tokens: Number(els.maxTokens.value || 900),
      }),
    });
    replaceThinkingMessage(result.assistant_message);
    await refreshChats();
    const chat = state.chats.find((item) => item.id === state.currentChatId);
    if (chat) els.chatTitle.textContent = chat.title;
    await refreshStatus();
  } catch (error) {
    replaceThinkingMessage({ role: "assistant", content: `Request failed: ${error.message}`, attachments: [] });
  } finally {
    setBusy(false);
  }
}

function autoGrow() {
  els.messageInput.style.height = "auto";
  els.messageInput.style.height = `${Math.min(180, els.messageInput.scrollHeight)}px`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function applySidebarState() {
  const savedWidth = Number(localStorage.getItem("caraxes.sidebarWidth") || 320);
  const width = clamp(savedWidth, 240, 560);
  const collapsed = localStorage.getItem("caraxes.sidebarCollapsed") === "true";
  document.documentElement.style.setProperty("--sidebar-width", `${width}px`);
  els.appShell.classList.toggle("sidebar-collapsed", collapsed);
  els.sidebarToggle.textContent = collapsed ? ">>" : "<<";
  els.sidebarToggle.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
  els.sidebarToggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
}

function setupSidebarControls() {
  applySidebarState();
  els.sidebarToggle.addEventListener("click", () => {
    const collapsed = !els.appShell.classList.contains("sidebar-collapsed");
    localStorage.setItem("caraxes.sidebarCollapsed", String(collapsed));
    applySidebarState();
  });

  let resizing = false;
  const stopResize = () => {
    resizing = false;
    document.body.classList.remove("resizing-sidebar");
  };
  const resize = (event) => {
    if (!resizing) return;
    const width = clamp(event.clientX, 240, 560);
    localStorage.setItem("caraxes.sidebarCollapsed", "false");
    localStorage.setItem("caraxes.sidebarWidth", String(width));
    document.documentElement.style.setProperty("--sidebar-width", `${width}px`);
    els.appShell.classList.remove("sidebar-collapsed");
    els.sidebarToggle.textContent = "<<";
  };

  els.sidebarResizer.addEventListener("pointerdown", (event) => {
    resizing = true;
    document.body.classList.add("resizing-sidebar");
    event.preventDefault();
  });
  window.addEventListener("pointermove", resize);
  window.addEventListener("pointerup", stopResize);
  window.addEventListener("pointercancel", stopResize);
}

async function boot() {
  setupSidebarControls();
  els.newChatBtn.addEventListener("click", newChat);
  els.composer.addEventListener("submit", sendMessage);
  els.fileInput.addEventListener("change", uploadSelectedFiles);
  els.messageInput.addEventListener("input", autoGrow);
  els.messages.addEventListener("scroll", updateScrollButton);
  els.scrollBottomBtn.addEventListener("click", () => scrollToBottom(true));
  els.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.composer.requestSubmit();
    }
  });

  await loadUser();
  await refreshStatus();
  await refreshChats();
  if (state.chats.length) {
    await loadChat(state.chats[0].id);
  } else {
    renderEmpty();
  }
  window.setInterval(refreshStatus, 10000);
}

boot().catch((error) => {
  els.statusTitle.textContent = "Boot failed";
  els.statusText.textContent = error.message;
  els.pulse.classList.add("error");
});
