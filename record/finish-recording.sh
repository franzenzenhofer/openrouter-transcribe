#!/bin/zsh
# After stopping: join the segments into one FLAC + a 16 kHz MP3, make everything read-only,
# and write SHA256SUMS.txt. Usage: ./finish-recording.sh <output-name>
set -euo pipefail
cd "$(dirname "$0")"
name=${1:?usage: finish-recording.sh <output-name>}
parts=("${(@f)$(ls "${RECORD_PREFIX:-session}"-*-part*.flac | sort)}")
sox "${parts[@]}" "$name.flac"
ffmpeg -nostdin -loglevel error -i "$name.flac" -ar 16000 -ac 1 -b:a 64k "$name-16k.mp3"
chmod a-w "${parts[@]}" "$name.flac" "$name-16k.mp3"
shasum -a 256 "${parts[@]}" "$name.flac" "$name-16k.mp3" >> SHA256SUMS.txt
shasum -a 256 -c SHA256SUMS.txt
