const elements = {
  pageTitle: document.getElementById("page-title"),
  selectionPreview: document.getElementById("selection-preview"),
  saveSelection: document.getElementById("save-selection"),
  savePage: document.getElementById("save-page"),
  saveScreenshot: document.getElementById("save-screenshot"),
  retryLast: document.getElementById("retry-last"),
  statusCard: document.getElementById("status-card"),
  statusMessage: document.getElementById("status-message"),
  statusMeta: document.getElementById("status-meta"),
  openOptions: document.getElementById("open-options"),
};

let activeTabId = null;

document.addEventListener("DOMContentLoaded", async () => {
  elements.saveSelection.addEventListener("click", () => void runCapture("selection"));
  elements.savePage.addEventListener("click", () => void runCapture("page"));
  elements.saveScreenshot.addEventListener("click", () => void runCapture("screenshot"));
  elements.retryLast.addEventListener("click", () => void retryLastFailure());
  elements.openOptions.addEventListener("click", () => chrome.runtime.openOptionsPage());

  await hydratePopup();
});

async function hydratePopup() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  activeTabId = typeof tab?.id === "number" ? tab.id : null;

  await Promise.all([loadPageContext(), loadExtensionState()]);
}

async function loadPageContext() {
  if (activeTabId === null) {
    setPageContext({
      title: "没有活动标签页",
      selectionPreview: "请先打开一个普通网页再进行采集。",
    });
    disableActionButtons(true);
    return;
  }

  try {
    const response = await chrome.tabs.sendMessage(activeTabId, { type: "LUMINA_GET_PAGE_CONTEXT" });
    if (!response?.ok) {
      throw new Error(response?.error || "无法读取当前页面信息。");
    }

    setPageContext({
      title: response.payload.title,
      selectionPreview: response.payload.hasSelection ? response.payload.selectionPreview : "当前页面没有选中文字。",
    });
  } catch (error) {
    setPageContext({
      title: tabTitleFallback(),
      selectionPreview: "当前页面不支持内容采集。",
    });
    disableActionButtons(true);
    renderStatus({ status: "error", message: getErrorMessage(error), at: new Date().toISOString() });
  }
}

async function loadExtensionState() {
  const response = await chrome.runtime.sendMessage({ type: "GET_EXTENSION_STATE" });
  if (!response?.ok) {
    renderStatus({ status: "error", message: response?.error || "无法读取插件状态。", at: new Date().toISOString() });
    return;
  }

  const state = response.result;
  if (!state.settingsConfigured) {
    renderStatus({
      status: "error",
      message: "请先在设置页配置后端地址。",
      at: new Date().toISOString(),
    });
  } else if (state.lastStatus) {
    renderStatus(state.lastStatus);
  } else {
    renderStatus({ status: "idle", message: "就绪。", at: null });
  }

  elements.retryLast.hidden = !state.hasFailedRequest;
}

async function runCapture(captureType) {
  if (activeTabId === null) {
    renderStatus({ status: "error", message: "当前没有可采集的活动标签页。", at: new Date().toISOString() });
    return;
  }

  disableActionButtons(true);
  renderStatus({
    status: "working",
    message: captureWorkingMessage(captureType),
    at: new Date().toISOString(),
  });

  try {
    const messageTypeByCapture = {
      selection: "RUN_SELECTION_CAPTURE",
      page: "RUN_PAGE_CAPTURE",
      screenshot: "RUN_SCREENSHOT_CAPTURE",
    };
    const response = await chrome.runtime.sendMessage({
      type: messageTypeByCapture[captureType],
      tabId: activeTabId,
    });

    if (!response?.ok) {
      throw new Error(response?.error || "上传失败。");
    }

    renderStatus({
      status: "success",
      message: response.result.message,
      captureType: response.result.captureType,
      title: response.result.title,
      url: response.result.url,
      at: new Date().toISOString(),
    });
    elements.retryLast.hidden = true;
  } catch (error) {
    renderStatus({ status: "error", message: getErrorMessage(error), at: new Date().toISOString() });
    elements.retryLast.hidden = false;
  } finally {
    disableActionButtons(false);
    await loadPageContext();
  }
}

async function retryLastFailure() {
  disableActionButtons(true);
  renderStatus({ status: "working", message: "正在重试上次失败上传...", at: new Date().toISOString() });

  try {
    const response = await chrome.runtime.sendMessage({ type: "RETRY_LAST_FAILURE" });
    if (!response?.ok) {
      throw new Error(response?.error || "重试失败。");
    }

    renderStatus({
      status: "success",
      message: response.result.message,
      captureType: response.result.captureType,
      title: response.result.title,
      url: response.result.url,
      at: new Date().toISOString(),
    });
    elements.retryLast.hidden = true;
  } catch (error) {
    renderStatus({ status: "error", message: getErrorMessage(error), at: new Date().toISOString() });
  } finally {
    disableActionButtons(false);
  }
}

function setPageContext({ title, selectionPreview }) {
  elements.pageTitle.textContent = title;
  elements.selectionPreview.textContent = selectionPreview;
}

function renderStatus(status) {
  elements.statusCard.dataset.status = status.status;
  elements.statusMessage.textContent = status.message;

  const metaParts = [];
  if (status.captureType) {
    metaParts.push(status.captureType);
  }
  if (status.title) {
    metaParts.push(status.title);
  }
  if (status.at) {
    metaParts.push(new Date(status.at).toLocaleTimeString());
  }
  elements.statusMeta.textContent = metaParts.join(" | ");
}

function disableActionButtons(disabled) {
  elements.saveSelection.disabled = disabled;
  elements.savePage.disabled = disabled;
  elements.saveScreenshot.disabled = disabled;
  elements.retryLast.disabled = disabled;
}

function captureWorkingMessage(captureType) {
  if (captureType === "selection") {
    return "正在保存选中文字...";
  }
  if (captureType === "screenshot") {
    return "请在页面上拖拽选择截图区域...";
  }
  return "正在保存网页正文...";
}

function tabTitleFallback() {
  return "当前页面不支持";
}

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  if (typeof error === "string") {
    return error;
  }

  return "未知错误";
}
