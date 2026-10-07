#!/bin/zsh
# Stop cleanly: sox gets SIGINT so the open FLAC segment is finalized.
set -euo pipefail
cd "$(dirname "$0")"
touch .stop
[[ -f .sox.pid ]] && kill -INT "$(cat .sox.pid)" 2>/dev/null || true
for _ in {1..30}; do pgrep -f "^/bin/zsh $PWD/record-loop.sh$" >/dev/null || break; sleep 1; done
pgrep -f "^/bin/zsh $PWD/record-loop.sh$" >/dev/null && echo "Supervisor still running" >&2 || echo "Recording stopped."
ls -lh "${RECORD_PREFIX:-session}"-*.flac
