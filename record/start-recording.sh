#!/bin/zsh
# Start the supervised recording, detached, with sleep prevented (on AC power).
# Do not close the lid: on most Macs that sleeps the machine and stops the microphone.
set -euo pipefail
cd "$(dirname "$0")"
if pgrep -f "^/bin/zsh $PWD/record-loop.sh$" >/dev/null; then
  echo "Recording supervisor already running." >&2
  exit 1
fi
rm -f .stop
nohup caffeinate -dis "$PWD/record-loop.sh" > /dev/null 2>&1 &
echo "Recording started (supervisor via caffeinate pid $!). Stop: ./stop-recording.sh"
