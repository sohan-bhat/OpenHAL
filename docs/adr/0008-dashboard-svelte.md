# 0008 Dashboard is Svelte 5 with Vite, served by the hub

## Context

The dashboard renders device pages generated from device files, live values over WebSockets, the stop control, the confirmation queue, the audit log, routines and the driver writer interview. It ships inside the Python package.

## Options considered

1. React with Vite. Large ecosystem, heavier runtime.
2. Svelte 5 with Vite. Small compiled output, fine-grained reactivity that suits many live values, simple stores for WebSocket state.
3. Server-rendered HTML with htmx. Less build tooling, weaker for live sparklines and generated controls.

## Decision

Svelte 5 with Vite and TypeScript. The production build is copied into `openhal/hub/static/` and served by FastAPI at `/`. Development uses the Vite dev server with a proxy to the hub.

## Consequences

No component library. The look comes from docs/DESIGN.md and shared design tokens in `design/tokens.css`, which the website imports too.
