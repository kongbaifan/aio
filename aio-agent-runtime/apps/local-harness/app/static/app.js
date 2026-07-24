const state = {
  token: localStorage.getItem("harnessToken") || "",
  sessionId: null,
  mode: localStorage.getItem("agentMode") || "single",
  // 当前选中模型：provider/model，优先来自 localStorage，随后被 /api/models 默认值校正
  provider: localStorage.getItem("harnessProvider") || "",
  model: localStorage.getItem("harnessModelId") || "",
  models: [],
  path: ".",
  busy: false,
  events: [],
  health: null,
  currentFile: null,
  controller: null,
  commandIndex: 0,
};

const elements = {};

// 所有 API 请求统一经过这里，确保 token、取消信号和错误格式一致。
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers["X-Harness-Token"] = state.token;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return response;
}

function showToast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.setAttribute("role", error ? "alert" : "status");
  elements.toast.classList.add("visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => elements.toast.classList.remove("visible"), 2800);
}

function formatBytes(size = 0) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.7 } });
}

let markedReady = false;
function ensureMarkedConfigured() {
  if (markedReady || !window.marked) return markedReady;
  // GFM + 换行敏感；高亮在渲染后由 highlight.js 后处理（marked@14 已移除 highlight 选项）。
  window.marked.setOptions({ gfm: true, breaks: true });
  markedReady = true;
  return true;
}

// 把 Markdown 文本渲染进容器；解析或净化不可用时安全回退为纯文本。
function renderMarkdownInto(container, text) {
  const raw = text == null ? "" : String(text);
  if (!window.marked || !window.DOMPurify) {
    container.textContent = raw;
    return;
  }
  ensureMarkedConfigured();
  try {
    const html = window.marked.parse(raw);
    container.innerHTML = window.DOMPurify.sanitize(html);
    // 链接统一新开标签页，避免在工作台内跳走。
    container.querySelectorAll("a[href]").forEach(anchor => {
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
    });
    // 代码块高亮：净化后逐个交给 highlight.js。
    if (window.hljs) {
      container.querySelectorAll("pre code").forEach(block => {
        try {
          window.hljs.highlightElement(block);
        } catch (_) {
          // 高亮失败保留纯代码文本
        }
      });
    }
  } catch (_) {
    container.textContent = raw;
  }
}

function setText(element, value) {
  if (element) element.textContent = value;
}

function updateRuntimeState(kind, label) {
  elements.runtimeState.className = `runtime-state ${kind}`;
  elements.runtimeState.querySelector("span:last-child").textContent = label;
  elements.sidebarRuntime.className = `sidebar-runtime ${kind}`;
  elements.sidebarRuntimeLabel.textContent = label;
}

function modelLabelText(provider = state.provider, model = state.model) {
  const found = state.models.find(item => item.provider === provider && item.id === model);
  if (found?.name) return `${found.name}`;
  return `${provider}/${model}`;
}

function setSelectedModel(provider, model, { persist = true, syncSelect = true } = {}) {
  if (!provider || !model) return;
  state.provider = provider;
  state.model = model;
  if (persist) {
    localStorage.setItem("harnessProvider", provider);
    localStorage.setItem("harnessModelId", model);
  }
  setText(elements.modelLabel, modelLabelText(provider, model));
  setText(elements.settingsModel, modelLabelText(provider, model));
  if (syncSelect && elements.modelSelect) {
    const value = `${provider}/${model}`;
    if ([...elements.modelSelect.options].some(option => option.value === value)) {
      elements.modelSelect.value = value;
    }
  }
}

function renderModelSelect() {
  if (!elements.modelSelect) return;
  const previous = `${state.provider}/${state.model}`;
  elements.modelSelect.replaceChildren();
  if (!state.models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "未配置模型";
    option.disabled = true;
    elements.modelSelect.append(option);
    return;
  }
  // 按 provider 分组展示
  const groups = new Map();
  for (const item of state.models) {
    if (!groups.has(item.provider)) groups.set(item.provider, []);
    groups.get(item.provider).push(item);
  }
  for (const [provider, items] of groups) {
    const group = document.createElement("optgroup");
    group.label = provider;
    for (const item of items) {
      const option = document.createElement("option");
      option.value = `${item.provider}/${item.id}`;
      option.textContent = item.available
        ? (item.name || item.id)
        : `${item.name || item.id}（未配置密钥）`;
      option.disabled = !item.available;
      group.append(option);
    }
    elements.modelSelect.append(group);
  }
  if ([...elements.modelSelect.options].some(option => option.value === previous && !option.disabled)) {
    elements.modelSelect.value = previous;
  } else {
    const firstAvailable = state.models.find(item => item.available) || state.models[0];
    if (firstAvailable) {
      setSelectedModel(firstAvailable.provider, firstAvailable.id, { persist: true, syncSelect: true });
    }
  }
}

async function loadModels() {
  try {
    const data = await (await api("/api/models")).json();
    state.models = data.models || [];
    const saved = `${state.provider}/${state.model}`;
    const savedOk = state.models.some(
      item => item.provider === state.provider && item.id === state.model && item.available,
    );
    if (!savedOk && data.default?.provider && data.default?.model) {
      const def = state.models.find(
        item => item.provider === data.default.provider && item.id === data.default.model && item.available,
      );
      if (def) setSelectedModel(def.provider, def.id, { persist: true, syncSelect: false });
      else {
        const first = state.models.find(item => item.available) || state.models[0];
        if (first) setSelectedModel(first.provider, first.id, { persist: true, syncSelect: false });
      }
    } else if (savedOk) {
      setSelectedModel(state.provider, state.model, { persist: false, syncSelect: false });
    }
    renderModelSelect();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadHealth() {
  try {
    const data = await (await api("/api/health")).json();
    state.health = data;
    const sandboxOnline = data.sandbox?.status === "ok";
    updateRuntimeState(sandboxOnline ? "online" : "warning", sandboxOnline ? "运行时在线" : "Sandbox 离线");
    setText(elements.modelLabel, modelLabelText());
    setText(elements.settingsModel, modelLabelText());
    setText(elements.settingsHarness, "已连接");
    elements.settingsHarness.className = "status-badge success";
    setText(elements.settingsSandbox, sandboxOnline ? "在线" : "离线");
    elements.settingsSandbox.className = `status-badge ${sandboxOnline ? "success" : "warning"}`;
    setText(elements.settingsTools, `${data.tools?.length || 0} 个`);
    renderMcp(data.mcp);
  } catch (error) {
    updateRuntimeState("error", "Harness 离线");
    setText(elements.settingsHarness, "离线");
    elements.settingsHarness.className = "status-badge error";
    showToast(error.message, true);
  }
}

function renderMcp(mcp) {
  const info = mcp || {
    status: "optional",
    name: "AIO Local Harness",
    transport: "stdio",
    tools: ["list_files", "read_file", "write_file", "execute_python"],
  };
  setText(elements.mcpServerName, info.name || "AIO Local Harness");
  setText(elements.mcpDescription, `${info.transport || "stdio"} · 可选本地入口`);
  setText(elements.mcpStatus, info.status === "running" ? "已连接" : "可用");
  elements.mcpStatus.className = `status-badge ${info.status === "running" ? "success" : "warning"}`;
  elements.mcpTools.replaceChildren();
  for (const tool of info.tools || []) {
    const chip = document.createElement("code");
    chip.className = "tool-chip";
    chip.textContent = tool;
    elements.mcpTools.append(chip);
  }
}

function addMessage(role, content, isError = false) {
  elements.emptyState.hidden = true;
  const article = document.createElement("article");
  article.className = `message ${role} ${isError ? "error" : ""}`;
  const label = role === "user" ? "你" : "AIO Agent";
  const icon = role === "user" ? "user" : "sparkles";
  article.innerHTML = `
    <div class="message-head">
      <span class="message-avatar"><i data-lucide="${icon}" aria-hidden="true"></i></span>
      <span class="message-role"></span>
      <time></time>
    </div>
    <div class="message-body"></div>`;
  article.querySelector(".message-role").textContent = label;
  article.querySelector("time").textContent = formatTime();
  const body = article.querySelector(".message-body");
  // 仅对 Agent 的正常回答渲染 Markdown；用户输入与错误信息保持纯文本，避免注入与误渲染。
  if (role === "assistant" && !isError) {
    body.classList.add("markdown");
    renderMarkdownInto(body, content);
  } else {
    body.textContent = content;
  }
  elements.chatMessages.append(article);
  refreshIcons();
  scrollChatToEnd();
}

// 创建一个空的 Agent 消息气泡，返回可持续追加文本的 handle（打字机效果）。
// 每次 push 累积全文并重渲染 Markdown；finalize 时做最终一次渲染。
function beginStreamingMessage() {
  elements.emptyState.hidden = true;
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = `
    <div class="message-head">
      <span class="message-avatar"><i data-lucide="sparkles" aria-hidden="true"></i></span>
      <span class="message-role"></span>
      <time></time>
    </div>
    <div class="message-body markdown streaming"></div>`;
  article.querySelector(".message-role").textContent = "AIO Agent";
  article.querySelector("time").textContent = formatTime();
  const body = article.querySelector(".message-body");
  elements.chatMessages.append(article);
  refreshIcons();
  scrollChatToEnd();
  let text = "";
  let raf = 0;
  const paint = () => {
    raf = 0;
    renderMarkdownInto(body, text);
    scrollChatToEnd();
  };
  return {
    push(piece) {
      text += piece;
      // 用 rAF 合批，避免每个 token 都触发一次 Markdown 解析。
      if (!raf) raf = requestAnimationFrame(paint);
    },
    finalize() {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      body.classList.remove("streaming");
      renderMarkdownInto(body, text);
      scrollChatToEnd();
    },
    get text() { return text; },
  };
}

function eventIcon(event) {
  if (event.status === "error") return "circle-alert";
  if (event.status === "running") return "loader-circle";
  if (event.type === "plan") return "list-tree";
  if (event.type === "result") return "check";
  return "wrench";
}

function eventStatusLabel(status) {
  if (status === "success") return "完成";
  if (status === "error") return "失败";
  return "执行中";
}

// 尽量把 JSON 字符串美化成多行；不是 JSON 时原样返回。
function prettyDetail(text) {
  const raw = text == null ? "" : String(text);
  const trimmed = raw.trim();
  if (!trimmed || (trimmed[0] !== "{" && trimmed[0] !== "[")) return raw;
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch (_) {
    return raw;
  }
}

// 一行事件的「摘要 + 展开详情」。running 行展开显示调用参数，
// success/error/blocked 行展开显示返回结果，都用可换行的 <pre>。
function buildActivityRow(event) {
  const row = document.createElement("article");
  row.className = `activity-event ${event.status}`;

  const isRunning = event.status === "running";
  const args = event.payload?.arguments;
  const hasArgs = args && Object.keys(args).length > 0;
  // running：优先展示参数；其他：展示返回 detail。
  const detailText = isRunning
    ? (hasArgs ? prettyDetail(JSON.stringify(args)) : "")
    : prettyDetail(event.detail);
  // 摘要行的副标题：running 显示「调用参数」，其余显示状态说明。
  const subtitle = isRunning
    ? (hasArgs ? "查看调用参数" : "模型请求执行工具")
    : (detailText ? "查看返回结果" : "没有附加信息");

  const details = document.createElement("details");
  details.className = "activity-event-detail";
  // 默认折叠；失败的默认展开，方便第一眼看到错误。
  details.open = event.status === "error";

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span class="event-icon"><i data-lucide="${eventIcon(event)}" aria-hidden="true"></i></span>
    <span class="event-copy"><strong></strong><span></span></span>
    <span class="event-status"></span>`;
  summary.querySelector("strong").textContent = event.name;
  summary.querySelector(".event-copy span").textContent = subtitle;
  summary.querySelector(".event-status").textContent = eventStatusLabel(event.status);
  details.append(summary);

  if (detailText) {
    const pre = document.createElement("pre");
    pre.className = "event-detail-body";
    pre.textContent = detailText;
    details.append(pre);
  } else {
    // 无可展开内容时禁用交互，避免点了没反应。
    summary.style.cursor = "default";
    details.addEventListener("toggle", () => { details.open = false; });
  }

  row.append(details);
  return row;
}

function addActivityGroup(events) {
  if (!events?.length) return;
  const hasError = events.some(event => event.status === "error");
  const hasRunning = events.some(event => event.status === "running");
  const status = hasError ? "error" : hasRunning ? "warning" : "success";
  const group = document.createElement("section");
  group.className = "activity-group";
  const details = document.createElement("details");
  details.open = hasError || events.length <= 2;
  details.innerHTML = `
    <summary>
      <i data-lucide="chevron-right" aria-hidden="true"></i>
      <strong>执行了 ${events.length} 个步骤</strong>
      <span class="activity-state ${status}">${hasError ? "包含失败" : hasRunning ? "执行中" : "已完成"}</span>
    </summary>
    <div class="activity-events"></div>`;
  const list = details.querySelector(".activity-events");
  for (const event of events) list.append(buildActivityRow(event));
  group.append(details);
  elements.chatMessages.append(group);
  refreshIcons();
  scrollChatToEnd();
}

// 流式活动组：先建壳，事件逐条到达时追加行，结束时定稿标题与状态。
function beginActivityGroup() {
  const group = document.createElement("section");
  group.className = "activity-group";
  const details = document.createElement("details");
  details.open = true;
  details.innerHTML = `
    <summary>
      <i data-lucide="chevron-right" aria-hidden="true"></i>
      <strong>执行中…</strong>
      <span class="activity-state warning">执行中</span>
    </summary>
    <div class="activity-events"></div>`;
  group.append(details);
  elements.chatMessages.append(group);
  refreshIcons();
  scrollChatToEnd();
  return {
    group,
    list: details.querySelector(".activity-events"),
    summaryTitle: details.querySelector("summary strong"),
    state: details.querySelector(".activity-state"),
    details,
    count: 0,
  };
}

function pushActivityEvent(handle, event) {
  if (!handle) return;
  handle.list.append(buildActivityRow(event));
  handle.count += 1;
  refreshIcons();
  scrollChatToEnd();
}

function finalizeActivityGroup(handle, events) {
  if (!handle) return;
  if (!handle.count) {
    handle.group.remove();
    return;
  }
  const hasError = events.some(event => event.status === "error");
  const status = hasError ? "error" : "success";
  handle.summaryTitle.textContent = `执行了 ${handle.count} 个步骤`;
  handle.state.className = `activity-state ${status}`;
  handle.state.textContent = hasError ? "包含失败" : "已完成";
  handle.details.open = hasError || handle.count <= 2;
  refreshIcons();
}

function scrollChatToEnd() {
  requestAnimationFrame(() => { elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight; });
}

function setBusy(busy) {
  state.busy = busy;
  elements.sendButton.classList.toggle("running", busy);
  elements.sendButton.title = busy ? "停止任务" : "发送任务";
  elements.sendButton.setAttribute("aria-label", busy ? "停止任务" : "发送任务");
  elements.sendButton.innerHTML = `<i data-lucide="${busy ? "square" : "arrow-up"}" aria-hidden="true"></i>`;
  if (busy) updateRuntimeState("running", "Agent 执行中");
  else if (state.health) {
    const online = state.health.sandbox?.status === "ok";
    updateRuntimeState(online ? "online" : "warning", online ? "运行时在线" : "Sandbox 离线");
  }
  refreshIcons();
}

function stopRequest() {
  if (!state.controller) return;
  state.controller.abort();
  state.controller = null;
}

// 逐帧解析 SSE：把 reader 里的字节流按空行拆成 data 帧，解析出 JSON 后交给 onFrame。
async function readSse(response, onFrame) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 帧之间以空行分隔；正则同时兼容 \n\n 和 \r\n\r\n。
    const separator = /\r?\n\r?\n/;
    let match;
    while ((match = separator.exec(buffer)) !== null) {
      const rawFrame = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const line = rawFrame.split(/\r?\n/).find(item => item.startsWith("data:"));
      if (!line) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        onFrame(JSON.parse(payload));
      } catch (_) {
        // 半帧或非 JSON 心跳直接跳过
      }
    }
  }
}

async function sendMessage(message) {
  const value = message.trim();
  if (!value || state.busy) return;
  addMessage("user", value);
  elements.messageInput.value = "";
  resizeComposer();
  setBusy(true);
  state.controller = new AbortController();
  // 本轮的流式活动组与新增事件，收尾时并入 state.events。
  let group = null;
  const roundEvents = [];
  let answered = false;
  // 最终答案的流式气泡：第一个 delta 到达时懒创建。
  let stream = null;
  try {
    const response = await api("/api/chat/stream", {
      method: "POST",
      body: JSON.stringify({
        message: value,
        session_id: state.sessionId,
        mode: state.mode,
        provider: state.provider,
        model: state.model,
      }),
      signal: state.controller.signal,
    });
    await readSse(response, frame => {
      if (frame.kind === "start") {
        if (frame.session_id) state.sessionId = frame.session_id;
        if (frame.matched?.length) showToast(`已匹配 ${frame.matched.length} 个 Skill`);
      } else if (frame.kind === "event") {
        const event = frame.event;
        if (!event) return;
        roundEvents.push(event);
        if (!group) group = beginActivityGroup();
        pushActivityEvent(group, event);
      } else if (frame.kind === "delta") {
        // 最终答案的文本增量：逐段追加到流式气泡（打字机）。
        if (group) finalizeActivityGroup(group);
        if (!stream) stream = beginStreamingMessage();
        stream.append(frame.text || "");
        answered = true;
      } else if (frame.kind === "answer") {
        // 非流式兜底：只有当没走过 delta 时才整段渲染，避免与打字机重复。
        if (group) finalizeActivityGroup(group);
        if (!stream) {
          addMessage("assistant", frame.answer);
          answered = true;
        }
      } else if (frame.kind === "done") {
        if (frame.provider && frame.model) {
          setSelectedModel(frame.provider, frame.model, { persist: true, syncSelect: true });
        }
        renderFiles(frame.files || [], ".");
      } else if (frame.kind === "error") {
        if (stream) { stream.finalize(); stream = null; }
        addMessage("assistant", frame.detail, true);
        showToast(frame.detail, true);
        answered = true;
      }
    });
    if (stream) stream.finalize();
    if (group) finalizeActivityGroup(group);
    state.events = [...state.events, ...roundEvents];
    renderTrace();
    await loadSessions();
  } catch (error) {
    if (group) finalizeActivityGroup(group);
    state.events = [...state.events, ...roundEvents];
    if (error.name === "AbortError") {
      const event = { type: "error", name: "任务已停止", status: "error", detail: "用户取消了本次请求", timestamp: new Date().toISOString() };
      state.events.push(event);
      addActivityGroup([event]);
      renderTrace();
      showToast("任务已停止");
    } else {
      if (!answered) addMessage("assistant", error.message, true);
      showToast(error.message, true);
    }
  } finally {
    state.controller = null;
    setBusy(false);
    elements.messageInput.focus();
  }
}

async function loadSessions() {
  try {
    const data = await (await api("/api/sessions")).json();
    elements.sessionList.replaceChildren();
    if (!data.sessions.length) {
      elements.sessionList.innerHTML = '<p class="sidebar-empty">还没有会话</p>';
      return;
    }
    for (const session of data.sessions) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `session-item ${session.id === state.sessionId ? "active" : ""}`;
      button.title = session.title;
      button.innerHTML = `<i data-lucide="message-square" aria-hidden="true"></i><span class="session-copy"><span class="session-title"></span><span class="session-meta"></span></span>`;
      button.querySelector(".session-title").textContent = session.title;
      button.querySelector(".session-meta").textContent = `${session.message_count} 条消息`;
      button.addEventListener("click", () => selectSession(session));
      elements.sessionList.append(button);
    }
    refreshIcons();
  } catch (error) {
    showToast(error.message, true);
  }
}

function selectSession(session) {
  state.sessionId = session.id;
  setText(elements.sessionTitle, session.title);
  if (session.provider && session.model) {
    setSelectedModel(session.provider, session.model, { persist: true, syncSelect: true });
  }
  loadSessions();
  closeMobilePanels();
  showToast("已切换会话；进程重启后历史会话会清空");
}

function newSession() {
  if (state.busy) stopRequest();
  state.sessionId = null;
  state.events = [];
  elements.chatMessages.querySelectorAll(".message, .activity-group").forEach(item => item.remove());
  elements.emptyState.hidden = false;
  setText(elements.sessionTitle, "新会话");
  renderTrace();
  loadSessions();
  activateNav("chat");
  elements.messageInput.focus();
}

function fileIcon(type) {
  return type === "dir" ? "folder" : "file-code-2";
}

function renderFiles(items = [], cwd = state.path) {
  state.path = cwd || ".";
  setText(elements.currentPath, state.path);
  elements.fileList.replaceChildren();
  if (!items.length) {
    elements.fileList.innerHTML = '<p class="muted-line">目录为空</p>';
    return;
  }
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "file-row";
    button.innerHTML = `<i data-lucide="${fileIcon(item.type)}" aria-hidden="true"></i><span class="file-name"></span><span class="file-size"></span>`;
    button.querySelector(".file-name").textContent = item.name;
    button.querySelector(".file-size").textContent = item.type === "dir" ? "" : formatBytes(item.size);
    button.addEventListener("click", () => item.type === "dir" ? loadFiles(item.path) : openFile(item.path));
    elements.fileList.append(button);
  }
  refreshIcons();
}

async function loadFiles(path = state.path) {
  try {
    const data = await (await api(`/api/files?path=${encodeURIComponent(path)}`)).json();
    renderFiles(data.items, data.cwd);
  } catch (error) {
    elements.fileList.innerHTML = '<p class="muted-line">无法读取文件列表</p>';
    showToast(error.message, true);
  }
}

async function openFile(path) {
  openContext("files");
  try {
    const data = await (await api(`/api/files/content?path=${encodeURIComponent(path)}`)).json();
    state.currentFile = path;
    setText(elements.filePreviewTitle, path.split(/[\\/]/).pop());
    setText(elements.filePreviewMeta, `${formatBytes(data.size)} · ${path}`);
    setText(elements.fileContent, data.content);
    elements.fileBrowser.hidden = true;
    elements.filePreview.hidden = false;
    setText(elements.contextTitle, "文件预览");
  } catch (error) {
    showToast(error.message, true);
  }
}

function closeFilePreview() {
  elements.filePreview.hidden = true;
  elements.fileBrowser.hidden = false;
  setText(elements.contextTitle, "文件");
}

async function downloadFile() {
  if (!state.currentFile) return;
  try {
    const response = await api(`/api/files/download?path=${encodeURIComponent(state.currentFile)}`);
    const blobUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = state.currentFile.split(/[\\/]/).pop() || "download";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderTrace() {
  setText(elements.eventCount, state.events.length);
  setText(elements.traceCount, state.events.length);
  elements.traceList.replaceChildren();
  if (!state.events.length) {
    elements.traceList.innerHTML = '<p class="muted-line">尚无执行记录</p>';
    return;
  }
  for (const event of [...state.events].reverse()) {
    const entry = document.createElement("article");
    entry.className = `trace-entry ${event.status}`;
    entry.innerHTML = '<div class="trace-head"><strong></strong><time class="trace-time"></time></div><div class="trace-detail"></div>';
    entry.querySelector("strong").textContent = event.name;
    entry.querySelector("time").textContent = formatTime(event.timestamp);
    entry.querySelector(".trace-detail").textContent = event.detail || eventStatusLabel(event.status);
    elements.traceList.append(entry);
  }
}

async function loadSkills() {
  try {
    const data = await (await api("/api/skills")).json();
    elements.skillList.replaceChildren();
    if (!data.skills.length) {
      elements.skillList.innerHTML = '<p class="muted-line">当前没有可用 Skill</p>';
      return;
    }
    for (const skill of data.skills) {
      const row = document.createElement("article");
      row.className = "skill-row";
      row.innerHTML = '<header><span class="skill-name"></span><span class="status-badge success">可用</span></header><div class="skill-description"></div>';
      row.querySelector(".skill-name").textContent = skill.name;
      row.querySelector(".skill-description").textContent = skill.description || "没有描述";
      elements.skillList.append(row);
    }
  } catch (error) {
    elements.skillList.innerHTML = '<p class="muted-line">Skills 加载失败</p>';
    showToast(error.message, true);
  }
}

function activateContextTab(tab) {
  document.querySelectorAll(".context-tab").forEach(button => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".context-view").forEach(view => view.classList.toggle("active", view.dataset.view === tab));
  setText(elements.contextTitle, tab === "files" ? "文件" : "活动");
  if (tab === "files") loadFiles();
  if (tab === "trace") renderTrace();
}

function openContext(tab = "files") {
  elements.appShell.classList.add("context-open");
  elements.contextPanel.setAttribute("aria-hidden", "false");
  closeFilePreview();
  activateContextTab(tab);
}

function closeContext() {
  elements.appShell.classList.remove("context-open");
  elements.contextPanel.setAttribute("aria-hidden", "true");
}

function toggleContext() {
  if (elements.appShell.classList.contains("context-open")) closeContext();
  else openContext("files");
}

function activateNav(target) {
  document.querySelectorAll("[data-nav-target]").forEach(button => button.classList.toggle("active", button.dataset.navTarget === target));
  if (target === "chat") closeContext();
  else openContext(target);
  closeMobilePanels();
}

function resizeComposer() {
  elements.messageInput.style.height = "auto";
  elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 180)}px`;
}

function toggleSidebar() {
  if (window.innerWidth <= 900) {
    elements.appShell.classList.toggle("mobile-sidebar-open");
    return;
  }
  const collapsed = elements.appShell.classList.toggle("sidebar-collapsed");
  localStorage.setItem("sidebarCollapsed", String(collapsed));
  elements.sidebarToggle.setAttribute("aria-label", collapsed ? "展开侧栏" : "折叠侧栏");
}

function closeMobilePanels() {
  elements.appShell.classList.remove("mobile-sidebar-open");
  if (window.innerWidth <= 900) closeContext();
}

function setMode(mode) {
  state.mode = mode;
  localStorage.setItem("agentMode", mode);
  setText(elements.modeLabel, mode === "team" ? "团队模式" : "单 Agent");
  document.querySelectorAll("[data-mode]").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
}

function activateSettingsTab(tab) {
  document.querySelectorAll("[data-settings-tab]").forEach(button => button.classList.toggle("active", button.dataset.settingsTab === tab));
  document.querySelectorAll("[data-settings-view]").forEach(view => view.classList.toggle("active", view.dataset.settingsView === tab));
  if (tab === "skills") loadSkills();
}

function openSettings(tab = "general") {
  elements.harnessTokenInput.value = state.token;
  activateSettingsTab(tab);
  if (!elements.settingsDialog.open) elements.settingsDialog.showModal();
  refreshIcons();
}

function saveSettings() {
  state.token = elements.harnessTokenInput.value.trim();
  localStorage.setItem("harnessToken", state.token);
  elements.settingsDialog.close();
  Promise.all([loadHealth(), loadModels(), loadSessions(), loadFiles(), loadSkills()]);
  showToast("设置已保存");
}

const commands = [
  { group: "会话", label: "新建会话", icon: "square-pen", run: newSession },
  { group: "会话", label: "聚焦聊天输入框", icon: "message-square", run: () => elements.messageInput.focus() },
  { group: "导航", label: "打开工作台", icon: "inbox", run: () => activateNav("chat") },
  { group: "导航", label: "打开运行记录", icon: "activity", run: () => activateNav("trace") },
  { group: "导航", label: "打开文件", icon: "files", run: () => activateNav("files") },
  { group: "设置", label: "打开设置", icon: "settings", run: () => openSettings("general") },
  { group: "设置", label: "查看 Skills", icon: "blocks", run: () => openSettings("skills") },
  { group: "设置", label: "查看 MCP", icon: "plug", run: () => openSettings("mcp") },
  { group: "界面", label: "切换左侧栏", icon: "panel-left", run: toggleSidebar },
  { group: "界面", label: "切换上下文面板", icon: "panel-right", run: toggleContext },
  { group: "Agent", label: "使用单 Agent", icon: "bot", run: () => setMode("single") },
  { group: "Agent", label: "使用团队模式", icon: "users", run: () => setMode("team") },
];

function filteredCommands() {
  const query = elements.commandInput.value.trim().toLocaleLowerCase();
  return commands.filter(command => !query || `${command.group} ${command.label}`.toLocaleLowerCase().includes(query));
}

function renderCommands() {
  const items = filteredCommands();
  state.commandIndex = Math.max(0, Math.min(state.commandIndex, items.length - 1));
  elements.commandResults.replaceChildren();
  let lastGroup = "";
  items.forEach((command, index) => {
    if (command.group !== lastGroup) {
      const label = document.createElement("div");
      label.className = "command-group-label";
      label.textContent = command.group;
      elements.commandResults.append(label);
      lastGroup = command.group;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = `command-item ${index === state.commandIndex ? "selected" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(index === state.commandIndex));
    button.innerHTML = `<i data-lucide="${command.icon}" aria-hidden="true"></i><span></span>`;
    button.querySelector("span").textContent = command.label;
    button.addEventListener("mouseenter", () => { state.commandIndex = index; renderCommands(); });
    button.addEventListener("click", () => runCommand(command));
    elements.commandResults.append(button);
  });
  if (!items.length) elements.commandResults.innerHTML = '<p class="muted-line">没有匹配的命令</p>';
  refreshIcons();
}

function openCommandPalette() {
  elements.commandInput.value = "";
  state.commandIndex = 0;
  renderCommands();
  if (!elements.commandDialog.open) elements.commandDialog.showModal();
  requestAnimationFrame(() => elements.commandInput.focus());
}

function runCommand(command) {
  elements.commandDialog.close();
  command.run();
}

function handleCommandKeydown(event) {
  const items = filteredCommands();
  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.commandIndex = Math.min(state.commandIndex + 1, items.length - 1);
    renderCommands();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    state.commandIndex = Math.max(state.commandIndex - 1, 0);
    renderCommands();
  } else if (event.key === "Enter" && items[state.commandIndex]) {
    event.preventDefault();
    runCommand(items[state.commandIndex]);
  }
}

function bindEvents() {
  elements.chatForm.addEventListener("submit", event => {
    event.preventDefault();
    if (state.busy) stopRequest();
    else sendMessage(elements.messageInput.value);
  });
  elements.messageInput.addEventListener("input", resizeComposer);
  elements.messageInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.chatForm.requestSubmit();
    }
  });
  document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => {
    elements.messageInput.value = button.dataset.prompt;
    resizeComposer();
    elements.messageInput.focus();
  }));
  document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => setMode(button.dataset.mode)));
  document.querySelectorAll("[data-nav-target]").forEach(button => button.addEventListener("click", () => activateNav(button.dataset.navTarget)));
  document.querySelectorAll(".context-tab").forEach(button => button.addEventListener("click", () => activateContextTab(button.dataset.tab)));
  document.querySelectorAll("[data-settings-tab]").forEach(button => button.addEventListener("click", () => activateSettingsTab(button.dataset.settingsTab)));

  elements.newSessionButton.addEventListener("click", newSession);
  elements.refreshSessionsButton.addEventListener("click", loadSessions);
  elements.searchButton.addEventListener("click", openCommandPalette);
  elements.sidebarToggle.addEventListener("click", toggleSidebar);
  elements.contextToggle.addEventListener("click", toggleContext);
  elements.closeContextButton.addEventListener("click", closeContext);
  elements.scrim.addEventListener("click", closeMobilePanels);
  elements.moreButton.addEventListener("click", openCommandPalette);
  elements.workspaceButton.addEventListener("click", () => openSettings("general"));
  elements.runtimeState.addEventListener("click", () => openSettings("general"));
  elements.settingsButton.addEventListener("click", () => openSettings("general"));
  elements.modeButton.addEventListener("click", () => openSettings("agent"));
  if (elements.modelSelect) {
    elements.modelSelect.addEventListener("change", () => {
      const value = elements.modelSelect.value || "";
      const slash = value.indexOf("/");
      if (slash <= 0) return;
      const provider = value.slice(0, slash);
      const model = value.slice(slash + 1);
      setSelectedModel(provider, model, { persist: true, syncSelect: false });
      showToast(`已切换模型：${modelLabelText(provider, model)}`);
    });
  }
  elements.attachContextButton.addEventListener("click", () => openContext("files"));
  elements.closeSettingsButton.addEventListener("click", () => elements.settingsDialog.close());
  elements.saveSettingsButton.addEventListener("click", saveSettings);
  elements.refreshFilesButton.addEventListener("click", () => loadFiles());
  elements.parentFolderButton.addEventListener("click", () => {
    const parts = state.path.replace(/\\/g, "/").split("/").filter(part => part && part !== ".");
    parts.pop();
    loadFiles(parts.join("/") || ".");
  });
  elements.backToFilesButton.addEventListener("click", closeFilePreview);
  elements.downloadFileButton.addEventListener("click", downloadFile);
  elements.commandInput.addEventListener("input", () => { state.commandIndex = 0; renderCommands(); });
  elements.commandInput.addEventListener("keydown", handleCommandKeydown);

  document.addEventListener("keydown", event => {
    const commandKey = event.ctrlKey || event.metaKey;
    if (commandKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
    } else if (commandKey && event.key.toLowerCase() === "b") {
      event.preventDefault();
      toggleSidebar();
    } else if (commandKey && event.key.toLowerCase() === "n") {
      event.preventDefault();
      newSession();
    } else if (event.key === "Escape" && !elements.settingsDialog.open && !elements.commandDialog.open) {
      closeMobilePanels();
      closeContext();
    }
  });
}

async function initialize() {
  Object.assign(elements, {
    appShell: document.getElementById("appShell"), sidebar: document.getElementById("sidebar"),
    workspaceButton: document.getElementById("workspaceButton"), modelLabel: document.getElementById("modelLabel"),
    sidebarToggle: document.getElementById("sidebarToggle"), contextToggle: document.getElementById("contextToggle"),
    contextPanel: document.getElementById("contextPanel"), closeContextButton: document.getElementById("closeContextButton"),
    contextTitle: document.getElementById("contextTitle"), scrim: document.getElementById("scrim"),
    runtimeState: document.getElementById("runtimeState"), sidebarRuntime: document.querySelector(".sidebar-runtime"),
    sidebarRuntimeLabel: document.getElementById("sidebarRuntimeLabel"), moreButton: document.getElementById("moreButton"),
    sessionTitle: document.getElementById("sessionTitle"), sessionList: document.getElementById("sessionList"),
    newSessionButton: document.getElementById("newSessionButton"), refreshSessionsButton: document.getElementById("refreshSessionsButton"),
    searchButton: document.getElementById("searchButton"), eventCount: document.getElementById("eventCount"),
    chatMessages: document.getElementById("chatMessages"), emptyState: document.getElementById("emptyState"),
    chatForm: document.getElementById("chatForm"), messageInput: document.getElementById("messageInput"),
    sendButton: document.getElementById("sendButton"), attachContextButton: document.getElementById("attachContextButton"),
    modeButton: document.getElementById("modeButton"), modeLabel: document.getElementById("modeLabel"),
    modelSelect: document.getElementById("modelSelect"),
    currentPath: document.getElementById("currentPath"), fileList: document.getElementById("fileList"),
    fileBrowser: document.getElementById("fileBrowser"), filePreview: document.getElementById("filePreview"),
    filePreviewTitle: document.getElementById("filePreviewTitle"), filePreviewMeta: document.getElementById("filePreviewMeta"),
    fileContent: document.getElementById("fileContent"), refreshFilesButton: document.getElementById("refreshFilesButton"),
    parentFolderButton: document.getElementById("parentFolderButton"), backToFilesButton: document.getElementById("backToFilesButton"),
    downloadFileButton: document.getElementById("downloadFileButton"), traceList: document.getElementById("traceList"),
    traceCount: document.getElementById("traceCount"), settingsButton: document.getElementById("settingsButton"),
    settingsDialog: document.getElementById("settingsDialog"), closeSettingsButton: document.getElementById("closeSettingsButton"),
    harnessTokenInput: document.getElementById("harnessTokenInput"), saveSettingsButton: document.getElementById("saveSettingsButton"),
    settingsModel: document.getElementById("settingsModel"), settingsHarness: document.getElementById("settingsHarness"),
    settingsSandbox: document.getElementById("settingsSandbox"), settingsTools: document.getElementById("settingsTools"),
    skillList: document.getElementById("skillList"), mcpServerName: document.getElementById("mcpServerName"),
    mcpDescription: document.getElementById("mcpDescription"), mcpStatus: document.getElementById("mcpStatus"),
    mcpTools: document.getElementById("mcpTools"), commandDialog: document.getElementById("commandDialog"),
    commandInput: document.getElementById("commandInput"), commandResults: document.getElementById("commandResults"),
    toast: document.getElementById("toast"),
  });

  if (localStorage.getItem("sidebarCollapsed") === "true" && window.innerWidth > 900) {
    elements.appShell.classList.add("sidebar-collapsed");
  }
  setMode(state.mode);
  bindEvents();
  refreshIcons();
  renderTrace();
  await Promise.all([loadHealth(), loadModels(), loadSessions(), loadFiles(), loadSkills()]);
}

document.addEventListener("DOMContentLoaded", initialize);
