#!/usr/bin/env bash
# Self-signed TLS certificate for the nginx container (offline: no ACME / Let's Encrypt).
#   ./scripts/gen-certs.sh [hostname-or-ip]        (default: APP_HOST from .env, else localhost)
# Output: ./certs/fullchain.pem + ./certs/privkey.pem. Import fullchain.pem into each client's trust store
# (or accept the browser warning once) — the cert is valid for 825 days.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${1:-}"
if [ -z "$HOST" ] && [ -f .env ]; then HOST="$(grep -E '^APP_HOST=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"; fi
HOST="${HOST:-localhost}"

mkdir -p certs
if [[ "$HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then SAN="IP:$HOST,DNS:localhost,IP:127.0.0.1"
elif [ "$HOST" = "localhost" ]; then SAN="DNS:localhost,IP:127.0.0.1"
else SAN="DNS:$HOST,DNS:localhost,IP:127.0.0.1"; fi
SAN="$(printf '%s' "$SAN" | awk -F, '{for(i=1;i<=NF;i++) if(!seen[$i]++) printf "%s%s", (n++?",":""), $i}')"

CONF="$(mktemp)"; trap 'rm -f "$CONF"' EXIT
cat > "$CONF" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = $HOST
O = Spectrogram Annotator
[v3]
subjectAltName = $SAN
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
EOF

openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes -config "$CONF" \
  -keyout certs/privkey.pem -out certs/fullchain.pem 2>/dev/null
chmod 600 certs/privkey.pem
echo "Wrote certs/fullchain.pem and certs/privkey.pem for: $SAN"
