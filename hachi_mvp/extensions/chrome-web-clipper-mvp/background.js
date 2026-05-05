const CONTEXT_MENU_IDS = {
  selection: "lumina-save-selection",
  page: "lumina-save-page",
  screenshot: "lumina-save-screenshot",
};

const STORAGE_KEYS = {
  settings: "luminaClipperSettings",
  lastStatus: "luminaClipperLastStatus",
  failedRequest: "luminaClipperFailedRequest",
};

const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8008",
  apiToken: "",
  selectionEndpoint: "/api/knowledge/text",
  pageEndpoint: "/api/knowledge/page",
  screenshotEndpoint: "/api/knowledge/screenshot",
  timeoutMs: 60000,
};

chrome.runtime.onInstalled.addListener(async () => {
  await createContextMenus();
});

chrome.runtime.onStartup.addListener(async () => {
  await createContextMenus();
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab || typeof tab.id !== "number") {
    return;
  }

  if (info.menuItemId === CONTEXT_MENU_IDS.selection) {
    void handleCaptureRequest("selection", tab.id).catch(() => {});
  }

  if (info.menuItemId === CONTEXT_MENU_IDS.page) {
    void handleCaptureRequest("page", tab.id).catch(() => {});
  }

  if (info.menuItemId === CONTEXT_MENU_IDS.screenshot) {
    void handleCaptureRequest("screenshot", tab.id).catch(() => {});
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== "string") {
    return false;
  }

  if (message.type === "RUN_SELECTION_CAPTURE") {
    void respondAsync(sendResponse, handleCaptureRequest("selection", message.tabId ?? sender.tab?.id));
    return true;
  }

  if (message.type === "RUN_PAGE_CAPTURE") {
    void respondAsync(sendResponse, handleCaptureRequest("page", message.tabId ?? sender.tab?.id));
    return true;
  }

  if (message.type === "RUN_SCREENSHOT_CAPTURE") {
    void respondAsync(sendResponse, handleCaptureRequest("screenshot", message.tabId ?? sender.tab?.id));
    return true;
  }

  if (message.type === "GET_EXTENSION_STATE") {
    void respondAsync(sendResponse, getExtensionState());
    return true;
  }

  if (message.type === "RETRY_LAST_FAILURE") {
    void respondAsync(sendResponse, retryLastFailure());
    return true;
  }

  return false;
});

async function respondAsync(sendResponse, promise) {
  try {
    const result = await promise;
    sendResponse({ ok: true, result });
  } catch (error) {
    sendResponse({ ok: false, error: getErrorMessage(error) });
  }
}

async function createContextMenus() {
  await chrome.contextMenus.removeAll();

  chrome.contextMenus.create({
    id: CONTEXT_MENU_IDS.selection,
    title: "保存选中文字到 Hachi",
    contexts: ["selection"],
  });

  chrome.contextMenus.create({
    id: CONTEXT_MENU_IDS.page,
    title: "保存网页正文到 Hachi",
    contexts: ["page", "action"],
  });

  chrome.contextMenus.create({
    id: CONTEXT_MENU_IDS.screenshot,
    title: "框选截图保存到 Hachi",
    contexts: ["page", "action"],
  });
}

async function getExtensionState() {
  const settings = await getSettings();
  const stored = await chrome.storage.local.get([STORAGE_KEYS.lastStatus, STORAGE_KEYS.failedRequest]);

  return {
    settings,
    settingsConfigured: Boolean(settings.apiBaseUrl),
    lastStatus: stored[STORAGE_KEYS.lastStatus] ?? null,
    hasFailedRequest: Boolean(stored[STORAGE_KEYS.failedRequest]),
  };
}

async function handleCaptureRequest(captureType, tabId) {
  try {
    if (typeof tabId !== "number") {
      throw new Error("当前没有可采集的活动标签页。");
    }

    const capture =
      captureType === "screenshot"
        ? await requestScreenshotFromTab(tabId)
        : await requestCaptureFromTab(tabId, captureType);
    const uploadResult = await uploadCapture(captureType, capture);

    await chrome.storage.local.set({
      [STORAGE_KEYS.lastStatus]: {
        status: "success",
        captureType,
        title: capture.title,
        url: capture.url,
        message: uploadResult.message,
        at: new Date().toISOString(),
      },
      [STORAGE_KEYS.failedRequest]: null,
    });

    return {
      status: "success",
      captureType,
      title: capture.title,
      url: capture.url,
      message: uploadResult.message,
      response: uploadResult.data,
    };
  } catch (error) {
    await chrome.storage.local.set({
      [STORAGE_KEYS.lastStatus]: {
        status: "error",
        captureType,
        message: getErrorMessage(error),
        at: new Date().toISOString(),
      },
    });
    throw error;
  }
}

async function retryLastFailure() {
  const stored = await chrome.storage.local.get(STORAGE_KEYS.failedRequest);
  const failedRequest = stored[STORAGE_KEYS.failedRequest];

  if (!failedRequest) {
    throw new Error("当前没有可重试的失败请求。");
  }

  const uploadResult = await uploadCapture(failedRequest.captureType, failedRequest.capture);

  await chrome.storage.local.set({
    [STORAGE_KEYS.lastStatus]: {
      status: "success",
      captureType: failedRequest.captureType,
      title: failedRequest.capture.title,
      url: failedRequest.capture.url,
      message: `${uploadResult.message} (retried)`,
      at: new Date().toISOString(),
    },
    [STORAGE_KEYS.failedRequest]: null,
  });

  return {
    status: "success",
    captureType: failedRequest.captureType,
    title: failedRequest.capture.title,
    url: failedRequest.capture.url,
    message: `${uploadResult.message} (retried)`,
    response: uploadResult.data,
  };
}

async function requestCaptureFromTab(tabId, captureType) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, {
      type: captureType === "selection" ? "LUMINA_CAPTURE_SELECTION" : "LUMINA_CAPTURE_PAGE",
    });

    if (!response || !response.ok) {
      throw new Error(response?.error || "页面采集脚本未返回有效结果。");
    }

    return response.payload;
  } catch (error) {
    const message = getErrorMessage(error);

    if (message.includes("Receiving end does not exist")) {
      throw new Error("当前页面不支持采集，请在普通网页中使用该插件，不要在浏览器内部页面中使用。");
    }

    throw error;
  }
}

async function requestScreenshotFromTab(tabId) {
  const tab = await chrome.tabs.get(tabId);
  if (!tab || typeof tab.windowId !== "number") {
    throw new Error("当前没有可截图的活动标签页。");
  }

  const selection = await requestScreenshotRegionFromTab(tabId);
  await delay(120);

  const imageDataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "jpeg",
    quality: 80,
  });

  if (!imageDataUrl || !imageDataUrl.startsWith("data:image/")) {
    throw new Error("截图采集失败，浏览器未返回图片数据。");
  }

  const croppedImageDataUrl = await cropImageDataUrl(imageDataUrl, selection);

  return {
    title: selection.title || tab.title || "未命名截图",
    url: selection.url || tab.url || "",
    imageDataUrl: croppedImageDataUrl,
    capturedAt: new Date().toISOString(),
    captureKind: "selected_region",
    region: selection.region,
  };
}

async function requestScreenshotRegionFromTab(tabId) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, {
      type: "LUMINA_SELECT_SCREENSHOT_REGION",
    });

    if (!response || !response.ok) {
      throw new Error(response?.error || "页面截图选区未返回有效结果。");
    }

    return response.payload;
  } catch (error) {
    const message = getErrorMessage(error);

    if (message.includes("Receiving end does not exist")) {
      throw new Error("当前页面不支持画框截图，请在普通网页中使用该插件。");
    }

    throw error;
  }
}

async function cropImageDataUrl(imageDataUrl, selection) {
  const rect = selection.region;
  if (!rect || rect.width <= 0 || rect.height <= 0) {
    throw new Error("截图选区无效。");
  }

  const blob = await (await fetch(imageDataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  const scaleX = bitmap.width / Math.max(1, Number(selection.viewportWidth) || bitmap.width);
  const scaleY = bitmap.height / Math.max(1, Number(selection.viewportHeight) || bitmap.height);

  const sx = clamp(Math.round(rect.x * scaleX), 0, bitmap.width - 1);
  const sy = clamp(Math.round(rect.y * scaleY), 0, bitmap.height - 1);
  const sw = clamp(Math.round(rect.width * scaleX), 1, bitmap.width - sx);
  const sh = clamp(Math.round(rect.height * scaleY), 1, bitmap.height - sy);

  const canvas = new OffscreenCanvas(sw, sh);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("无法创建截图裁剪画布。");
  }

  context.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);
  bitmap.close?.();
  const croppedBlob = await canvas.convertToBlob({
    type: "image/jpeg",
    quality: 0.86,
  });
  return await blobToDataUrl(croppedBlob);
}

async function uploadCapture(captureType, capture) {
  const settings = await getSettings();

  if (!settings.apiBaseUrl) {
    throw new Error("后端地址未配置，请先打开插件设置页完成配置。");
  }

  try {
    if (captureType === "selection") {
      return await postSelectionCapture(settings, capture);
    }

    if (captureType === "screenshot") {
      return await postScreenshotCapture(settings, capture);
    }

    return await postPageCapture(settings, capture);
  } catch (error) {
    await chrome.storage.local.set({
      [STORAGE_KEYS.lastStatus]: {
        status: "error",
        captureType,
        title: capture.title,
        url: capture.url,
        message: getErrorMessage(error),
        at: new Date().toISOString(),
      },
      [STORAGE_KEYS.failedRequest]: { captureType, capture },
    });
    throw error;
  }
}

async function postScreenshotCapture(settings, capture) {
  const url = joinUrl(settings.apiBaseUrl, settings.screenshotEndpoint || DEFAULT_SETTINGS.screenshotEndpoint);
  const payload = {
    title: `截图：${capture.title || "未命名页面"}`,
    url: capture.url,
    image_data_url: capture.imageDataUrl,
    metadata: {
      captured_at: capture.capturedAt,
      capture_kind: capture.captureKind,
      region: capture.region,
      capture_tool: "lumina-web-clipper-mvp",
    },
  };

  const screenshotSettings = {
    ...settings,
    timeoutMs: Math.max(Number(settings.timeoutMs) || 0, 60000),
  };
  const data = await postJson(url, payload, screenshotSettings);
  return {
    message: "框选截图已识别并保存。",
    data,
  };
}

async function postSelectionCapture(settings, capture) {
  const url = joinUrl(settings.apiBaseUrl, settings.selectionEndpoint);
  const payload = {
    title: capture.title,
    text: capture.text,
    url: capture.url,
    source_type: "selection",
    metadata: {
      site_name: capture.siteName,
      captured_at: capture.capturedAt,
      context_before: capture.contextBefore,
      context_after: capture.contextAfter,
      capture_tool: "lumina-web-clipper-mvp",
    },
  };

  const data = await postJson(url, payload, settings);
  return {
    message: "选中文字已成功保存。",
    data,
  };
}

async function postPageCapture(settings, capture) {
  const pageUrl = joinUrl(settings.apiBaseUrl, settings.pageEndpoint);
  const pagePayload = {
    title: capture.title,
    url: capture.url,
    content: capture.content,
    excerpt: capture.excerpt,
    source_type: "page",
    metadata: {
      site_name: capture.siteName,
      captured_at: capture.capturedAt,
      byline: capture.byline,
      capture_tool: "lumina-web-clipper-mvp",
    },
  };

  try {
    const data = await postJson(pageUrl, pagePayload, settings);
    return {
      message: "网页正文已成功保存。",
      data,
    };
  } catch (error) {
    if (!shouldFallbackToTextEndpoint(error)) {
      throw error;
    }

    const fallbackUrl = joinUrl(settings.apiBaseUrl, settings.selectionEndpoint);
    const fallbackPayload = {
      title: capture.title,
      text: capture.content,
      url: capture.url,
      source_type: "page",
      metadata: {
        site_name: capture.siteName,
        captured_at: capture.capturedAt,
        excerpt: capture.excerpt,
        byline: capture.byline,
        capture_tool: "lumina-web-clipper-mvp",
      },
    };

    const data = await postJson(fallbackUrl, fallbackPayload, settings);
    return {
      message: "网页正文已通过文本入库接口保存。",
      data,
    };
  }
}

async function postJson(url, payload, settings) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), settings.timeoutMs);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: buildHeaders(settings.apiToken),
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const rawText = await response.text();
    const data = tryParseJson(rawText);

    if (!response.ok) {
      const error = new Error(formatApiError(data, rawText, response.status));
      error.status = response.status;
      error.responseBody = rawText;
      throw error;
    }

    return data ?? rawText;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(`请求超时，已超过 ${settings.timeoutMs} 毫秒。`);
    }

    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

function shouldFallbackToTextEndpoint(error) {
  return error && (error.status === 404 || error.status === 405);
}

function buildHeaders(apiToken) {
  const headers = {
    "Content-Type": "application/json",
  };

  if (apiToken) {
    headers.Authorization = `Bearer ${apiToken}`;
  }

  return headers;
}

function joinUrl(baseUrl, pathName) {
  const safeBase = baseUrl.replace(/\/$/, "");
  const safePath = pathName.startsWith("/") ? pathName : `/${pathName}`;
  return `${safeBase}${safePath}`;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

async function blobToDataUrl(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return `data:${blob.type || "image/jpeg"};base64,${btoa(binary)}`;
}

async function getSettings() {
  const stored = await chrome.storage.sync.get(STORAGE_KEYS.settings);
  return {
    ...DEFAULT_SETTINGS,
    ...(stored[STORAGE_KEYS.settings] || {}),
  };
}

function tryParseJson(rawText) {
  if (!rawText) {
    return null;
  }

  try {
    return JSON.parse(rawText);
  } catch {
    return null;
  }
}

function formatApiError(data, rawText, status) {
  if (data && typeof data === "object") {
    const providerMessage = data?.error?.message;
    if (providerMessage) {
      return String(providerMessage);
    }

    if (Array.isArray(data.detail)) {
      const lines = data.detail.map((item) => formatValidationItem(item)).filter(Boolean);
      if (lines.length > 0) {
        return lines.join("; ");
      }
    }

    if (typeof data.detail === "string" && data.detail) {
      return data.detail;
    }

    if (data.detail && typeof data.detail === "object") {
      return JSON.stringify(data.detail);
    }
  }

  return rawText || `请求失败，状态码 ${status}`;
}

function formatValidationItem(item) {
  if (!item || typeof item !== "object") {
    return "";
  }

  const location = Array.isArray(item.loc) ? item.loc.join(".") : "";
  const message = typeof item.msg === "string" ? item.msg : "";
  if (location && message) {
    return `${location}: ${message}`;
  }
  if (message) {
    return message;
  }
  return JSON.stringify(item);
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
