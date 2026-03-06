# Echo UI

Browser-based chat interface for the Echo Gateway.

## Overview

Single-file HTML/CSS/JS chat interface with dark theme matching FGIP styling.

## File

```
echo_ui/
└── index.html    # Complete chat UI (HTML + embedded CSS + JS)
```

## Features

- Dark theme (--bg-primary: #0a0a0f, --accent: #00ff88)
- Real-time chat with typing indicator
- Tool call visualization (expandable panels)
- Health status indicator
- Suggested queries on welcome screen

## Usage

Served by Echo Gateway at `http://localhost:7777/`:

```bash
make echo-ui
# Open http://localhost:7777 in browser
```

## API Integration

The UI communicates with Echo Gateway via:

```javascript
// Unified task endpoint
POST /v1/task
{
  "task_type": "chat",
  "payload": { "messages": [...] },
  "require_kat": false
}
```

## Styling

CSS variables for theming:

```css
:root {
    --bg-primary: #0a0a0f;
    --bg-secondary: #12121a;
    --bg-tertiary: #1a1a25;
    --border: #2a2a3a;
    --text-primary: #e0e0e0;
    --text-secondary: #888;
    --accent: #00ff88;
    --accent-dim: #00cc6a;
    --danger: #ff4757;
    --warning: #ffaa00;
    --info: #4da6ff;
}
```

## Suggested Queries

Default suggestions on welcome screen:

- "Search for Intel"
- "Graph stats"
- "CHIPS Act connections"
- "Lobbying relationships"

## See Also

- `echo_gateway/` — Backend server
- `web/templates/index.html` — Full FGIP dashboard UI (different from chat)
