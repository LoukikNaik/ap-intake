# Deployment — UI on GitHub Pages, backend on your machine

The split:
- **Frontend** → built static files served by **GitHub Pages** (HTTPS).
- **Backend + Postgres** → run with `docker compose` on **your machine**, exposed over **HTTPS**
  via an **Nginx reverse proxy** (or a Cloudflare Tunnel).

```
  Browser ──HTTPS──> GitHub Pages (static UI)
     │
     └──HTTPS (VITE_API_URL)──> Nginx (TLS) ──> 127.0.0.1:8000 (FastAPI) ──> Postgres
                                  └ on your machine ────────────────────────────┘
```

> **Why HTTPS on the backend is mandatory:** the UI is served over HTTPS from Pages, and
> browsers block an HTTPS page from calling an `http://` API (mixed content). So the backend
> must be reachable over HTTPS — hence the Nginx TLS proxy (or a tunnel that provides TLS).

> **Why not a Cloudflare Worker (like the portfolio's API)?** The portfolio backend is a
> lightweight serverless Worker (JS + D1 + KV). This backend is **FastAPI + Postgres + the
> OpenAI Agents SDK** — Python, stateful, with multi-second agent runs — which doesn't fit the
> Worker model. So the frontend deploys exactly like the portfolio, but the backend runs on
> your machine behind Nginx (or a tunnel).

---

## 1. Push the repo

```bash
git push -u origin main
```

## 2. Frontend → GitHub Pages

This mirrors the proven `loukik.dev` portfolio setup: build → push to the `gh-pages` branch
(via `JamesIves/github-pages-deploy-action`), with a `404.html` SPA fallback and an optional
custom-domain `CNAME`.

1. Repo **Settings → Secrets and variables → Actions → Variables**, add:
   - `VITE_API_URL` = backend's public HTTPS URL, e.g. `https://ap-api.loukik.dev`
   - `VITE_BASE` = `"/"` if using a custom domain, or `"/<repo-name>/"` for a project site.
   - `VITE_CNAME` *(optional)* = custom domain, e.g. `ap.loukik.dev`. Leave unset to use
     `user.github.io/<repo>/`.
2. Push to `main` (or run the workflow manually). The workflow builds, copies `index.html` →
   `404.html`, writes `CNAME` if set, and deploys to the `gh-pages` branch.
3. Repo **Settings → Pages → Source: Deploy from a branch → `gh-pages` / root**. (If using a
   custom domain, also set it under Settings → Pages and add the DNS record per GitHub's docs.)

Routing note: the UI uses **clean URLs (BrowserRouter)**. Deep links and refreshes work on
Pages because the workflow copies `index.html` to `404.html` — Pages serves that for unknown
paths, the SPA boots, and the router takes over. (Same trick as the portfolio; no hash router.)

## 3. Backend → your machine, exposed over HTTPS

Run it:
```bash
cp .env.example .env       # set OPENAI_API_KEY and CORS_ORIGINS (see step 4)
docker compose up --build  # backend on 127.0.0.1:8000, Postgres alongside
```

Then expose it over HTTPS. **Two options:**

### Option A — Nginx + Let's Encrypt (you have a domain + can port-forward)
1. Point a DNS A record (e.g. `api.yourdomain.com`) at your machine's public IP.
2. Forward router ports **80** and **443** to your machine.
3. Install Nginx, copy `deploy/nginx.conf` to `/etc/nginx/sites-available/ap-intake`
   (edit `server_name`), symlink into `sites-enabled`, then:
   ```bash
   sudo certbot --nginx -d api.yourdomain.com   # issues + wires up TLS
   sudo nginx -t && sudo systemctl reload nginx
   ```
   Nginx now terminates HTTPS and proxies to `127.0.0.1:8000`.

### Option B — Cloudflare Tunnel (no port-forward, no cert wrangling)
```bash
cloudflared tunnel --url http://localhost:8000
```
This prints a public `https://…trycloudflare.com` URL (or bind a named tunnel to your own
hostname). Use that as `VITE_API_URL`. No Nginx/cert needed — the tunnel provides TLS.

## 4. CORS — let the UI's origin call the API

In your machine's `.env`, add the Pages origin to `CORS_ORIGINS`:
```
CORS_ORIGINS=http://localhost:5173,https://<user>.github.io
```
Restart the backend (`docker compose up -d backend`). CORS is enforced by the FastAPI app; do
**not** also add CORS headers in Nginx (that double-sets them).

## 5. Verify

- `curl https://api.yourdomain.com/health` → `{"status":"ok",...}`
- Open `https://<user>.github.io/<repo>/`, upload an invoice, confirm it processes.

---

## Notes / caveats

- **Postgres is never exposed** — it stays on the docker network; only the backend talks to it.
- **Your machine must be on** for the API to answer; Pages (the UI) is always up.
- The free `trycloudflare.com` URL changes each run — use a **named tunnel** or a real domain
  for a stable `VITE_API_URL`.
- Secrets: `.env` is gitignored. The OpenAI key lives only on your machine, never in the repo
  or the Pages build (the UI only knows `VITE_API_URL`).
