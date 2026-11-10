#!/bin/bash
# Build the transcription input: STEREO, left = me (mic track 1), right = remote (system audio), 16 kHz,
# aligned by the start offset between the two recorders, cut into mp3 chunks that stay under 5 MB
# (32 kbps => 1080 s chunk = about 4.3 MB).
# Usage: mix.sh --main FILE.mkv --sys FILE.m4a --out DIR --offset-ms N [--with-mic2] [--chunk-sec 1080]
#   --offset-ms  sysaudio_start_ms - ffmpeg_start_ms from record.state (positive = system audio started later)
#   --with-mic2  also add mic track 2 to the left channel (only if track 1 is weak; may echo the remote voice)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$HERE/lib.sh"
MAIN=""; SYS=""; OUT=""; OFFSET=0; MIC2=0; CHUNK=1080
while [ $# -gt 0 ]; do
  case "$1" in
    --main) MAIN="$2"; shift 2;; --sys) SYS="$2"; shift 2;; --out) OUT="$2"; shift 2;;
    --offset-ms) OFFSET="$2"; shift 2;; --with-mic2) MIC2=1; shift;; --chunk-sec) CHUNK="$2"; shift 2;;
    *) die "unknown argument $1";;
  esac
done
[ -s "$MAIN" ] && [ -s "$SYS" ] && [ -n "$OUT" ] || die "--main, --sys, --out are required and the files must exist"
mkdir -p "$OUT"

# offset > 0: system audio started later => delay it. offset < 0: delay the mics instead.
SYS_DELAY=0; MIC_DELAY=0
if [ "$OFFSET" -ge 0 ]; then SYS_DELAY="$OFFSET"; else MIC_DELAY=$((-OFFSET)); fi
LEFT="[0:a:0]aresample=16000:async=1:first_pts=0,pan=mono|c0=c0,adelay=${MIC_DELAY}[l]"
LMAP="[l]"
if [ "$MIC2" = 1 ]; then
  LEFT="[0:a:0]aresample=16000:async=1:first_pts=0,pan=mono|c0=c0,adelay=${MIC_DELAY}[l1];[0:a:1]aresample=16000:async=1:first_pts=0,pan=mono|c0=c0,adelay=${MIC_DELAY}[l2];[l1][l2]amix=inputs=2:normalize=0[l]"
fi
RIGHT="[1:a:0]aresample=16000:async=1:first_pts=0,pan=mono|c0=0.5*c0+0.5*c1,adelay=${SYS_DELAY}[r]"
FULL="$OUT/mix-stereo-16k.wav"
ffmpeg -hide_banner -loglevel error -y -i "$MAIN" -i "$SYS" -filter_complex \
  "$LEFT;$RIGHT;${LMAP}[r]join=inputs=2:channel_layout=stereo,dynaudnorm[m]" -map "[m]" -ar 16000 "$FULL"
ffmpeg -hide_banner -loglevel error -y -i "$FULL" -f segment -segment_time "$CHUNK" -ac 2 -ar 16000 \
  -c:a libmp3lame -b:a 32k "$OUT/chunk-%03d.mp3"
echo "full mix: $FULL ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$FULL") s)"
for f in "$OUT"/chunk-*.mp3; do
  SZ=$(stat -f%z "$f")
  [ "$SZ" -lt 5000000 ] || die "$f is $SZ bytes, over the 5 MB upload limit - use a smaller --chunk-sec"
  printf '%s  %s bytes  %s s\n' "$(basename "$f")" "$SZ" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")"
done
echo "next: python3 -I $HERE/transcribe.py --chunks-dir $OUT --chunk-sec $CHUNK --out transcript.md --title ... --language ... --participants ..."
