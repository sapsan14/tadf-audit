#!/usr/bin/env bash
# Server-side deploy script. Runs as `deploy` on the Hetzner host.
# CI scps: docker-compose.yml, Caddyfile, .env, auth.yaml, bootstrap.sh
# then invokes: GHCR_USERNAME=… GHCR_TOKEN=… bash bootstrap.sh
#
# Idempotent. Persistent state lives in named Docker volumes
# (`tadf-data`, `caddy-data`, `caddy-config`) — re-runs are safe.

set -euo pipefail

APP_DIR="/opt/tadf"
cd "${APP_DIR}"

log()  { printf '[bootstrap] %s\n' "$*"; }
fail() { printf '[bootstrap][ERROR] %s\n' "$*" >&2; exit 1; }

[[ -f "${APP_DIR}/.env" ]]               || fail ".env is missing"
[[ -f "${APP_DIR}/docker-compose.yml" ]] || fail "docker-compose.yml is missing"
[[ -f "${APP_DIR}/Caddyfile" ]]          || fail "Caddyfile is missing"
[[ -f "${APP_DIR}/auth.yaml" ]]          || fail "auth.yaml is missing (must come from CI secret AUTH_YAML)"

chmod 0600 "${APP_DIR}/.env" "${APP_DIR}/auth.yaml"

# GHCR login so private images can be pulled.
if [[ -n "${GHCR_USERNAME:-}" && -n "${GHCR_TOKEN:-}" ]]; then
	log "Logging in to GHCR as ${GHCR_USERNAME}"
	printf '%s' "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USERNAME}" --password-stdin
fi

log "Pulling images"
docker compose pull

log "Starting stack"
docker compose up -d --remove-orphans

# Caddyfile is bind-mounted; container sees the new file but Caddy keeps
# its parsed config in memory. Reload (SIGUSR1-style) without restart so
# in-flight requests aren't dropped. Falls back to a hard restart if the
# reload-via-exec path fails (e.g. caddy container still warming up).
log "Reloading Caddy"
if docker compose exec -T caddy caddy reload \
        --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1; then
	log "Caddy config reloaded"
else
	log "caddy reload failed — restarting container instead"
	docker compose restart caddy
fi

log "Waiting for tadf /_stcore/health (max 3 min)"
for i in {1..60}; do
	if docker compose exec -T tadf curl -fsS --max-time 3 http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
		log "tadf streamlit healthy after ${i} attempts"
		break
	fi
	sleep 3
	if (( i == 60 )); then
		log "tadf failed to become healthy — recent logs:"
		docker compose logs --tail 200 tadf || true
		fail "tadf health check timed out"
	fi
done

# FastAPI sidecar — receives EHR/Teatmik imports from the in-browser
# helpers. Different process inside the same container, port 8001.
log "Waiting for tadf FastAPI sidecar /api/health (max 60 s)"
for i in {1..20}; do
	if docker compose exec -T tadf curl -fsS --max-time 3 http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
		log "tadf FastAPI sidecar healthy after ${i} attempts"
		break
	fi
	sleep 3
	if (( i == 20 )); then
		log "FastAPI sidecar failed to become healthy — recent logs:"
		docker compose logs --tail 200 tadf || true
		fail "FastAPI sidecar health check timed out"
	fi
done

log "docker compose ps:"
docker compose ps

log "Done."
