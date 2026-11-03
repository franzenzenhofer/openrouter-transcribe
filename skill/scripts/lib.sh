#!/bin/bash
# Shared helpers for the call-recording scripts. Source it, do not run it.

die() { echo "ERROR: $*" >&2; exit 1; }

# now_ms: epoch milliseconds (python3 -I, no GNU date needed)
now_ms() { python3 -I -c 'import time; print(int(time.time()*1000))'; }

# find_device <video|audio> <name-regex>: prints the avfoundation index of the first device whose
# name matches (case-insensitive extended regex). Fails loudly when nothing matches.
find_device() {
  local kind="$1" pattern="$2" listing section
  listing="$(ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)"
  section="$(printf '%s\n' "$listing" | awk -v k="$kind" '
    /AVFoundation video devices/ {on = (k == "video"); next}
    /AVFoundation audio devices/ {on = (k == "audio"); next}
    on && /\[[0-9]+\] / {print}')"
  local hit
  hit="$(printf '%s\n' "$section" | grep -iE -- "$pattern" | head -1 || true)"
  if [ -z "$hit" ]; then
    echo "ERROR: no $kind device matches /$pattern/. Available:" >&2
    printf '%s\n' "$section" >&2
    exit 1
  fi
  printf '%s\n' "$hit" | sed -E 's/.*\[([0-9]+)\] .*/\1/'
}

# state file helpers (key=value)
state_get() { grep -E "^$2=" "$1" | tail -1 | cut -d= -f2-; }
