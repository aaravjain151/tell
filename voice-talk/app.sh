#!/usr/bin/env bash
# One command: voice-talk on http://127.0.0.1:8765 (loopback only), with a local OpenAI-compatible LLM server.
# Uses the uv venv at ~/.venvs/voice-talk (override with VT_PY). Extra args go to run.py (e.g. --tts 1.7B).
#
# Machine-local choices live in .env.local (gitignored), e.g.:
#   VT_BACKEND=lmstudio          # lmstudio | ollama | llamacpp | vllm | jan | custom
#   VT_LLM_MODEL=some-model-id   # optional; default: the first chat model the server offers (or pick it in the page)
#   VT_LLM_URL=http://127.0.0.1:8080/v1   # optional: any other OpenAI-compatible loopback endpoint (backend becomes custom)
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env.local ]; then set -a; . ./.env.local; set +a; fi
PY="${VT_PY:-$HOME/.venvs/voice-talk/bin/python}"
PORT="${VT_PORT:-8765}"
export VT_BACKEND="${VT_BACKEND:-lmstudio}"

case "$VT_BACKEND" in
  lmstudio) PROBE=http://127.0.0.1:1234/v1/models ;;
  ollama)   PROBE=http://127.0.0.1:11434/v1/models ;;
  llamacpp) PROBE=http://127.0.0.1:8080/v1/models ;;
  vllm)     PROBE=http://127.0.0.1:8000/v1/models ;;
  jan)      PROBE=http://127.0.0.1:1337/v1/models ;;
  *)        PROBE="${VT_LLM_URL:-http://127.0.0.1:1234/v1}/models" ;;
esac

if ! curl -fsS -m 3 "$PROBE" >/dev/null 2>&1; then
  if [ "$VT_BACKEND" = "ollama" ]; then
    echo "[app] starting ollama serve"
    nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
    for _ in $(seq 1 20); do curl -fsS -m 3 "$PROBE" >/dev/null 2>&1 && break; sleep 0.5; done
  else
    echo "[app] warning: no model server answering at $PROBE. Start it (LM Studio: lms server start; load a model), or pick another server in the page." >&2
  fi
fi

[ -d voices/sanath ] || echo "[app] no 'sanath' voice yet: see README (tools/import_voice.py)"
(sleep 4 && open "http://127.0.0.1:${PORT}") >/dev/null 2>&1 &
exec "$PY" run.py --port "$PORT" "$@"
