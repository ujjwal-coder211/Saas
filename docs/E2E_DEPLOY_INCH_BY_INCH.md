# E2E Networks — inch by inch deploy guide (Aksh)

**Repo:** https://github.com/ujjwal-coder211/Saas  
**Docker files:** `Dockerfile` + `docker-compose.prod.yml`  
**Marketing site (aitotech.in):** separate repo `Aitotech` — Docker on same E2E VM. Guide: https://github.com/ujjwal-coder211/Aitotech/blob/main/docs/E2E_DEPLOY.md

---

## Part A — What is already done (GitHub)

| Item | Status |
|------|--------|
| Aksh API + Studio + Omni | Code on `main` |
| Docker image build | `Dockerfile` |
| Production stack | `docker-compose.prod.yml` (Postgres + Redis + API) |
| Entry script | `scripts/docker-entrypoint.sh` (wait DB + start) |
| Env template | `.env.production.example` |

You only **deploy** — no coding required for basic launch.

---

## Part B — What YOU must do (E2E platform)

### Step 1 — E2E account + VM (Delhi NCR)

1. Login: https://www.e2enetworks.com/
2. Create **VPC** (if not exists)
3. Create **Linux VM** (Ubuntu 22.04 recommended)
   - Region: **Delhi NCR** (not Mumbai for new projects)
   - Size: minimum **2 vCPU, 4 GB RAM** (8 GB better)
   - Disk: **40 GB+**
4. Note **public IP** of VM (example: `203.0.113.50`)
5. Security group / firewall: allow **TCP 22** (SSH), **TCP 80**, **TCP 443**, **TCP 8000** (temporary until nginx)

---

### Step 2 — SSH into VM

From your laptop (PowerShell or terminal):

```bash
ssh root@YOUR_VM_IP
```

(or `ubuntu@...` if E2E uses ubuntu user)

---

### Step 3 — Install Docker on VM

```bash
apt-get update
apt-get install -y git curl ca-certificates
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
apt-get install -y docker-compose-plugin
docker --version
docker compose version
```

---

### Step 4 — Clone Aksh repo

```bash
cd /opt
git clone https://github.com/ujjwal-coder211/Saas.git aksh
cd aksh
git pull origin main
```

---

### Step 5 — Create `.env` (secrets — NEVER commit)

```bash
cp .env.production.example .env
nano .env
```

**Minimum fields to fill:**

| Variable | Example | Where to get |
|----------|---------|--------------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | https://openrouter.ai/keys |
| `POSTGRES_PASSWORD` | long random password | you invent |
| `JWT_SECRET` | 64 char random | `openssl rand -hex 32` |
| `SAAS_ALLOW_PUBLIC_SIGNUP` | `true` (launch) | allow signup |
| `SAAS_PUBLIC_URL` | `https://api.aksh.aitotech.in` | your API domain |
| `NEURALROUTER_CORS_ORIGINS` | `https://api.aksh.aitotech.in,https://aitotech.in` | your domains |
| `OMNI_VAULT_HMAC_KEY` | random hex | `openssl rand -hex 32` |
| `OMNI_VAULT_ENCRYPTION_KEY` | random hex | `openssl rand -hex 32` |
| `OMNI_ADMIN_KEY` | random string | you invent (admin brain promote) |

Optional but good:

| Variable | Purpose |
|----------|---------|
| `AKSH_SEARCH_API_KEY` | Tavily key for web search |
| `STRIPE_*` | Pro billing (later) |

Save file: `Ctrl+O`, Enter, `Ctrl+X`

---

### Step 6 — Build and run Docker stack

```bash
cd /opt/aksh
chmod +x scripts/e2e-deploy.sh scripts/docker-entrypoint.sh
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes **5–15 minutes**.

Check status:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api
```

Wait until logs show `Application startup complete`.

---

### Step 7 — Test on VM (before domain)

```bash
curl http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8000/web/studio/
```

From browser (your PC):

```
http://YOUR_VM_IP:8000/web/dashboard/
http://YOUR_VM_IP:8000/web/studio/
```

---

### Step 8 — DNS (domain point to E2E)

At your domain registrar (where `aitotech.in` is):

| Type | Name | Value |
|------|------|-------|
| A | `api.aksh` | YOUR_VM_IP |

Wait **5–30 minutes** for DNS.

Test:

```bash
curl http://api.aksh.aitotech.in:8000/health
```

---

### Step 9 — HTTPS (nginx + Let's Encrypt)

Install nginx + certbot on VM:

```bash
apt-get install -y nginx certbot python3-certbot-nginx
nano /etc/nginx/sites-available/aksh
```

Paste:

```nginx
server {
    listen 80;
    server_name api.aksh.aitotech.in;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable:

```bash
ln -s /etc/nginx/sites-available/aksh /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d api.aksh.aitotech.in
```

Update `.env`:

```env
SAAS_PUBLIC_URL=https://api.aksh.aitotech.in
NEURALROUTER_CORS_ORIGINS=https://api.aksh.aitotech.in,https://aitotech.in
```

Restart API:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Test:

```bash
curl https://api.aksh.aitotech.in/health
```

---

### Step 10 — First user test

1. Open `https://api.aksh.aitotech.in/web/dashboard/`
2. **Create free account** → copy **API key**
3. Open **Studio** → paste API key → **New cloud** project
4. Test Chat / Composer / Ctrl+K

---

### Step 11 — Connect marketing website (Aitotech)

**Repo:** `ujjwal-coder211/Aitotech` (Vercel)

In Vercel env (optional — if waitlist writes to same Supabase):

- Website waitlist = Supabase (already documented in `docs/LAUNCH_SETUP.md`)

To link Studio from website, add button URL:

`https://api.aksh.aitotech.in/web/studio/`

**Cursor users:** Base URL `https://api.aksh.aitotech.in/v1`, model `omni`

---

## Part C — After deploy (maintenance)

### Update Aksh (new GitHub code)

```bash
cd /opt/aksh
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

### View logs

```bash
docker compose -f docker-compose.prod.yml logs -f api
```

### Backup Postgres

```bash
docker compose -f docker-compose.prod.yml exec postgres pg_dump -U aitotech neuralrouter > backup.sql
```

### Stop everything

```bash
docker compose -f docker-compose.prod.yml down
```

---

## Part D — What I cannot do for you

| Task | Why you do it |
|------|----------------|
| E2E account + payment | Your billing |
| VM create + SSH | Your cloud login |
| Domain DNS A record | Your registrar |
| SSL certbot | Your server access |
| OpenRouter API key | Your account |
| Vercel redeploy (website) | Your Vercel dashboard |
| Supabase waitlist keys | Your Supabase project |
| Stripe keys | Your Stripe account |
| TIR GPU (Omni inference) | E2E GPU console — optional phase 2 |

---

## Part E — Troubleshooting

| Problem | Fix |
|---------|-----|
| `POSTGRES_PASSWORD` error | Set in `.env` before compose up |
| Health 502 | `docker compose logs api` — check OPENROUTER key |
| Signup fails | `SAAS_ALLOW_PUBLIC_SIGNUP=true` in `.env` |
| Studio empty projects | DATABASE_URL must reach postgres container |
| Chat no answer | Set `OPENROUTER_API_KEY` |
| Git buttons fail | git is in Docker image — rebuild image |

---

## Quick command cheat sheet

```bash
# One-time setup
cd /opt && git clone https://github.com/ujjwal-coder211/Saas.git aksh
cd aksh && cp .env.production.example .env && nano .env
docker compose -f docker-compose.prod.yml up -d --build

# Health
curl http://127.0.0.1:8000/health

# Update
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

---

**Files to use:** `Dockerfile` · `docker-compose.prod.yml` · `.env.production.example` · `scripts/docker-entrypoint.sh`
