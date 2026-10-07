#!/bin/zsh
# Supervised lossless recording (macOS, sox + coreaudio). Records 30-minute FLAC segments
# (a crash loses at most the tail of one segment, never the day), restarts sox if it exits,
# and kills + restarts it if the newest segment stops growing for 60 seconds.
# Start: ./start-recording.sh   Stop: ./stop-recording.sh   Check: ./status.sh
# Env: RECORD_DEVICE (default "MacBook Pro Microphone"), RECORD_PREFIX (default "session").
set -uo pipefail
cd "$(dirname "$0")"

readonly DEVICE="${RECORD_DEVICE:-MacBook Pro Microphone}"
readonly PREFIX="${RECORD_PREFIX:-session}"
readonly SEGMENT_SECONDS=1800
readonly STALL_SECONDS=60
readonly POLL_SECONDS=15
readonly STOP_FILE=".stop"
readonly LOG="supervisor.log"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

newest_segment_size() {
  local newest
  newest=$(ls -t "$PREFIX"-*.flac 2>/dev/null | head -1)
  [[ -n "$newest" ]] && stat -f %z "$newest" || echo 0
}

watch_sox() {
  local pid=$1 last_size=-1 last_growth=$SECONDS size
  while kill -0 "$pid" 2>/dev/null; do
    sleep "$POLL_SECONDS"
    size=$(newest_segment_size)
    if (( size != last_size )); then
      last_size=$size; last_growth=$SECONDS
    elif (( SECONDS - last_growth >= STALL_SECONDS )) && [[ ! -f "$STOP_FILE" ]]; then
      log "STALL: no growth for ${STALL_SECONDS}s, killing sox $pid"
      say "Recording stalled, restarting" &
      kill -INT "$pid" 2>/dev/null; sleep 3; kill -KILL "$pid" 2>/dev/null
    fi
  done
}

log "supervisor start pid $$"
while [[ ! -f "$STOP_FILE" ]]; do
  base="$PREFIX-$(date +%Y-%m-%d_%H%M%S)-part.flac"
  sox -q -t coreaudio "$DEVICE" -c 1 -b 24 "$base" \
    trim 0 "$SEGMENT_SECONDS" : newfile : restart >> sox.log 2>&1 &
  sox_pid=$!
  echo "$sox_pid" > .sox.pid
  log "sox start pid $sox_pid -> ${base%.flac}NNN.flac"
  watch_sox "$sox_pid"
  wait "$sox_pid"; log "sox exit code $?"
  [[ -f "$STOP_FILE" ]] || { say "Recording restarted" & sleep 2; }
done
rm -f .sox.pid
log "supervisor stop"
