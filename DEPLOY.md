# Deploying to Render (free tier) — step by step

This guide deploys the whole app as **one free Docker web service** on Render:
the FastAPI backend serves both the API (`/api/*`) **and** the compiled React
app, from a single HTTPS origin.

> **Why one service / why Docker?**
> The frontend calls a relative `/api` and the OAuth session cookie is
> `SameSite=Lax`, so the API and the UI must share an origin (a separate static
> site would break login). And Render's *Python* runtime has no Node.js, so the
> Vite frontend must be built in a Docker stage. Hence: one Docker web service.

---

## Files this repo now ships for deployment

| File | Purpose |
|------|---------|
| `backend/requirements.txt` | Python deps the Docker build installs |
| `Dockerfile` | Stage 1 builds `frontend/dist`; stage 2 runs FastAPI and serves it |
| `.dockerignore` | Keeps `.venv`, `node_modules`, secrets and working DBs out of the image |
| `render.yaml` | Optional "Blueprint" (one-click infra-as-code) |
| `.gitignore` | Keeps secrets/`.venv`/`node_modules`/working DBs out of git |

> The DuckDB **seed** databases `backend/data/*_src.duckdb` **must be committed**
> — they are the data the app serves. `.gitignore` keeps only the generated
> working copies out.

---

## Prerequisites

1. A **GitHub** account (Render deploys from a repo).
2. A **Render** account — sign up at <https://render.com> (free; a card is
   required for identity verification but the *Free* instance type is $0).
3. Your **Google OAuth** client id/secret (already in `backend/.env`).
4. `git` installed locally.

---

## Step 1 — Put the project on GitHub

From `c:\webapp` (run in Git Bash / PowerShell with git installed):

```bash
cd c:/webapp
git init
git add .
git status            # sanity check: backend/.env must NOT be listed
git commit -m "Retail Analytics Command Center"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

If `git status` shows `backend/.env`, **stop** — it must stay ignored (it holds
your Google secret). The `.env.example` file is fine to commit.

---

## Step 2 — Create the Render service

### Option A — Blueprint (uses `render.yaml`, recommended)

1. Render dashboard → **New +** → **Blueprint**.
2. Pick your repo → **Apply**. Render reads `render.yaml`, prompts for the three
   `sync: false` secrets (Google client id/secret/redirect URI), then builds.

### Option B — Manual Web Service

1. **New +** → **Web Service** → connect your repo.
2. Settings:
   - **Name:** `retail-analytics` (this becomes the URL prefix)
   - **Language / Runtime:** **Docker**
   - **Dockerfile Path:** `./Dockerfile`
   - **Instance Type:** **Free**
   - **Health Check Path:** `/api/health`
   - **Auto-Deploy:** **Yes**
3. Leave Build/Start commands blank — the Dockerfile controls them.

---

## Step 3 — Environment variables

In **Service → Environment**, add (Option A already sets these):

| Key | Value |
|-----|-------|
| `AUTH_SECRET_KEY` | a long random string (Blueprint generates one) |
| `ENVIRONMENT` | `production`  *(makes the session cookie `secure`/HTTPS-only)* |
| `INITIAL_ADMIN_EMAIL` | `mis@adonisgroup.in` *(first admin auto-created)* |
| `GOOGLE_CLIENT_ID` | from `backend/.env` |
| `GOOGLE_CLIENT_SECRET` | from `backend/.env` |
| `GOOGLE_REDIRECT_URI` | `https://<your-service>.onrender.com/api/auth/callback` |
| `CORS_ORIGINS` | `*` |

> `PORT` is injected by Render automatically — do **not** set it. `APP_DATA_DIR`
> and `AUTH_DB_PATH` also have working defaults and can be left unset.

---

## Step 4 — Deploy and copy your URL

Trigger **Manual Deploy → Deploy latest commit** (or it auto-runs after Step 2).
When the log ends with `Application startup complete`, open:

```
https://<your-service>.onrender.com/api/health
```

You should see `{"status":"ok","app":"Retail Analytics Command Center"}`.

---

## Step 5 — Point Google OAuth at the new URL

In <https://console.cloud.google.com> → **APIs & Services → Credentials** →
your OAuth 2.0 Client ID:

- **Authorized redirect URIs** → add
  `https://<your-service>.onrender.com/api/auth/callback`
- **Authorized JavaScript origins** → add
  `https://<your-service>.onrender.com`
- **Save**.

Make sure Render's `GOOGLE_REDIRECT_URI` is **exactly** the same callback URL
(Google compares it character-for-character).

---

## Step 6 — Verify

1. Open `https://<your-service>.onrender.com` → redirected to **/login**.
2. **Sign in with Google** using an allowed email (the bootstrapped admin, or a
   user an admin added).
3. Check the pages: Dashboard, **Secondary Sales Analysis**, Tertiary, Store
   Master, SQL Platform.
4. Confirm a known KPI, e.g. Secondary → filter Retailer = **BSC DAVANGERE** →
   KPI **TRENDING (Proj. Full Year)** ≈ **₹24.49 Cr** and **PROJ. GROWTH %** ≈
   **+56.2%** (the values from the trending-method change).

---

## How to deploy an update

Render watches your repo's branch and (`autoDeploy: true`) rebuilds on every
push:

```bash
# 1. make your changes locally + run the tests
cd c:/webapp/backend && ./.venv/Scripts/python -m pytest tests -q
cd c:/webapp/frontend && npm run build

# 2. commit and push
cd c:/webapp
git add .
git commit -m "Describe the change"
git push
```

Render then: pulls the commit → runs the Dockerfile → **restarts** the service.
Watch progress in **Service → Logs** (a new "Deploy" line appears in
**Events**). No manual step needed.

**Manual re-deploy** (no push): Service → **Manual Deploy** →
- *Deploy latest commit* — normal redeploy.
- *Clear build cache & deploy* — use after changing `requirements.txt` or
  `package.json`.

**Changing an env var:** edit it and click **Save** — Render redeploys
automatically.

---

## Free-tier limits you should know

| Limit | Effect |
|-------|--------|
| **Spins down after 15 min idle** | First request after idling is slow (~30–60 s cold start); later requests are fast. |
| **Ephemeral disk** | `backend/data/auth.sqlite` resets on every deploy/restart. Runtime-added users are lost; the `INITIAL_ADMIN_EMAIL` admin is re-created automatically. |
| **512 MB RAM / shared CPU** | Fine for this dataset (~11 MB DuckDB). A very heavy SQL Platform query can be slow. |
| **No persistent disks on Free** | To keep auth/users or DB edits across deploys you need a paid instance + a disk mounted at e.g. `/var/data`, then set `AUTH_DB_PATH=/var/data/auth.sqlite` and `APP_DATA_DIR=/var/data`. |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Build fails at `npm ci` | Delete `frontend/package-lock.json` from git and re-push, or change the Dockerfile `npm ci` to `npm install`. |
| Build fails at `pip install` | A wheel has no CPython 3.12 Linux build — adjust the pin in `backend/requirements.txt`. |
| Deploy OK but `/` 404s | `frontend/dist` wasn't produced — check the frontend build stage logs. |
| Login → `unauthorized_email` | The Google account isn't in the users table. The `INITIAL_ADMIN_EMAIL` admin is auto-created; add others from the Admin screen. |
| Login → `redirect_uri_mismatch` | Step 5's redirect URI ≠ `GOOGLE_REDIRECT_URI`. They must match exactly. |
| Login loops back to `/login` | `ENVIRONMENT=production` but you're on `http://` — the `secure` cookie is dropped. Always use the `https://` URL. |
| `/api/health` 502 for a minute | Cold start after idle; wait and retry. |

---

## Alternative (no Docker): pre-built frontend + Python service

If you would rather not use Docker:

1. Build locally once: `cd frontend && npm run build`.
2. **Commit `frontend/dist`** (remove it from `.gitignore`) so it ships in the repo.
3. Render → **Web Service** → Runtime **Python 3**:
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add the same env vars as Step 3.
4. Remember to **rebuild + recommit `frontend/dist` on every frontend change**
   (the reason Docker is recommended).


