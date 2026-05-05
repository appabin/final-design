const STORAGE_KEY = "luminaClipperSettings";
const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8008",
  apiToken: "",
  selectionEndpoint: "/api/knowledge/text",
  pageEndpoint: "/api/knowledge/page",
  screenshotEndpoint: "/api/knowledge/screenshot",
  timeoutMs: 60000,
};

const elements = {
  form: document.getElementById("settings-form"),
  apiBaseUrl: document.getElementById("api-base-url"),
  apiToken: document.getElementById("api-token"),
  selectionEndpoint: document.getElementById("selection-endpoint"),
  pageEndpoint: document.getElementById("page-endpoint"),
  screenshotEndpoint: document.getElementById("screenshot-endpoint"),
  timeoutMs: document.getElementById("timeout-ms"),
  resetDefaults: document.getElementById("reset-defaults"),
  statusCard: document.getElementById("settings-status-card"),
  statusMessage: document.getElementById("settings-status-message"),
};

document.addEventListener("DOMContentLoaded", async () => {
  const settings = await loadSettings();
  applySettings(settings);

  elements.form.addEventListener("submit", onSaveSettings);
  elements.resetDefaults.addEventListener("click", onResetDefaults);
});

async function onSaveSettings(event) {
  event.preventDefault();

  const settings = {
    apiBaseUrl: elements.apiBaseUrl.value.trim(),
    apiToken: elements.apiToken.value.trim(),
    selectionEndpoint: ensureLeadingSlash(elements.selectionEndpoint.value.trim()),
    pageEndpoint: ensureLeadingSlash(elements.pageEndpoint.value.trim()),
    screenshotEndpoint: ensureLeadingSlash(elements.screenshotEndpoint.value.trim()),
    timeoutMs: Number(elements.timeoutMs.value) || DEFAULT_SETTINGS.timeoutMs,
  };

  await chrome.storage.sync.set({ [STORAGE_KEY]: settings });
  renderStatus("success", "设置已保存。");
}

async function onResetDefaults() {
  applySettings(DEFAULT_SETTINGS);
  await chrome.storage.sync.set({ [STORAGE_KEY]: DEFAULT_SETTINGS });
  renderStatus("success", "已恢复默认设置。");
}

async function loadSettings() {
  const stored = await chrome.storage.sync.get(STORAGE_KEY);
  return {
    ...DEFAULT_SETTINGS,
    ...(stored[STORAGE_KEY] || {}),
  };
}

function applySettings(settings) {
  elements.apiBaseUrl.value = settings.apiBaseUrl;
  elements.apiToken.value = settings.apiToken;
  elements.selectionEndpoint.value = settings.selectionEndpoint;
  elements.pageEndpoint.value = settings.pageEndpoint;
  elements.screenshotEndpoint.value = settings.screenshotEndpoint || DEFAULT_SETTINGS.screenshotEndpoint;
  elements.timeoutMs.value = String(settings.timeoutMs);
}

function renderStatus(status, message) {
  elements.statusCard.dataset.status = status;
  elements.statusMessage.textContent = message;
}

function ensureLeadingSlash(value) {
  if (!value) {
    return "/";
  }
  return value.startsWith("/") ? value : `/${value}`;
}
