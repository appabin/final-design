const NOISE_SELECTORS = [
  "script",
  "style",
  "noscript",
  "iframe",
  "svg",
  "canvas",
  "form",
  "button",
  "input",
  "select",
  "textarea",
  "nav",
  "footer",
  "aside",
  "[role='navigation']",
  "[role='complementary']",
  ".sidebar",
  ".advertisement",
  ".ads",
  ".cookie",
  ".newsletter",
  ".share",
  ".social",
  ".comments",
  ".related",
  ".recommend",
];

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message.type !== "string") {
    return false;
  }

  if (message.type === "LUMINA_SELECT_SCREENSHOT_REGION") {
    void selectScreenshotRegion()
      .then((payload) => sendResponse({ ok: true, payload }))
      .catch((error) => sendResponse({ ok: false, error: getErrorMessage(error) }));
    return true;
  }

  try {
    if (message.type === "LUMINA_GET_PAGE_CONTEXT") {
      sendResponse({ ok: true, payload: getPageContext() });
      return false;
    }

    if (message.type === "LUMINA_CAPTURE_SELECTION") {
      sendResponse({ ok: true, payload: extractSelectionCapture() });
      return false;
    }

    if (message.type === "LUMINA_CAPTURE_PAGE") {
      sendResponse({ ok: true, payload: extractPageCapture() });
      return false;
    }
  } catch (error) {
    sendResponse({ ok: false, error: getErrorMessage(error) });
    return false;
  }

  return false;
});

function selectScreenshotRegion() {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById("lumina-screenshot-region-overlay");
    if (existing) {
      existing.remove();
    }

    const overlay = document.createElement("div");
    overlay.id = "lumina-screenshot-region-overlay";
    overlay.style.cssText = [
      "position:fixed",
      "inset:0",
      "z-index:2147483647",
      "cursor:crosshair",
      "background:rgba(12,18,32,0.18)",
      "user-select:none",
      "touch-action:none",
    ].join(";");

    const hint = document.createElement("div");
    hint.textContent = "拖拽选择截图区域，松开后点击确认";
    hint.style.cssText = [
      "position:fixed",
      "top:18px",
      "left:50%",
      "transform:translateX(-50%)",
      "padding:9px 12px",
      "border-radius:10px",
      "background:rgba(12,18,32,0.88)",
      "color:#fff",
      "font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      "box-shadow:0 10px 28px rgba(0,0,0,0.22)",
      "pointer-events:none",
    ].join(";");

    const box = document.createElement("div");
    box.style.cssText = [
      "position:fixed",
      "display:none",
      "border:2px solid #4f8cff",
      "background:rgba(79,140,255,0.16)",
      "box-shadow:0 0 0 9999px rgba(12,18,32,0.38)",
      "pointer-events:none",
    ].join(";");

    const toolbar = document.createElement("div");
    toolbar.style.cssText = [
      "position:fixed",
      "display:none",
      "z-index:2147483647",
      "gap:8px",
      "align-items:center",
      "padding:8px",
      "border-radius:12px",
      "background:rgba(12,18,32,0.92)",
      "box-shadow:0 14px 32px rgba(0,0,0,0.28)",
    ].join(";");

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.textContent = "确认截图";
    confirmButton.style.cssText = screenshotRegionButtonStyle("#4f8cff", "#fff");

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "取消";
    cancelButton.style.cssText = screenshotRegionButtonStyle("rgba(255,255,255,0.12)", "#fff");

    toolbar.append(confirmButton, cancelButton);

    overlay.append(hint, box, toolbar);
    document.documentElement.appendChild(overlay);

    let startX = 0;
    let startY = 0;
    let currentRect = null;
    let drawing = false;
    let readyToConfirm = false;

    const cleanup = () => {
      overlay.removeEventListener("pointerdown", onPointerDown, true);
      overlay.removeEventListener("pointermove", onPointerMove, true);
      overlay.removeEventListener("pointerup", onPointerUp, true);
      overlay.removeEventListener("pointercancel", onPointerCancel, true);
      confirmButton.removeEventListener("click", onConfirmClick, true);
      cancelButton.removeEventListener("click", onCancelClick, true);
      document.removeEventListener("keydown", onKeyDown, true);
      overlay.remove();
    };

    const finish = () => {
      if (!currentRect || currentRect.width < 8 || currentRect.height < 8) {
        hint.textContent = "截图区域过小，请重新拖拽选择";
        toolbar.style.display = "none";
        box.style.display = "none";
        currentRect = null;
        readyToConfirm = false;
        return;
      }

      cleanup();
      resolve({
        title: getDocumentTitle(),
        url: window.location.href,
        siteName: getSiteName(),
        capturedAt: new Date().toISOString(),
        captureKind: "selected_region",
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio || 1,
        region: currentRect,
      });
    };

    const showToolbar = () => {
      if (!currentRect || currentRect.width < 8 || currentRect.height < 8) {
        finish();
        return;
      }

      readyToConfirm = true;
      hint.textContent = "确认截图，或重新拖拽选择区域";
      const toolbarWidth = 156;
      const toolbarHeight = 42;
      const left = clamp(currentRect.x + currentRect.width - toolbarWidth, 8, window.innerWidth - toolbarWidth - 8);
      const below = currentRect.y + currentRect.height + 10;
      const above = currentRect.y - toolbarHeight - 10;
      const top = below + toolbarHeight < window.innerHeight ? below : clamp(above, 8, window.innerHeight - toolbarHeight - 8);
      toolbar.style.left = `${left}px`;
      toolbar.style.top = `${top}px`;
      toolbar.style.display = "flex";
    };

    const updateBox = (clientX, clientY) => {
      const x1 = clamp(startX, 0, window.innerWidth);
      const y1 = clamp(startY, 0, window.innerHeight);
      const x2 = clamp(clientX, 0, window.innerWidth);
      const y2 = clamp(clientY, 0, window.innerHeight);
      const left = Math.min(x1, x2);
      const top = Math.min(y1, y2);
      const width = Math.abs(x2 - x1);
      const height = Math.abs(y2 - y1);
      currentRect = { x: left, y: top, width, height };
      box.style.display = "block";
      box.style.left = `${left}px`;
      box.style.top = `${top}px`;
      box.style.width = `${width}px`;
      box.style.height = `${height}px`;
    };

    function onPointerDown(event) {
      if (toolbar.contains(event.target)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      drawing = true;
      readyToConfirm = false;
      toolbar.style.display = "none";
      hint.textContent = "拖拽选择截图区域，松开后点击确认";
      startX = event.clientX;
      startY = event.clientY;
      overlay.setPointerCapture?.(event.pointerId);
      updateBox(event.clientX, event.clientY);
    }

    function onPointerMove(event) {
      if (!drawing) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      updateBox(event.clientX, event.clientY);
    }

    function onPointerUp(event) {
      if (!drawing) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      drawing = false;
      updateBox(event.clientX, event.clientY);
      showToolbar();
    }

    function onPointerCancel() {
      cleanup();
      reject(new Error("截图选择已取消。"));
    }

    function onKeyDown(event) {
      if (event.key === "Enter" && readyToConfirm) {
        event.preventDefault();
        event.stopPropagation();
        finish();
        return;
      }

      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      cleanup();
      reject(new Error("截图选择已取消。"));
    }

    function onConfirmClick(event) {
      event.preventDefault();
      event.stopPropagation();
      finish();
    }

    function onCancelClick(event) {
      event.preventDefault();
      event.stopPropagation();
      cleanup();
      reject(new Error("截图选择已取消。"));
    }

    overlay.addEventListener("pointerdown", onPointerDown, true);
    overlay.addEventListener("pointermove", onPointerMove, true);
    overlay.addEventListener("pointerup", onPointerUp, true);
    overlay.addEventListener("pointercancel", onPointerCancel, true);
    confirmButton.addEventListener("click", onConfirmClick, true);
    cancelButton.addEventListener("click", onCancelClick, true);
    document.addEventListener("keydown", onKeyDown, true);
  });
}

function screenshotRegionButtonStyle(background, color) {
  return [
    "appearance:none",
    "border:0",
    "border-radius:9px",
    "padding:8px 10px",
    `background:${background}`,
    `color:${color}`,
    "font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "font-weight:700",
    "cursor:pointer",
  ].join(";");
}

function getPageContext() {
  const selectionText = collapseWhitespace(window.getSelection()?.toString() || "");

  return {
    title: getDocumentTitle(),
    url: window.location.href,
    hasSelection: Boolean(selectionText),
    selectionPreview: selectionText.slice(0, 160),
  };
}

function extractSelectionCapture() {
  const selection = window.getSelection();
  const text = collapseWhitespace(selection?.toString() || "");

  if (!text) {
    throw new Error("请先选中文字，再执行保存。");
  }

  const range = selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
  const contextBlockText = range ? findContextBlockText(range.commonAncestorContainer) : "";
  const { contextBefore, contextAfter } = splitContextAroundSelection(contextBlockText, text);

  return {
    title: getDocumentTitle(),
    url: window.location.href,
    siteName: getSiteName(),
    text,
    contextBefore,
    contextAfter,
    capturedAt: new Date().toISOString(),
  };
}

function extractPageCapture() {
  const bestRoot = pickBestContentRoot();
  const clonedRoot = bestRoot.cloneNode(true);
  stripNoise(clonedRoot);

  const content = collapseWhitespace(clonedRoot.innerText || bestRoot.innerText || "");

  if (!content || content.length < 80) {
    throw new Error("网页正文过短，当前页面暂时无法稳定提取。");
  }

  return {
    title: getDocumentTitle(),
    url: window.location.href,
    siteName: getSiteName(),
    byline: getByline(),
    excerpt: content.slice(0, 240),
    content,
    capturedAt: new Date().toISOString(),
  };
}

function pickBestContentRoot() {
  const selectorCandidates = [
    "article",
    "main",
    "[role='main']",
    ".article",
    ".article-content",
    ".post",
    ".post-content",
    ".entry-content",
    ".content",
    ".markdown-body",
  ];

  const candidates = [];

  for (const selector of selectorCandidates) {
    const elements = document.querySelectorAll(selector);
    for (const element of elements) {
      if (element instanceof HTMLElement) {
        candidates.push(element);
      }
    }
  }

  candidates.push(document.body);

  let bestElement = document.body;
  let bestScore = -1;

  for (const candidate of dedupeElements(candidates)) {
    const score = scoreContentRoot(candidate);
    if (score > bestScore) {
      bestScore = score;
      bestElement = candidate;
    }
  }

  return bestElement;
}

function scoreContentRoot(element) {
  const cloned = element.cloneNode(true);
  stripNoise(cloned);

  const text = collapseWhitespace(cloned.innerText || "");
  const textLength = text.length;
  const paragraphCount = element.querySelectorAll("p").length;
  const headingCount = element.querySelectorAll("h1, h2, h3").length;
  const linkTextLength = Array.from(element.querySelectorAll("a"))
    .map((node) => collapseWhitespace(node.innerText || "").length)
    .reduce((sum, value) => sum + value, 0);
  const linkDensity = textLength === 0 ? 0 : linkTextLength / textLength;

  return textLength + paragraphCount * 120 + headingCount * 80 - linkDensity * 600;
}

function stripNoise(root) {
  for (const selector of NOISE_SELECTORS) {
    const nodes = root.querySelectorAll(selector);
    for (const node of nodes) {
      node.remove();
    }
  }
}

function dedupeElements(elements) {
  const seen = new Set();
  const result = [];

  for (const element of elements) {
    if (seen.has(element)) {
      continue;
    }
    seen.add(element);
    result.push(element);
  }

  return result;
}

function findContextBlockText(node) {
  const element = node instanceof Element ? node : node.parentElement;

  if (!element) {
    return "";
  }

  const block = element.closest("p, li, blockquote, td, th, article, section, main, div");
  return collapseWhitespace(block?.innerText || element.innerText || "");
}

function splitContextAroundSelection(contextText, selectionText) {
  if (!contextText || !selectionText) {
    return {
      contextBefore: "",
      contextAfter: "",
    };
  }

  const index = contextText.indexOf(selectionText);
  if (index === -1) {
    return {
      contextBefore: contextText.slice(0, 160),
      contextAfter: contextText.slice(-160),
    };
  }

  return {
    contextBefore: contextText.slice(Math.max(0, index - 160), index),
    contextAfter: contextText.slice(index + selectionText.length, index + selectionText.length + 160),
  };
}

function getDocumentTitle() {
  const ogTitle = document.querySelector("meta[property='og:title']")?.getAttribute("content");
  return collapseWhitespace(ogTitle || document.title || "Untitled page") || "Untitled page";
}

function getSiteName() {
  const metaSiteName = document.querySelector("meta[property='og:site_name']")?.getAttribute("content");
  return collapseWhitespace(metaSiteName || window.location.hostname || "");
}

function getByline() {
  const metaAuthor = document.querySelector("meta[name='author']")?.getAttribute("content");
  return collapseWhitespace(metaAuthor || "");
}

function collapseWhitespace(value) {
  return value.replace(/\s+/g, " ").trim();
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
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
