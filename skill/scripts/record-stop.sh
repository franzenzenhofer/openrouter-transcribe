#!/bin/bash
# Stop both recorders with SIGINT (files get finalised), wait for exit, then print ffprobe duration and
# volumedetect for every track. Exit 3 when a file is missing or any track is silent (mean < -60 dB).
# Usage: record-stop.sh --out DIR
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"
OUT=""
while [ $# -gt 0 ]; do case "$1" in --out) OUT="$2"; shift 2;; *) die "unknown argument $1";; esac; done
[ -n "$OUT" ] || die "--out DIR is required"
STATE="$OUT/record.state"
[ -f "$STATE" ] || die "no $STATE - nothing recording here"
FF_PID="$(state_get "$STATE" ffmpeg_pid)"; SYS_PID="$(state_get "$STATE" sysaudio_pid)"
MAIN="$(state_get "$STATE" main_file)"; SYS="$(state_get "$STATE" sys_file)"

FAIL=0
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SYSLOG="$(state_get "$STATE" sysaudio_log)"; [ -n "$SYSLOG" ] || SYSLOG="$OUT/sysaudio.log"
echo "--- interruptions (recording started $(state_get "$STATE" start_iso), stopped $NOW_ISO) ---"
if ! kill -0 "$FF_PID" 2>/dev/null; then echo "FAIL  ffmpeg (pid $FF_PID) died before stop - main file ends early (checked $NOW_ISO; see $OUT/ffmpeg.log)"; FAIL=1; fi
if ! kill -0 "$SYS_PID" 2>/dev/null; then echo "FAIL  sysaudio (pid $SYS_PID) died before stop - system audio ends early (checked $NOW_ISO; see $SYSLOG)"; FAIL=1; fi
if [ -f "$SYSLOG" ] && grep -qE 'SLEEP|WAKE|stopped with error' "$SYSLOG"; then
  grep -E 'SLEEP|WAKE|stopped with error' "$SYSLOG" | sed 's/^/FAIL  Mac slept or capture broke: /'
  FAIL=1
fi
[ "$FAIL" = 0 ] && echo "ok    no sleep, wake or early death seen"
kill -INT "$FF_PID" "$SYS_PID" 2>/dev/null
for _ in $(seq 1 100); do
  kill -0 "$FF_PID" 2>/dev/null || kill -0 "$SYS_PID" 2>/dev/null || break
  sleep 0.3
done
for p in "$FF_PID" "$SYS_PID"; do
  if kill -0 "$p" 2>/dev/null; then echo "FAIL: pid $p still running after 30 s (file may be unfinalised)"; FAIL=1; fi
done
mv "$STATE" "$OUT/record.state.stopped-$(date -u +%Y%m%dT%H%M%SZ)"

check_track() { # file stream label
  local f="$1" s="$2" label="$3" dur mean max
  dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null | head -1)"
  if [ -z "$(ffprobe -v error -select_streams "${s#0:}" -show_entries stream=index -of csv=p=0 "$f" 2>/dev/null)" ]; then echo "FAIL  $label: stream $s unreadable in $f"; FAIL=1; return; fi
  local vd; vd="$(ffmpeg -hide_banner -nostats -i "$f" -map "$s" -af volumedetect -f null /dev/null 2>&1)"
  mean="$(printf '%s' "$vd" | sed -n 's/.*mean_volume: \(-\{0,1\}[0-9.]*\) dB.*/\1/p' | head -1)"
  max="$(printf '%s' "$vd" | sed -n 's/.*max_volume: \(-\{0,1\}[0-9.]*\) dB.*/\1/p' | head -1)"
  if [ -z "$mean" ]; then echo "FAIL  $label: no level measured"; FAIL=1; return; fi
  local verdict="ok  "
  if python3 -I -c "import sys; sys.exit(0 if float('$mean') < -60 else 1)"; then verdict="FAIL"; FAIL=1; fi
  printf '%s  %-22s dur %8.1f s  mean %6s dB  max %6s dB\n' "$verdict" "$label" "$dur" "$mean" "$max"
}

echo "--- levels (silent = mean below -60 dB) ---"
for f in "$MAIN" "$SYS"; do [ -s "$f" ] || { echo "FAIL  missing or empty: $f"; FAIL=1; }; done
if [ -s "$MAIN" ]; then
  NA="$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$MAIN" | wc -l | tr -d ' ')"
  for i in $(seq 0 $((NA - 1))); do check_track "$MAIN" "0:a:$i" "mic track $((i + 1))"; done
  if [ -n "$(ffprobe -v error -select_streams v -show_entries stream=index -of csv=p=0 "$MAIN")" ]; then
    echo "ok    video stream present, file duration $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$MAIN") s"
  fi
fi
[ -s "$SYS" ] && check_track "$SYS" "0:a:0" "system audio (remote)"
echo "files: $MAIN"; echo "       $SYS"
if [ "$FAIL" != 0 ]; then echo "RESULT: FAILED - a track is missing or silent. Fix before the call is over; do not transcribe this."; exit 3; fi
echo "RESULT: all tracks present and carrying signal"
