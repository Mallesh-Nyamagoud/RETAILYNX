# Deploying RETAILYNX to Google Cloud Run

A complete, beginner-friendly walkthrough: **budget alert → APIs → Postgres →
secrets → Cloud Run → test → update → shut down**.

> **You will not run any deploy command as part of this repository's setup.**
> Everything below is what *you* run when you choose to deploy.

RETAILYNX ships as **one container image**: the FastAPI backend serves both the
JSON API (`/api/*`) and the compiled React app, so browser requests are always
same-origin (required for the `SameSite=Lax` session cookie).

| Setting | Value used in this guide |
|---|---|
| Region | `asia-south1` (Mumbai) |
| Memory / CPU | **2 GiB / 1 CPU** |
| Min / max instances | **0 / 1** (0 = scale to zero = no idle cost) |
| Authentication | **Allow unauthenticated** (Cloud Run IAM off; the app has its own login) |
| User database | **External Postgres** (Cloud Run disk is temporary) |
| Container port | `8080` (Cloud Run sets `$PORT`) |

---

## 0. Before you start

1. A **Google account** and a **billing account** on
   <https://console.cloud.google.com>.
   Cloud Run's free tier is generous, but Cloud SQL / Artifact Registry need
   billing enabled even for tiny usage.
2. **Docker Desktop** installed *if* you want to test the image locally
   (optional — Cloud Run can build from your GitHub repo).
3. Your code **pushed to GitHub** (see Part D / the end of this document).
4. Install the gcloud CLI: <https://cloud.google.com/sdk/docs/install>
   Then, in a terminal:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

> Replace `YOUR_PROJECT_ID` everywhere below. Pick one **region** (`asia-south1`)
> and stay in it — cross-region traffic is slower and costs more.

---

## 1. Set a billing budget alert FIRST (so nothing runs away)

1. Console → search **"Billing"** → **Budgets & alerts** → **Create budget**.
2. **Name:** `retailynx-monthly`.
3. **Scope:** leave as *All projects* (or pick just this project).
4. **Amount:** *Specified amount* → e.g. **₹500 / $5**.
5. **Thresholds:** 50% · 90% · 100% *(percent of budget)*.
6. **Notifications:** tick **Email alerts to billing admins and users** and make
   sure your address is listed. Save.

Optional belt-and-braces guard: **Cloud Run → your service → Edit → Maximum
instances = 1** (already set below) plus **Cloud SQL → Edit → small tier** means
the worst case is a few rupees a day, not hundreds.

---

## 2. Enable the required APIs

Console → **APIs & Services → Library**, and enable each of:

* **Cloud Run Admin API**
* **Cloud Build API**
* **Artifact Registry API**
* **Secret Manager API**
* **Cloud SQL Admin API** *(only if you use Cloud SQL for Postgres)*

Or do it all in one command:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com
```

---

## 3. Create the external Postgres database

The container's disk is **wiped** on every deploy, restart and scale event.
Accounts (and every password reset) must therefore live in an external
database. The app supports **any** Postgres via `DATABASE_URL`, including
Neon / Supabase / ElephantSQL. Pick ONE option.

### Option A — Cloud SQL for PostgreSQL (inside GCP, easiest to keep private)

1. Console → **SQL** → **Create instance** → **PostgreSQL**.
2. **Instance ID:** `retailynx-db`
3. **Password:** set a strong password for the `postgres` user (save it).
4. **Region:** `asia-south1` — **the same region as Cloud Run**.
5. **Edition / preset:** *Enterprise* → **Development / Sandbox** (the smallest
   shared-core machine, ~1 vCPU / 3.75 GB) — this is the cheap choice.
6. **Connections → Networking:** *Public IP* is simplest to start. Under
   **Add a network** you can leave it default for now (Cloud Run connects over
   the private Cloud SQL connector, not the public IP).
7. **Create instance** (takes a few minutes).
8. When it is ready: **Databases** → **Create database** → name `retailynx`.
9. Open **SQL → retailynx-db → Overview** and copy the **Connection name**
   (looks like `project:asia-south1:retailynx-db`). You need it in step 5.

```bash
# Or from the CLI:
gcloud sql instances create retailynx-db \
  --database-version=POSTGRES_16 \
  --region=asia-south1 \
  --tier=db-f1-micro \
  --storage-size=10GB
gcloud sql databases create retailynx --instance=retailynx-db
gcloud sql users set-password postgres --instance=retailynx-db --password='YOUR-DB-PASSWORD'
gcloud sql instances describe retailynx-db --format='value(connectionName)'
```

### Option B — Free hosted Postgres (Neon / Supabase — no Cloud SQL cost)

Create a free Postgres at <https://neon.tech> (or supabase.com), then take the
**connection string** it gives you and add `?sslmode=require`:

```
postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
```

That is your `DATABASE_URL` in step 4. No Cloud SQL instance, no Cloud SQL cost
— but it lives outside your GCP project.

---

## 4. Generate the secrets and store them in Secret Manager

The app **refuses to start** if `SESSION_SECRET_KEY`, `ADMIN_USERNAME` or
`ADMIN_PASSWORD` is missing (and, with `ENVIRONMENT=production`, also
`DATABASE_URL` **and** `DATA_DIR`) — so a half-configured revision fails
immediately and loudly instead of running broken.

Generate two random values (one for the session cookie, one for the admin
password):

```bash
# Linux / macOS / Git Bash
openssl rand -hex 32     # -> session secret
openssl rand -base64 24  # -> admin password

# Windows PowerShell
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))"
```

Now create one secret per variable. **Never put a real secret in a file that is
committed to git.**

```bash
# SESSION_SECRET_KEY - signs the session cookie (changing it logs everyone out)
printf '%s' 'PASTE-SESSION-SECRET-HERE' | \
  gcloud secrets create SESSION_SECRET_KEY --data-file=- --replication-policy=automatic

# ADMIN_PASSWORD - password for the first ADMIN created on startup
printf '%s' 'PASTE-ADMIN-PASSWORD-HERE' | \
  gcloud secrets create ADMIN_PASSWORD --data-file=- --replication-policy=automatic

# DATABASE_URL - the Postgres connection string from step 3
printf '%s' 'postgresql://USER:PASSWORD@HOST:5432/retailynx?sslmode=require' | \
  gcloud secrets create DATABASE_URL --data-file=- --replication-policy=automatic
```

`ADMIN_USERNAME` is not sensitive, but keeping every variable in one place is
tidier:

```bash
printf '%s' 'your-admin-username' | \
  gcloud secrets create ADMIN_USERNAME --data-file=- --replication-policy=automatic
```

To change a secret later (creates a new version; Cloud Run picks it up on the
next deploy):

```bash
printf '%s' 'NEW-VALUE' | gcloud secrets versions add ADMIN_PASSWORD --data-file=-
```

> The first admin is created **only while no admin exists**. Re-deploying with a
> different `ADMIN_PASSWORD` will *not* change an existing admin's password —
> use the **User Access** screen in the app for that.

---

## 5. Create the Cloud Run service from GitHub

This is the "connect my repo" route, so every `git push` can redeploy.

1. Console → **Cloud Run** → **Create service**.
2. **Source:** *Continuously deploy from a repository (source or function)* →
   **Set up with Cloud Build**.
3. **Repository provider:** *GitHub* → authorize → pick
   **`Mallesh-Nyamagoud/RETAILYNX`** and the **`main`** branch.
   **Build type:** *Dockerfile* (path `Dockerfile`, context `/`).
4. **Service name:** `retailynx`
5. **Region:** `asia-south1`
6. **Authentication:** **Allow unauthenticated invocations**
   *(the app has its own username/password login; Cloud Run IAM would sit in
   front of it and demand a Google identity instead)*
7. **Container(s), Volumes, Networking, Security** → open the dropdown:
   * **Container port:** `8080`  *(leave it; the app reads `$PORT`)*
   * **Memory:** **2 GiB**
   * **CPU:** **1**
   * **Autoscaling:** **Minimum instances `0`**, **Maximum instances `1`**
     *(min 0 = you pay nothing while idle; max 1 keeps DuckDB's memory use and
     cost predictable)*
   * **Request timeout:** `300` seconds *(heavy SQL Platform exports)*
   * **Startup CPU boost:** tick it
8. **Variables & Secrets** → **Add** each of the following.
   Use **Reference a secret** for the sensitive ones:

   | Name | How it is supplied | Value / secret |
   |---|---|---|
   | `SESSION_SECRET_KEY` | Secret → *SESSION_SECRET_KEY* → latest | |
   | `ADMIN_USERNAME` | Secret → *ADMIN_USERNAME* → latest *(or plain env var)* | |
   | `ADMIN_PASSWORD` | Secret → *ADMIN_PASSWORD* → latest | |
   | `DATABASE_URL` | Secret → *DATABASE_URL* → latest | |
   | `DATA_DIR` | Plain env var | `/app/backend/data` |
   | `ENVIRONMENT` | Plain env var | `production` |
   | `CORS_ORIGINS` | Plain env var | `*` |

   > **Do NOT set `PORT`.** Cloud Run injects it (default `8080`) and the
   > container's start command already honours it.

   **If you chose Cloud SQL (Option A)**, also add **Cloud SQL connections →
   Add connection →** your instance (`project:asia-south1:retailynx-db`). That
   lets the container reach the instance over its private socket. With a hosted
   Postgres (Option B) skip this.
9. *(Optional)* **Security → Service account:** the default compute service
   account is fine. It needs **Secret Manager Secret Accessor** — grant it if
   your organisation requires explicit grants:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

10. **Create**. The first build takes ~4–8 minutes (Node build + pip install).
11. When it finishes, copy the **service URL**, e.g.
    `https://retailynx-xxxxxxxxxx-el.a.run.app`.

---

## 6. Test it

### 6a. Health check (must be `200`, no login needed)

```bash
curl -i https://YOUR-SERVICE-URL/health
```

Expected:

```
HTTP/2 200
{"status":"ok","app":"Retail Analytics Command Center"}
```

(The same endpoint is also reachable at `/api/health` for backwards
compatibility.)

### 6b. Log in

1. Open `https://YOUR-SERVICE-URL/` — you are redirected to **/login**.
2. Sign in with **`ADMIN_USERNAME`** and **`ADMIN_PASSWORD`** from step 4.
3. Open the account menu (top right) → **User Access**:
   * **Add User** — create a user with a username, role and initial password.
   * **Change role** — the dropdown in the *Role* column.
   * **Set/reset password** — the key icon in the *Actions* column.
   * **Disable** — click *Active* to flip an account to *Disabled*.
4. Confirm the data pages load (Dashboard, Secondary, Tertiary, Store Master,
   SQL Platform, Order-to-Transformation Tracker).

### 6c. Prove the API is protected

```bash
# Without the cookie: 401
curl -i https://YOUR-SERVICE-URL/api/auth/me
```

Even with the URL in hand, no data route returns anything to an unauthenticated
caller. The browser cookie is `HttpOnly`, `Secure` (in production) and
`SameSite=Lax`.

---

## 7. Shipping your data to Cloud Run

Cloud Run's filesystem is **ephemeral**: anything not in the image is gone on
the next deploy/cold start. You have two options.

### Option 1 (default) — the seed DuckDB files inside the image

`backend/data/*_src.duckdb` are copied into the image by the Dockerfile, and at
startup the app makes a writable working copy in `/tmp`. Nothing to configure.
This is what the steps above already give you.

### Option 2 — Parquet in `DATA_DIR` (recommended for large data)

DuckDB reads Parquet **directly** (`read_parquet`), streaming only the row
groups a query needs — it is never loaded into pandas, and DuckDB is capped at
`memory_limit=1GB` / `threads=2` so it cannot exhaust the container.

1. Put your data next to the image as Parquet, e.g. `backend/data/tertiary_data.parquet`
   (or a folder `backend/data/tertiary_data/*.parquet`).
2. Keep `DATA_DIR` pointing at that folder (`/app/backend/data` by default).
3. Rebuild/redeploy. On startup the dataset is then read from Parquet instead
   of the seed database.

> **`store_status` / `ter_min_date` / `ter_max_date` in Parquet mode are
> read-only.** They cannot be recomputed in place, so they must already be
> present in the Parquet columns. Produce them with the local app once (Store
> Master → edit → save recomputes them) before exporting to Parquet.

To keep data outside the image entirely, mount a Cloud Storage bucket
(Cloud Run **Volumes → Add volume → Cloud Storage bucket**).

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Container fails to start; log says **`Invalid application configuration: missing required environment variable(s): ...`** | That variable was not added in step 5. Add it and redeploy. |
| Log says **`SESSION_SECRET_KEY is still the public development placeholder`** | You deployed with the sample value. Create a real random secret (step 4). |
| **`/health` 503 / "container failed to start"** | Usually the app could not reach Postgres. Check `DATABASE_URL` (password, `?sslmode=require`, host) and, for Cloud SQL, that the instance is **added under Cloud Connections**. |
| **`could not translate host name`** / timeouts | Wrong host, or the Cloud SQL instance is in a different region/project. Verify with `gcloud sql instances describe retailynx-db`. |
| **Login says "Invalid username or password" on a fresh deploy** | The admin is seeded only when *no* admin exists. If you changed `ADMIN_PASSWORD` after the first boot, reset it from **User Access** (or point `DATABASE_URL` at a fresh database). |
| **Login "succeeds" then bounces back to /login** | `ENVIRONMENT=production` makes the cookie `Secure`. Use the **https** service URL, not `http`. |
| **"Too many failed login attempts"** | The throttle locked the account for `LOGIN_LOCKOUT_SECONDS` (15 min by default). An admin can unlock it instantly by resetting the password in **User Access**. |
| **502 / 504 on a heavy SQL Platform query** | The request outran the timeout, or ran out of memory. Raise **Request timeout** to 300 s and confirm memory is **2 GiB**. |
| **Store Master edits disappear after a while** | Expected: the working DuckDB copy lives in `/tmp`. Keep edits in the seed data + git, or use Parquet in `DATA_DIR`. |
| **Slow first request after idling** | *Minimum instances = 0* scaled to zero. That is the price of paying nothing while idle; set min instances to 1 for speed (and an always-on cost). |
| **Build fails: permission denied pushing to Artifact Registry** | Make sure the **Artifact Registry API** and **Cloud Build API** are enabled (step 2). |
| **Build fails at `npm ci`** | Delete `frontend/package-lock.json` from git and re-push, or change the Dockerfile's `npm ci` to `npm install`. |
| **Build fails at `pip install`** | A pinned wheel has no CPython 3.11 Linux build — adjust the pin in `backend/requirements.txt`. |

Handy log command:

```bash
gcloud run services logs read retailynx --region=asia-south1 --limit=100
```

---

## 9. How to deploy an update

**Automatic (what you set up in step 5):** Cloud Build is wired to the `main`
branch, so a push redeploys:

```bash
cd c:/webapp
git add .
git commit -m "Describe your change"
git push            # Cloud Build -> new revision -> traffic shifted
```

**Manual redeploy** (no code change): Console → **Cloud Run → retailynx →
Deploy new revision → Deploy**.

**Changing a setting** (memory, instances, an env var): **Edit & deploy new
revision** → change it → **Deploy**.

**Changing a secret:** add a new version (step 4), then redeploy (or *Edit →
Variables & Secrets → re-point at `latest`*) so the new version is picked up.

**Rolling back:** Console → **Cloud Run → retailynx → Revisions** → pick the
previous good revision → **Manage traffic → 100 %** → **Save**.

---

## 10. How to shut it all down (stop all charges)

Do these in order. Nothing here is reversible, so make sure you have a backup of
any data you care about.

**1. Delete the Cloud Run service** (stops all request billing and the
always-on part of min-instances):

```bash
gcloud run services delete retailynx --region=asia-south1
```

**2. Delete the Cloud SQL instance** — this is the biggest cost while running.
*Deleting the instance deletes the database.* If you might come back, take a
backup/dump first (`gcloud sql export sql ...`, or `pg_dump`) to Cloud Storage.

```bash
gcloud sql instances delete retailynx-db
```

**3. Delete the container images** in Artifact Registry (they bill per GB):

```bash
gcloud artifacts repositories list
gcloud artifacts repositories delete REPOSITORY_NAME --location=asia-south1
```

**4. Delete the secrets** (they bill a tiny amount per version):

```bash
for s in SESSION_SECRET_KEY ADMIN_USERNAME ADMIN_PASSWORD DATABASE_URL; do
  gcloud secrets delete "$s" --quiet
done
```

**5. Delete the Cloud Build trigger / connection** so a push cannot resurrect
the service:
Console → **Cloud Build → Triggers** → delete the `retailynx` trigger. If you
also want to remove the GitHub link, **Cloud Build → Repositories (2nd gen)** →
delete the connection.

**6. (Optional) Delete the project** — the nuclear option that removes every
billable resource at once:

```bash
gcloud projects delete YOUR_PROJECT_ID
```

> A project sits in a 30-day "pending deletion" window and can be restored
> during it. After that it is gone for good.

**Sanity check** that nothing is left billing: Console → **Billing → Reports**,
group by **Service**, and look at the last few days. Also
**Cloud SQL → Instances** and **Cloud Run → Services** should both be empty.

---

## Appendix — every environment variable

| Variable | Required? | Purpose |
|---|---|---|
| `SESSION_SECRET_KEY` | **Always** | Signs the session cookie. Generate once; changing it logs everyone out. |
| `ADMIN_USERNAME` | **Always** | Username of the first ADMIN. |
| `ADMIN_PASSWORD` | **Always** | Password of the first ADMIN (min 8 chars). Used **only** while no admin exists. |
| `DATABASE_URL` | In production | Postgres connection string. Defaults to SQLite under `DATA_DIR` (local dev). |
| `DATA_DIR` | In production | Where the seed/Parquet data lives. Defaults to `backend/data`. |
| `ENVIRONMENT` | No | `production` enables `Secure` cookies + strict startup checks. |
| `CORS_ORIGINS` | No | Comma-separated browser origins (default `*`). |
| `DUCKDB_MEMORY_LIMIT` | No | DuckDB memory cap (default `1GB`). |
| `DUCKDB_THREADS` | No | DuckDB thread count (default `2`). |
| `MAX_LOGIN_ATTEMPTS` | No | Failed logins before lockout (default `5`). |
| `LOGIN_LOCKOUT_SECONDS` | No | Lockout duration (default `900` = 15 min). |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | No | Window the failures are counted in (default `900`). |
| `BCRYPT_ROUNDS` | No | bcrypt cost for new hashes (default `12`). |
| `PORT` | No | Injected by Cloud Run. **Never set it yourself.** |
