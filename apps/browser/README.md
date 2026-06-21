# Routely Browser IDE

Try Routely in the browser — React + Monaco editor.

## Dev

```bash
npm install
npm run dev
```

Runs on http://localhost:5173 and proxies API calls to `http://localhost:8000`.

Start the Routely API first (`docker compose up` from repo root).

## Env

| Variable | Default |
|----------|---------|
| `VITE_ROUTELY_API_URL` | empty (use Vite proxy in dev) |

## Build

```bash
npm run build
```

Deploy `dist/` to `app.routely.aitotech.in` (static host or CDN).
