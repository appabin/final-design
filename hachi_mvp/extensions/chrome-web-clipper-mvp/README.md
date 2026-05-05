# Lumina Web Clipper MVP

A minimal Chrome Manifest V3 extension that captures selected text, readable page content, or a user-selected screenshot region and posts it to a knowledge backend.

## Included MVP flows

- Save selected text with surrounding context
- Save the readable body of the current page
- Draw a screenshot region for backend visual analysis
- Configure the backend URL and bearer token in an options page
- Retry the most recent failed upload from the popup

## Load the extension in Chrome

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this folder: `extensions/chrome-web-clipper-mvp`.

## Validate the extension files

Run this from the repository root:

```bash
npm run extension:validate
```

## Default backend settings

- API base URL: `http://127.0.0.1:8008`
- Selection endpoint: `/api/knowledge/text`
- Page endpoint: `/api/knowledge/page`
- Screenshot endpoint: `/api/knowledge/screenshot`

If the page endpoint returns `404` or `405`, the extension automatically falls back to the selection endpoint and sends the readable page text there.

## Payload shapes

### Selection capture

```json
{
  "title": "Page title",
  "text": "Selected text",
  "url": "https://example.com/article",
  "source_type": "selection",
  "metadata": {
    "site_name": "example.com",
    "captured_at": "2026-03-25T09:30:00.000Z",
    "context_before": "Text before the selection",
    "context_after": "Text after the selection",
    "capture_tool": "lumina-web-clipper-mvp"
  }
}
```

### Page capture

```json
{
  "title": "Page title",
  "url": "https://example.com/article",
  "content": "Readable page text",
  "excerpt": "First 240 chars",
  "source_type": "page",
  "metadata": {
    "site_name": "example.com",
    "captured_at": "2026-03-25T09:30:00.000Z",
    "byline": "Author name",
    "capture_tool": "lumina-web-clipper-mvp"
  }
}
```

### Screenshot capture

```json
{
  "title": "截图：Page title",
  "url": "https://example.com/article",
  "image_data_url": "data:image/jpeg;base64,...",
  "metadata": {
    "captured_at": "2026-03-25T09:30:00.000Z",
    "capture_kind": "selected_region",
    "region": { "x": 24, "y": 96, "width": 480, "height": 320 },
    "capture_tool": "lumina-web-clipper-mvp"
  }
}
```

## Limits

- Browser-internal pages such as `chrome://` do not allow content capture.
- Readable page extraction uses DOM heuristics, not Mozilla Readability.
- Screenshot capture stores the model-generated text analysis, not the raw image bytes.
