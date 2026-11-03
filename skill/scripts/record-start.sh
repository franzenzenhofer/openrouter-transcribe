#!/bin/bash
# Start ONE recording session: ffmpeg (screen + mic track 1 + mic track 2) and sysaudio (system audio =
# the remote participants' voices) are launched together, PIDs and start timestamps go to <out>/record.state.
#
# Usage: record-start.sh --out DIR [--title NAME] [--mic1 REGEX] [--mic2 REGEX] [--screen REGEX] [--no-video]
#   --mic1   mic of the headset, default "AirPods"   (track 1; if absent, falls back to --mic2 only)
#   --mic2   built-in mic, default "MacBook.*Microphone"
#   --screen default "Capture screen"
# Needs Screen Recording permission for the terminal app (System Settings > Privacy & Security).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

OUT=""; TITLE="call"; MIC1="AirPods"; MIC2="MacBook.*Microphone"; SCREEN="Capture screen"; VIDEO=1
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2;;
    --title) TITLE="$2"; shift 2;;
    --mic1) MIC1="$2"; shift 2;;
    --mic2) MIC2="$2"; shift 2;;
    --screen) SCREEN="$2"; shift 2;;
    --no-video) VIDEO=0; shift;;
    *) die "unknown argument $1";;
  esac
done
[ -n "$OUT" ] || die "--out DIR is required"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
STATE="$OUT/record.state"
if [ -f "$STATE" ] && kill -0 "$(state_get "$STATE" ffmpeg_pid)" 2>/dev/null; then
  die "a recording is already running in $OUT (see $STATE)"
fi
command -v ffmpeg >/dev/null || die "ffmpeg not installed"

# compile sysaudio once (or when the source is newer)
BIN="$HERE/sysaudio"
if [ ! -x "$BIN" ] || [ "$HERE/sysaudio.swift" -nt "$BIN" ]; then
  echo "compiling sysaudio.swift ..."
  swiftc -O "$HERE/sysaudio.swift" -o "$BIN"
fi

# devices by name, never by hardcoded index
MIC1_IDX=""; MIC2_IDX=""
MIC1_IDX="$(find_device audio "$MIC1" 2>/dev/null)" || echo "note: no mic matching /$MIC1/ - track 1 will be the built-in mic only" >&2
MIC2_IDX="$(find_device audio "$MIC2")"
[ -n "$MIC1_IDX" ] || { MIC1_IDX="$MIC2_IDX"; MIC2_IDX=""; }
INPUTS=(); MAPS=()
if [ "$VIDEO" = 1 ]; then
  SCREEN_IDX="$(find_device video "$SCREEN")"
  INPUTS+=(-f avfoundation -capture_cursor 1 -framerate 15 -i "$SCREEN_IDX:$MIC1_IDX"); MAPS+=(-map 0:v -map 0:a)
  if [ -n "$MIC2_IDX" ]; then INPUTS+=(-f avfoundation -i ":$MIC2_IDX"); MAPS+=(-map 1:a); fi
  CODEC=(-c:v h264_videotoolbox -b:v 2500k -pix_fmt yuv420p -c:a aac -b:a 128k); EXT=mkv
else
  INPUTS+=(-f avfoundation -i ":$MIC1_IDX"); MAPS+=(-map 0:a)
  if [ -n "$MIC2_IDX" ]; then INPUTS+=(-f avfoundation -i ":$MIC2_IDX"); MAPS+=(-map 1:a); fi
  CODEC=(-c:a aac -b:a 128k); EXT=mka
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SAFE="$(printf '%s' "$TITLE" | tr -c 'A-Za-z0-9._-' '-')"
MAIN="$OUT/$SAFE-$STAMP.$EXT"
SYS="$OUT/$SAFE-sysaudio-$STAMP.m4a"
SYSLOG="$OUT/sysaudio.log"; FFLOG="$OUT/ffmpeg.log"
: > "$SYSLOG"

# launch both back to back; sysaudio needs about a second to report "recording"
"$BIN" "$SYS" > "$SYSLOG" 2>&1 &
SYS_PID=$!
T_SYS_LAUNCH="$(now_ms)"
ffmpeg -hide_banner -loglevel warning -nostdin "${INPUTS[@]}" "${MAPS[@]}" "${CODEC[@]}" "$MAIN" > "$FFLOG" 2>&1 &
FF_PID=$!
T_FF_LAUNCH="$(now_ms)"

for _ in $(seq 1 50); do
  grep -q 'recording' "$SYSLOG" && break
  kill -0 "$SYS_PID" 2>/dev/null || { cat "$SYSLOG" >&2; kill -INT "$FF_PID" 2>/dev/null || true; die "sysaudio exited at start (Screen Recording permission for this terminal?)"; }
  sleep 0.2
done
grep -q 'recording' "$SYSLOG" || { kill -INT "$SYS_PID" "$FF_PID" 2>/dev/null || true; die "sysaudio did not start within 10 s"; }
T_SYS_READY="$(now_ms)"
sleep 1
kill -0 "$FF_PID" 2>/dev/null || { cat "$FFLOG" >&2; kill -INT "$SYS_PID" 2>/dev/null || true; die "ffmpeg exited at start (see above; Screen Recording permission?)"; }

cat > "$STATE" <<STATE_EOF
title=$TITLE
main_file=$MAIN
sys_file=$SYS
ffmpeg_pid=$FF_PID
sysaudio_pid=$SYS_PID
ffmpeg_start_ms=$T_FF_LAUNCH
sysaudio_start_ms=$T_SYS_READY
sysaudio_launch_ms=$T_SYS_LAUNCH
mic1_index=$MIC1_IDX
mic2_index=$MIC2_IDX
video=$VIDEO
STATE_EOF
echo "recording started: $TITLE"
echo "  main   : $MAIN  (ffmpeg pid $FF_PID, mic1 idx $MIC1_IDX, mic2 idx ${MIC2_IDX:-none})"
echo "  system : $SYS  (sysaudio pid $SYS_PID)"
echo "  offset : sysaudio began $((T_SYS_READY - T_FF_LAUNCH)) ms after ffmpeg"
echo "  stop   : bash $HERE/record-stop.sh --out $OUT"
