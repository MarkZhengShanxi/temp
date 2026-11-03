chrome.runtime.onInstalled.addListener(() => {
  if (chrome.sidePanel?.setPanelBehavior) {
    chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message)
    .then(sendResponse)
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

async function handleMessage(message) {
  switch (message.type) {
    case "GET_BROWSER_STATE":
      return { ok: true, browser: await getBrowserState() };
    case "OBSERVE_ACTIVE_TAB":
      return observeActiveTab();
    case "EXECUTE_ACTION":
      return executeAction(message.action);
    default:
      return { ok: false, error: `Unknown message type: ${message.type}` };
  }
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("No active tab found.");
  return tab;
}

async function getBrowserState() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const active = tabs.find((tab) => tab.active);
  return {
    activeTabId: active?.id,
    activeTabUrl: active?.url,
    activeTabTitle: active?.title,
    tabs: tabs.map((tab, index) => ({
      index,
      id: tab.id,
      title: tab.title,
      url: tab.url,
      active: tab.active
    }))
  };
}

function isInjectableUrl(url) {
  if (!url) return false;
  return /^(https?|file):/.test(url);
}

async function ensureContentScript(tabId, url) {
  if (!isInjectableUrl(url)) {
    throw new Error("This page cannot be controlled by extensions. Try a normal http(s) web page.");
  }

  try {
    await chrome.tabs.sendMessage(tabId, { type: "PING" });
    return;
  } catch (_error) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"]
    });
  }
}

async function observeActiveTab() {
  const tab = await getActiveTab();
  await ensureContentScript(tab.id, tab.url);
  const browser = await getBrowserState();
  const observation = await chrome.tabs.sendMessage(tab.id, { type: "OBSERVE_PAGE" });
  observation.browser = browser;
  return { ok: true, observation };
}

async function executeAction(action) {
  if (!action?.type) return { ok: false, error: "Missing action type." };

  if (["open_tab", "switch_tab", "close_tab"].includes(action.type)) {
    return executeTabAction(action);
  }

  const tab = await getActiveTab();
  await ensureContentScript(tab.id, tab.url);
  return chrome.tabs.sendMessage(tab.id, { type: "EXECUTE_ACTION", action });
}

async function executeTabAction(action) {
  if (action.type === "open_tab") {
    if (!action.url) return { ok: false, error: "open_tab requires url." };
    const tab = await chrome.tabs.create({ url: action.url, active: true });
    return { ok: true, message: `Opened tab: ${tab.title || action.url}` };
  }

  const tabs = await chrome.tabs.query({ currentWindow: true });
  const target = tabs[action.tab_index];
  if (!target?.id) return { ok: false, error: `No tab at index ${action.tab_index}.` };

  if (action.type === "switch_tab") {
    await chrome.tabs.update(target.id, { active: true });
    return { ok: true, message: `Switched to tab: ${target.title || target.url}` };
  }

  if (action.type === "close_tab") {
    await chrome.tabs.remove(target.id);
    return { ok: true, message: `Closed tab: ${target.title || target.url}` };
  }

  return { ok: false, error: `Unsupported tab action: ${action.type}` };
}
