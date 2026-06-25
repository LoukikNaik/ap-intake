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

---

## 1. Push the repo

```bash
git push -u origin main
```

## 2. Frontend → GitHub Pages

1. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Repo **Settings → Secrets and variables → Actions → Variables**, add:
   - `VITE_API_URL` = your backend's public HTTPS URL, e.g. `https://api.yourdomain.com`
   - `VITE_BASE` = `"/<repo-name>/"` for a project site (`user.github.io/<repo>/`), or `"/"`
     for a user/org site (`user.github.io`).
3. Push to `main` (or run the workflow manually). The **Deploy frontend** workflow builds and
   publishes. The app appears at `https://<user>.github.io/<repo>/`.

Routing note: the UI uses a **hash router** (`/#/bills/1`), so deep links and refreshes work on
Pages without any SPA-fallback server config.

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
