# Hachi Assistant integration note

This Chrome Manifest V3 extension is the MVP web clipper for Hachi_Assistant.

Location:

- `hachi_mvp/extensions/chrome-web-clipper-mvp`

Validation:

```bash
cd /Users/appa/Hachi_Assistant/hachi_mvp
./scripts/validate_chrome_extension.sh
```

Load in Chrome:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `hachi_mvp/extensions/chrome-web-clipper-mvp`

Default backend target:

- `http://127.0.0.1:8008`
- selection endpoint: `/api/knowledge/text`
- page endpoint: `/api/knowledge/page`
- screenshot endpoint: `/api/knowledge/screenshot`
