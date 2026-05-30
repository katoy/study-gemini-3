---
name: Agentic
colors:
  primary: "#FF5701"
  secondary: "#F6F6F1"
  success: "#16A34A"
  warning: "#D97706"
  danger: "#DC2626"
  surface: "#FFFFFF"
  text: "#111827"
  neutral: "#FFFFFF"
typography:
  h1:
    fontFamily: "Playfair Display"
    fontSize: 2.5rem
  body-md:
    fontFamily: "Playfair Display"
    fontSize: 1rem
  label-caps:
    fontFamily: "JetBrains Mono"
    fontSize: 0.875rem
  sourceScale: "14/16/18/24/32/40"
  weights: "100, 200, 300, 400, 500, 600, 700, 800, 900"
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
  sourceScale: "8pt baseline grid"
---

## Overview

Conversational AI-first interface with minimal controls, clear outcomes, and delegated task flows for agentic workflows.

## Style Foundations

- **Visual style:** modern, bold
- **Typography scale:** 14/16/18/24/32/40
- **Typography fonts:** primary=Playfair Display, display=Playfair Display, mono=JetBrains Mono
- **Typography weights:** 100, 200, 300, 400, 500, 600, 700, 800, 900
- **Color palette:** surface/subtle layers
- **Spacing scale:** 8pt baseline grid

## Colors

- **Primary (#FF5701):** Token from style foundations.
- **Secondary (#F6F6F1):** Token from style foundations.
- **Success (#16A34A):** Token from style foundations.
- **Warning (#D97706):** Token from style foundations.
- **Danger (#DC2626):** Token from style foundations.
- **Surface (#FFFFFF):** Token from style foundations.
- **Text (#111827):** Token from style foundations.
- **Neutral (#FFFFFF):** Derived from the surface token for official format compatibility.

---

## Architecture (2026-05-30 Update)

### Code Structure - routes.py モジュール分割完了

**Status**: 243/254 tests passing (95.7%) | Coverage: 98.32%

```
app/routes/
├── _shared.py      (113 lines) - Shared imports, constants, helpers
├── html.py          (82 lines) - HTML response endpoints
├── internal.py     (106 lines) - Internal APIs (/api/download, /cache, /settings)
├── api_v1.py       (113 lines) - REST API v1 (/api/v1/*)
├── ws.py            (18 lines) - WebSocket (/ws/jobs)
└── __init__.py       (9 lines) - Router assembly
```

### Module Responsibilities

**_shared.py (Common Layer)**
- Central re-export point for all testable functions
- FastAPI Depends() functions for dependency injection
- Helper functions for genre filtering, data transformation
- All test mocks target this module via `patch("app.routes._shared.*")`

**html.py (HTML Endpoints)**
- Templates rendered with htmx for progressive enhancement
- Stateful UI: `data-open` attributes, DL buttons with `data-program`/`data-episode`
- Endpoints: GET /, /programs, /programs/{id}/episodes, POST /download*

**internal.py (Internal APIs)**
- `/api/download/*` - job status polling, cancellation, file download
- `/api/episodes/*/file` - downloaded episode file retrieval
- `/api/cache/clear` - cache management
- `/api/settings` - storage limit config
- `/api/jobs/recent` - job activity panel
- Returns HTML fragments for htmx SWAP

**api_v1.py (REST API)**
- Full REST API (GET /api/v1/genres, /programs, /episodes, /download-jobs, /settings, /cache/status)
- Pydantic response models from api_models.py
- JSON responses for client applications

**ws.py (WebSocket)**
- Real-time download progress streaming via pub/sub pattern

### Testing Strategy

**Mock Unification**
- All mockable functions re-exported via `__all__` in _shared.py
- All tests patch at import location: `patch("app.routes._shared.function_name")`
- State reset in setUp/tearDown to prevent test interference

**Remaining Issues** (11 failures, 4.3%)
- FastAPI dependency injection caching + unittest.mock interaction
- Primarily episode endpoint mocks in test_routes.py
- Root cause: Depends() functions cache results across test cases
- Solution: Requires deeper investigation into FastAPI's request/dependency scoping
