# record - lossless, supervised recording on macOS

```bash
brew install sox ffmpeg
RECORD_PREFIX=workshop ./start-recording.sh    # 30-minute 24-bit FLAC segments
./status.sh
RECORD_PREFIX=workshop ./stop-recording.sh
RECORD_PREFIX=workshop ./finish-recording.sh workshop-2026-03-12   # join, read-only, checksums
```

Grant the terminal microphone access first (System Settings > Privacy > Microphone). Keep the
laptop on power with the lid open. Copy the finished files off the machine the same day.
