#!/usr/bin/env bash
# Push every clip through a phone-grade codec chain and back to 16 kHz WAV, so eval can report clean vs opus-8k.
#   tools/redteam/degrade.sh [dir=data/calls]
# For <stem>.wav writes <stem>.opus8k.wav (+ copies <stem>.txt to <stem>.opus8k.txt). Idempotent; skips *.opus8k.wav and *.replayed.wav.
# Chain: libopus 12 kbps @ 8 kHz  ->  decode  ->  16 kHz mono PCM wav.
set -euo pipefail
DIR="${1:-data/calls}"
command -v ffmpeg >/dev/null || { echo "ffmpeg not found (brew install ffmpeg)" >&2; exit 2; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
n=0
shopt -s nullglob
for f in "$DIR"/*.wav; do
  case "$f" in *.opus8k.wav|*.replayed.wav) continue;; esac
  stem="${f%.wav}"
  ffmpeg -loglevel error -y -i "$f" -ac 1 -c:a libopus -b:a 12k -ar 8000 "$tmp/x.ogg"
  ffmpeg -loglevel error -y -i "$tmp/x.ogg" -ar 16000 -ac 1 -c:a pcm_s16le "${stem}.opus8k.wav"
  [ -f "${stem}.txt" ] && cp "${stem}.txt" "${stem}.opus8k.txt"
  n=$((n+1))
done
echo "degraded $n clip(s) in $DIR"
