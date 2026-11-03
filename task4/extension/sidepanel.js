const DEFAULT_CONFIG = {
  backendUrl: "http://127.0.0.1:8765",
  baseUrl: "https://api.openai.com/v1",
  model: "gpt-4.1-mini",
  temperature: 0.2,
  maxTokens: 2048,
  rememberKey: false,
  apiKey: ""
};

const els = {
  backendUrl: document.getElementById("backendUrl"),
  baseUrl: document.getElementById("baseUrl"),
  apiKey: document.getElementById("apiKey"),
  model: document.getElementById("model"),
  temperature: document.getElementById("temperature"),
  maxTokens: document.getElementById("maxTokens"),
  rememberKey: document.getElementById("rememberKey"),
  saveConfig: document.getElementById("saveConfig"),
  testConfig: document.getElementById("testConfig"),
  clearKey: document.getElementById("clearKey"),
  task: document.getElementById("task"),
  start: document.getElementById("start"),
  stop: document.getElementById("stop"),
  observe: document.getElementById("observe"),
  status: document.getElementById("status"),
  log: document.getElementById("log"),
  confirmCard: document.getElementById("confirmCard"),
  confirmText: document.getElementById("confirmText"),
  confirmAction: document.getElementById("confirmAction"),
  allowAction: document.getElementById("allowAction"),
  denyAction: document.getElementById("denyAction")
};

let currentRunId = null;
let pendingAction = null;
let lastObservation = null;
let stopped = false;

init();

async function init() {
  const saved = await chrome.storage.local.get(DEFAULT_CONFIG);
  setConfig(saved);
  bindEvents();
  log("Side Panel ready.");
}

function bindEvents() {
  els.saveConfig.addEventListener("click", saveConfig);
  els.testConfig.addEventListener("click", testConfig);
  els.clearKey.addEventListener("click", clearKey);
  els.observe.addEventListener("click", observeOnly);
  els.start.addEventListener("click", startRun);
  els.stop.addEventListener("click", stopRun);
  els.allowAction.addEventListener("click", () => continueAfterConfirmation("allow"));
  els.denyAction.addEventListener("click", () => continueAfterConfirmation("deny"));
}

function setConfig(config) {
  els.backendUrl.value = config.backendUrl || DEFAULT_CONFIG.backendUrl;
  els.baseUrl.value = config.baseUrl || DEFAULT_CONFIG.baseUrl;
  els.apiKey.value = config.apiKey || "";
  els.model.value = config.model || DEFAULT_CONFIG.model;
  els.temperature.value = config.temperature ?? DEFAULT_CONFIG.temperature;
  els.maxTokens.value = config.maxTokens || DEFAULT_CONFIG.maxTokens;
  els.rememberKey.checked = Boolean(config.rememberKey);
}

function getConfig() {
  return {
    backendUrl: els.backendUrl.value.trim().replace(/\/$/, ""),
    baseUrl: els.baseUrl.value.trim().replace(/\/$/, ""),
    apiKey: els.apiKey.value,
    model: els.model.value.trim(),
    temperature: Number(els.temperature.value || DEFAULT_CONFIG.temperature),
    maxTokens: Number(els.maxTokens.value || DEFAULT_CONFIG.maxTokens),
    rememberKey: els.rememberKey.checked
  };
}

async function saveConfig() {
  const config = getConfig();
  const toStore = { ...config };
  if (!config.rememberKey) toStore.apiKey = "";
  await chrome.storage.local.set(toStore);
  log(config.rememberKey ? "配置已保存（包含 API Key）。" : "配置已保存（API Key 未持久化）。");
}

async function clearKey() {
  els.apiKey.value = "";
  await chrome.storage.local.set({ apiKey: "", rememberKey: false });
  els.rememberKey.checked = false;
  log("API Key 已清除。");
}

async function testConfig() {
  const config = getConfig();
  setStatus("正在测试连接...");
  log(`测试连接：POST ${config.backendUrl}/api/config/test，base_url=${config.baseUrl}，model=${config.model}，api_key=${config.apiKey ? "已填写" : "未填写"}`);
  try {
    const res = await backendFetch("/api/config/test", {
      llm_config: llmConfigPayload()
    });
    log(res.ok ? `连接成功：${res.message}` : `连接失败：${res.message}`);
    setStatus(res.ok ? "后端和模型连接正常" : "模型连接失败（查看后端终端或 backend/logs/backend.log）");
  } catch (error) {
    log(`测试失败：${error.message}`);
    log("如果没有后端日志，请确认 uvicorn 正在运行，且后端 URL 指向 http://127.0.0.1:8765。");
    setStatus("连接失败");
  }
}

async function observeOnly() {
  try {
    setStatus("正在观察当前页面...");
    lastObservation = await observePage();
    log(`页面：${lastObservation.title || "(无标题)"}\nURL：${lastObservation.url}\n元素数：${lastObservation.elements?.length || 0}`);
    setStatus("页面观察完成");
  } catch (error) {
    log(`观察失败：${error.message}`);
    setStatus("页面观察失败");
  }
}

async function startRun() {
  const task = els.task.value.trim();
  if (!task) {
    log("请先输入任务。");
    return;
  }

  stopped = false;
  pendingAction = null;
  currentRunId = null;
  els.start.disabled = true;
  els.stop.disabled = false;
  hideConfirm();
  setStatus("启动 Agent...");
  log(`任务：${task}`);

  try {
    lastObservation = await observePage();
    const response = await backendFetch("/api/agent/start", {
      task,
      browser_state: lastObservation,
      llm_config: llmConfigPayload(),
      options: { max_steps: 20, require_confirmation_for_submit: true }
    });
    currentRunId = response.run_id;
    await handleAgentResponse(response);
  } catch (error) {
    log(`启动失败：${error.message}`);
    setStatus("启动失败");
    els.start.disabled = false;
    els.stop.disabled = true;
  }
}

async function stopRun() {
  stopped = true;
  hideConfirm();
  if (currentRunId) {
    try {
      await backendFetch("/api/agent/stop", { run_id: currentRunId });
    } catch (error) {
      log(`停止请求失败：${error.message}`);
    }
  }
  setStatus("已停止");
  els.start.disabled = false;
  els.stop.disabled = true;
}

async function handleAgentResponse(response) {
  if (stopped) return;
  log(`Step ${response.step_index}: ${response.message}`);

  if (["completed", "failed", "stopped"].includes(response.status)) {
    setStatus(response.status === "completed" ? "任务完成" : `任务${response.status}`);
    if (response.summary) log(`总结：${response.summary}`);
    els.start.disabled = false;
    els.stop.disabled = true;
    return;
  }

  if (response.requires_confirmation) {
    pendingAction = response.action;
    showConfirm(response.message, response.action);
    setStatus("等待用户确认");
    return;
  }

  if (!response.action) {
    setStatus("没有可执行动作");
    els.start.disabled = false;
    els.stop.disabled = true;
    return;
  }

  await executeAndContinue(response.action);
}

async function executeAndContinue(action) {
  if (stopped) return;
  setStatus(`执行动作：${action.type}`);
  log(`执行：${action.type} - ${action.rationale || ""}`);

  let result = await chrome.runtime.sendMessage({ type: "EXECUTE_ACTION", action });
  if (!result) result = { ok: false, error: "No result from background." };
  log(result.ok ? `执行成功：${result.message || "ok"}` : `执行失败：${result.error || "unknown error"}`);

  await sleep(500);
  try {
    lastObservation = await observePage();
  } catch (error) {
    lastObservation = { url: "", title: "", text: "", elements: [], error: error.message };
  }

  const response = await backendFetch("/api/agent/step", {
    run_id: currentRunId,
    browser_state: lastObservation,
    last_action_result: {
      ok: Boolean(result.ok),
      message: result.message || null,
      error: result.error || null,
      data: result.data || {},
      observation: result.observation || null
    },
    user_confirmation: null
  });
  await handleAgentResponse(response);
}

async function continueAfterConfirmation(decision) {
  hideConfirm();

  if (decision === "allow" && pendingAction) {
    log("用户允许动作。 ");
    const action = pendingAction;
    pendingAction = null;
    await executeAndContinue({ ...action, requires_confirmation: false });
    return;
  }

  log("用户拒绝动作，任务停止。 ");
  const response = await backendFetch("/api/agent/step", {
    run_id: currentRunId,
    browser_state: lastObservation || (await observePage()),
    last_action_result: null,
    user_confirmation: "deny"
  });
  await handleAgentResponse(response);
}

async function observePage() {
  const response = await chrome.runtime.sendMessage({ type: "OBSERVE_ACTIVE_TAB" });
  if (!response?.ok) throw new Error(response?.error || "observe failed");
  return response.observation;
}

function llmConfigPayload() {
  const config = getConfig();
  return {
    base_url: config.baseUrl,
    api_key: config.apiKey || null,
    model: config.model,
    temperature: config.temperature,
    max_tokens: config.maxTokens
  };
}

async function backendFetch(path, body) {
  const config = getConfig();
  const response = await fetch(`${config.backendUrl}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_error) {
    data = { detail: text };
  }
  if (!response.ok) throw new Error(data.detail || data.message || `${response.status} ${text}`);
  return data;
}

function showConfirm(message, action) {
  els.confirmText.textContent = message;
  els.confirmAction.textContent = JSON.stringify(action, null, 2);
  els.confirmCard.classList.remove("hidden");
}

function hideConfirm() {
  els.confirmCard.classList.add("hidden");
}

function setStatus(text) {
  els.status.textContent = text;
}

function log(message) {
  const time = new Date().toLocaleTimeString();
  els.log.textContent += `[${time}] ${message}\n`;
  els.log.scrollTop = els.log.scrollHeight;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
