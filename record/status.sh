#!/bin/zsh
# Is the recording running? Segments so far and the supervisor log.
cd "$(dirname "$0")"
pgrep -f "^/bin/zsh $PWD/record-loop.sh$" >/dev/null && echo "SUPERVISOR: running" || echo "SUPERVISOR: NOT RUNNING"
[[ -f .sox.pid ]] && kill -0 "$(cat .sox.pid)" 2>/dev/null && echo "SOX: running pid $(cat .sox.pid)" || echo "SOX: NOT RUNNING"
ls -lhtr "${RECORD_PREFIX:-session}"-*.flac 2>/dev/null
tail -5 supervisor.log
