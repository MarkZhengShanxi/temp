let elementCounter = 1;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "PING") {
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "OBSERVE_PAGE") {
    sendResponse(observePage());
    return true;
  }

  if (message.type === "EXECUTE_ACTION") {
    executeAction(message.action)
      .then(sendResponse)
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
});

function observePage() {
  return {
    url: location.href,
    title: document.title,
    text: visibleText(),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      documentHeight: document.documentElement.scrollHeight,
      documentWidth: document.documentElement.scrollWidth
    },
    elements: collectElements()
  };
}

function visibleText() {
  const text = document.body?.innerText || "";
  return text.replace(/\s+/g, " ").trim().slice(0, 7000);
}

function collectElements() {
  const selector = [
    "a[href]",
    "button",
    "input",
    "textarea",
    "select",
    "[role='button']",
    "[role='link']",
    "[contenteditable='true']",
    "[onclick]"
  ].join(",");

  const nodes = Array.from(document.querySelectorAll(selector));
  const out = [];

  for (const node of nodes) {
    if (!isVisible(node)) continue;
    if (!node.dataset.agentId) node.dataset.agentId = `e${elementCounter++}`;

    const rect = node.getBoundingClientRect();
    const inputType = node.getAttribute("type");
    const isPassword = inputType?.toLowerCase() === "password";

    out.push({
      id: node.dataset.agentId,
      tag: node.tagName.toLowerCase(),
      role: node.getAttribute("role"),
      type: inputType,
      text: labelFor(node).slice(0, 200),
      aria_label: node.getAttribute("aria-label"),
      placeholder: node.getAttribute("placeholder"),
      selector: cssPath(node),
      href: node.href || null,
      value: isPassword ? null : valueOf(node),
      visible: true,
      enabled: !node.disabled,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });

    if (out.length >= 180) break;
  }

  return out;
}

function isVisible(el) {
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    style.visibility !== "hidden" &&
    style.display !== "none" &&
    rect.bottom >= 0 &&
    rect.right >= 0 &&
    rect.top <= window.innerHeight &&
    rect.left <= window.innerWidth
  );
}

function labelFor(el) {
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.trim();

  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const label = document.getElementById(labelledBy);
    if (label?.innerText) return label.innerText.trim();
  }

  if (el.id) {
    const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (label?.innerText) return label.innerText.trim();
  }

  const placeholder = el.getAttribute("placeholder");
  if (placeholder) return placeholder.trim();

  const title = el.getAttribute("title");
  if (title) return title.trim();

  const text = el.innerText || el.textContent || "";
  if (text.trim()) return text.trim();

  const value = valueOf(el);
  if (value) return value;

  return `${el.tagName.toLowerCase()} ${el.getAttribute("name") || ""}`.trim();
}

function valueOf(el) {
  if ("value" in el && el.getAttribute("type")?.toLowerCase() !== "password") return el.value || "";
  return "";
}

function cssPath(el) {
  if (el.id) return `#${CSS.escape(el.id)}`;
  if (el.dataset.agentId) return `[data-agent-id="${CSS.escape(el.dataset.agentId)}"]`;
  return el.tagName.toLowerCase();
}

async function executeAction(action) {
  switch (action.type) {
    case "click":
      return click(action.target_element_id);
    case "type":
      return typeText(action.target_element_id, action.text || "");
    case "clear":
      return clear(action.target_element_id);
    case "press_key":
      return pressKey(action.target_element_id, action.key || "Enter");
    case "select":
      return selectValue(action.target_element_id, action.text || "");
    case "scroll":
      return scrollPage(action.direction || "down", action.amount || 700);
    case "wait":
      await sleep(action.amount || 1000);
      return { ok: true, message: `Waited ${action.amount || 1000}ms.` };
    case "read_page":
      return { ok: true, message: "Observed page.", observation: observePage() };
    default:
      return { ok: false, error: `Unsupported page action: ${action.type}` };
  }
}

function byId(id) {
  if (!id) throw new Error("Missing target_element_id.");
  const el = document.querySelector(`[data-agent-id="${CSS.escape(id)}"]`);
  if (!el) throw new Error(`Element not found: ${id}`);
  return el;
}

async function prepare(el) {
  el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  await sleep(250);
  el.focus?.();
}

async function click(id) {
  const el = byId(id);
  await prepare(el);
  el.click();
  return { ok: true, message: `Clicked ${id}: ${labelFor(el).slice(0, 100)}` };
}

async function typeText(id, text) {
  const el = byId(id);
  await prepare(el);
  if (el.getAttribute("type")?.toLowerCase() === "password") {
    return { ok: false, error: "Password fields require manual user handling." };
  }
  if ("value" in el) {
    el.value = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  } else if (el.isContentEditable) {
    el.textContent = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
  } else {
    throw new Error(`Element ${id} is not editable.`);
  }
  return { ok: true, message: `Typed into ${id}.` };
}

async function clear(id) {
  return typeText(id, "");
}

async function pressKey(id, key) {
  const el = id ? byId(id) : document.activeElement;
  await prepare(el);
  for (const type of ["keydown", "keyup"]) {
    el.dispatchEvent(new KeyboardEvent(type, { key, bubbles: true, cancelable: true }));
  }
  return { ok: true, message: `Pressed ${key}.` };
}

async function selectValue(id, value) {
  const el = byId(id);
  await prepare(el);
  if (el.tagName.toLowerCase() !== "select") throw new Error(`Element ${id} is not a select.`);
  el.value = value;
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return { ok: true, message: `Selected ${value}.` };
}

async function scrollPage(direction, amount) {
  const sign = direction === "up" || direction === "left" ? -1 : 1;
  const horizontal = direction === "left" || direction === "right";
  window.scrollBy({
    top: horizontal ? 0 : sign * amount,
    left: horizontal ? sign * amount : 0,
    behavior: "smooth"
  });
  await sleep(500);
  return { ok: true, message: `Scrolled ${direction} by ${amount}px.` };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
