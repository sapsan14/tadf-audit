# Hetzner deployment

## What this is

Production deploy of TADF Аудит to a small Hetzner CAX11 (ARM, 2 vCPU,
4 GB RAM, ~€3.29/mo, Helsinki). Cloudflare provides DNS for the
`tadf-audit.h2oatlas.ee` subdomain. Caddy on the box terminates TLS
(Let's Encrypt HTTP-01) and reverse-proxies to the Streamlit container.

```
              ┌──── github actions (deploy-hetzner.yml) ──────┐
              │  build amd64+arm64 image → push to GHCR        │
              │  CF API → upsert A record tadf-audit.h2oatlas.ee │
              │  hcloud   → ensure CAX11 server                │
              │  ssh      → scp bootstrap + .env + auth.yaml   │
              │  ssh      → bash bootstrap.sh                  │
              └────────────────────────────────────────────────┘
                                   │
                       ┌───────────▼─────────────┐
                       │ Hetzner CAX11 (Helsinki) │
                       │  ┌───────┐  ┌─────────┐  │
                       │  │ caddy │──│  tadf   │  │
                       │  │ :443  │  │ :8501   │  │
                       │  └───────┘  └─────────┘  │
                       │   tadf-data  caddy-data  │
                       └──────────────────────────┘
                                   ▲
                              tadf-audit.h2oatlas.ee
                                   │
                            cloudflare (DNS-only)
```

---

## One-time setup

### 1. Hetzner account + project

1. Sign up at https://www.hetzner.com/cloud (if you haven't already).
2. Create a project (e.g. `tadf`).
3. **Project → Security → API tokens** → "Generate API Token", name it
   `gh-actions-deploy`, permissions **Read & Write**. Copy the token.
4. Save as GitHub secret **`HCLOUD_TOKEN`**.

### 2. Deploy SSH key

Generate locally:

```bash
ssh-keygen -t ed25519 -C "tadf-deploy" -f ~/.ssh/tadf-deploy -N ""
```

- Save the **private key** (contents of `~/.ssh/tadf-deploy`) as GitHub
  secret **`DEPLOY_SSH_PRIVATE_KEY`**.
- Save the **public key** (contents of `~/.ssh/tadf-deploy.pub`) as
  GitHub secret **`DEPLOY_SSH_PUBLIC_KEY`**.

The workflow will register the public key in Hetzner and bake it into
the server's `deploy` user via cloud-init.

### 3. Cloudflare DNS

Cloudflare zone for `h2oatlas.ee` already exists (per project context).

1. **Cloudflare dashboard → Profile → API Tokens** → "Create Token" →
   template **"Edit zone DNS"** → Zone Resources → Specific zone →
   `h2oatlas.ee`. Copy the token.
2. Save as GitHub secret **`CF_API_TOKEN`**.
3. **Cloudflare dashboard → h2oatlas.ee → Overview** → bottom right
   → copy the **Zone ID**. Save as GitHub secret **`CF_ZONE_ID`**.

> The workflow upserts an A record `tadf-audit.h2oatlas.ee` → server IP
> with `proxied: false` (DNS-only). Caddy then handles HTTPS via
> Let's Encrypt HTTP-01. To switch to proxied (orange cloud) later, set
> repository **variable** `CF_PROXIED=true` (Settings → Variables, not
> Secrets) — but you'll then need a different ACME challenge (DNS-01)
> because Cloudflare proxying breaks HTTP-01.

### 4. Anthropic API key

Already added by you as **`ANTHROPIC_API_KEY`**. ✅

### 5. Auth config (passwords)

Save the **entire content of `auth.yaml`** as GitHub secret
**`AUTH_YAML`** (multi-line). The workflow writes it to
`/opt/tadf/auth.yaml` on the server, mounted read-only into the container.

To regenerate later:
```bash
cat auth.yaml | gh secret set AUTH_YAML
```

### 6. Caddy admin email

Pick the email Let's Encrypt uses for cert-expiry notifications. Save as
GitHub secret **`CADDY_ADMIN_EMAIL`** (e.g. `sokolovmeister@gmail.com`).

---

## Required GitHub secrets — checklist

| Secret | Value |
|---|---|
| `HCLOUD_TOKEN` | Hetzner Cloud API token (Read & Write) |
| `DEPLOY_SSH_PRIVATE_KEY` | ed25519 private key contents |
| `DEPLOY_SSH_PUBLIC_KEY` | ed25519 public key contents |
| `CF_API_TOKEN` | Cloudflare token, scope `Zone.DNS:Edit` on `h2oatlas.ee` |
| `CF_ZONE_ID` | Cloudflare zone ID for `h2oatlas.ee` |
| `CADDY_ADMIN_EMAIL` | Email for Let's Encrypt notifications |
| `ANTHROPIC_API_KEY` | Claude API key (already added) |
| `AUTH_YAML` | Full content of local `auth.yaml` |

Optional:
| Variable (Settings → Variables) | Default | Use |
|---|---|---|
| `CF_PROXIED` | `false` | Set to `true` to flip CF to orange-cloud |

---

## How to deploy

### First time

1. Configure all GitHub secrets above.
2. Trigger the workflow manually:
   **Actions → Deploy (Hetzner) → Run workflow** (default options).
3. Watch the run. First time takes ~10–15 min:
   - 5 min: build + push image
   - 3 min: provision server + cloud-init
   - 1 min: deploy + Caddy obtains TLS cert
   - 1 min: smoke tests

After success, https://tadf-audit.h2oatlas.ee is live.

### Subsequent deploys

Every push to `main` that touches `app/`, `src/`, `Dockerfile`, or `ops/`
re-runs the workflow. Server is reused, only the image is rebuilt and
the container restarted. ~3–5 min total.

### Manual options

- **Skip rebuild** (use latest GHCR image): manual trigger →
  *Skip rebuilding* checked.
- **Recreate server** (rare — only if cloud-init or arch needs reset):
  manual trigger → *Delete existing server* checked. **WARNING:**
  deletes the named volumes too unless you snapshot first.

---

## Operating the box

```bash
# SSH in
ssh -i ~/.ssh/tadf-deploy deploy@<server-ip>

# Check stack
cd /opt/tadf
docker compose ps
docker compose logs -f tadf caddy

# Restart just the app
docker compose restart tadf

# Roll back to a specific image tag
docker pull ghcr.io/sapsan14/tadf-audit:sha-abc123def456
sed -i 's|TADF_IMAGE=.*|TADF_IMAGE=ghcr.io/sapsan14/tadf-audit:sha-abc123def456|' .env
docker compose up -d --remove-orphans
```

### Backups (manual, do this monthly)

```bash
# On the server
ssh deploy@<ip> "docker run --rm -v tadf_tadf-data:/data -v /tmp:/backup alpine \
    tar czf /backup/tadf-data-$(date +%F).tar.gz -C /data ."
scp deploy@<ip>:/tmp/tadf-data-*.tar.gz ~/tadf-backups/
```

The 7-year legal retention requires this be done routinely. Consider
a `restic` cron job to an off-site bucket — see plan PLAN_DEV_RU.md → Phase 5.

---

## Cost

| Item | €/mo |
|---|---|
| Hetzner CAX11 (ARM, 2 vCPU, 4 GB) in Helsinki | 3.29 |
| Outbound traffic (20 TB included) | 0 |
| IPv4 | included |
| Cloudflare (Free plan) | 0 |
| GitHub Actions (private repo, ~30 min/month at QEMU build) | typically free under inclusive minutes |
| **Total** | **~€3.29** |

Plus Anthropic API usage (variable; see sidebar tracker).
