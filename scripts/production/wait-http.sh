#!/usr/bin/env bash
# Nginx reload is asynchronous: new workers may need time to accept new routes.
set -u
probe_url=${1:?Usage: wait-http.sh URL}
for attempt in $(seq 1 20); do
    if curl -fsS --connect-timeout 3 --max-time 10 "$probe_url" >/dev/null 2>&1; then exit 0; fi
    sleep 1
done
echo "Health check remained unavailable: $probe_url" >&2
exit 1
