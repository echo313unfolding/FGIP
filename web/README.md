# FGIP Web Dashboard

Flask/FastAPI web application for graph visualization and management.

## Overview

Full-featured dashboard with:
- Interactive graph visualization (Cytoscape.js)
- Analytics charts (Chart.js)
- Thesis scoring display
- Proposal approval interface
- System health monitoring

## Quick Start

```bash
python3 web/app.py
# Open http://localhost:5000
```

## Directory Structure

```
web/
├── app.py              # Main Flask application (40KB)
├── static/
│   ├── css/            # Stylesheets
│   ├── img/            # Images
│   └── js/             # JavaScript
└── templates/
    └── index.html      # Main dashboard template (79KB)
```

## API Endpoints

### Graph

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/graph` | GET | Get graph data for visualization |
| `/api/node/{id}` | GET | Get node details |
| `/api/search` | GET | Search nodes |

### Stats

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/stats` | GET | Graph statistics |
| `/api/health` | GET | System health |

### Risk & Analysis

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/risk/thesis` | GET | Thesis confidence score |
| `/api/both-sides` | GET | Both-sides patterns |
| `/api/scenarios` | GET | Economic scenarios |

### Approvals

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/approvals` | GET | List pending proposals |
| `/api/approvals/approve` | POST | Approve proposals |
| `/api/approvals/reject` | POST | Reject proposals |
| `/api/approvals/bulk-approve` | POST | Bulk approve by criteria |

## Dashboard Tabs

### Graph Tab

- Interactive force-directed graph
- Node type filtering
- Layout options (Force, Hierarchy, Circle, Grid)
- Node detail panel
- Export to PNG/JSON

### Analytics Tab

- Node types distribution (doughnut)
- Edge types distribution (bar)
- Source tiers breakdown (pie)
- Problem vs Correction edges

### Thesis Tab

- Thesis confidence score (0-100)
- Factor breakdown
- Both-sides entity detection

### Approvals Tab

- Pending proposals list
- Evidence preview
- Approve/reject actions
- Bulk operations

### Health Tab

- Database status
- Coverage gaps
- Verification status
- Agent recommendations

## Styling

Dark theme consistent with FGIP:

```css
--bg-primary: #0a0a0f
--bg-secondary: #12121a
--accent: #00ff88
--danger: #ff4757
```

## Dependencies

Frontend (CDN):
- Cytoscape.js 3.27.0
- Chart.js 4.4.1
- Dagre layout plugin

Backend:
- Flask
- sqlite3

## Configuration

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `FGIP_DB` | `fgip.db` | Database path |
| `PORT` | `5000` | Server port |

## See Also

- `echo_gateway/` — Chat interface (port 7777)
- `echo_ui/` — Chat frontend
- `fgip/cli.py` — CLI alternative
