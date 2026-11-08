.PHONY: setup lock test eval api web demo models redteam record wild audit
PY=./.venv/bin/python
VPY=$(CURDIR)/.venv/bin/python
# uvicorn refuses a missing --env-file, so a fresh clone without .env must not pass one
ENVFILE=$(if $(wildcard .env),--env-file $(CURDIR)/.env,)
LOCK=services/api/requirements.lock
MODELS_LOCK=services/api/requirements-models.lock
# first interpreter >= 3.11 on PATH (macOS /usr/bin/python3 is 3.9 and cannot install the lock)
SYSPY:=$(shell for p in python3.13 python3.12 python3.11 python3; do command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && { echo $$p; break; }; done)

# Pinned install. Uses uv when present (fast), plain venv + pip otherwise. Additive: never removes `make models` deps.
setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv -q --allow-existing --python '>=3.11' .venv && uv pip install -q --python $(PY) -r $(LOCK); \
	else \
		test -n "$(SYSPY)" || { echo "need Python >= 3.11 (brew install python@3.12) or uv (brew install uv)"; exit 2; }; \
		$(SYSPY) -m venv .venv && $(PY) -m pip install -q --upgrade pip && $(PY) -m pip install -q -r $(LOCK); \
	fi
	@echo "setup ok: $$($(PY) --version), deps from $(LOCK)"

# Re-pin after editing services/api/requirements*.txt or tools/redteam/requirements.txt (the tests import the red-team engines). Needs uv; commit both .lock files.
lock:
	cd services/api && uv pip compile -q --universal --python-version 3.11 requirements.txt ../../tools/redteam/requirements.txt -o requirements.lock
	cd services/api && uv pip compile -q --universal --python-version 3.11 requirements-models.txt ../../tools/redteam/requirements.txt -o requirements-models.lock

test:
	cd services/api && $(VPY) -m pytest -q
eval:
	cd services/api && $(VPY) eval/run_eval.py $(ARGS)
api:
	cd services/api && $(VPY) -m uvicorn doublespeak.main:app --reload --port 8000$(if $(ENVFILE), $(ENVFILE),)
web:
	cd apps/web && python3 -m http.server 5173 --bind 127.0.0.1
# Android app (apps/android): the engine must accept the app's origins. http://localhost = the installed app (Capacitor),
# :5173 = the PWA opened in Chrome on the phone. All loopback; the phone reaches it through `adb reverse` only.
api-android:
	cd services/api && DOUBLESPEAK_CORS_ORIGINS=http://localhost,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000 $(VPY) -m uvicorn doublespeak.main:app --port 8000$(if $(ENVFILE), $(ENVFILE),)
android-pwa:
	cd apps/android && python3 -m http.server 5173 --bind 127.0.0.1

# Heavy local voters: install their pinned packages, then download weights once (online). Then set DOUBLESPEAK_OFFLINE=1.
models:
	@if command -v uv >/dev/null 2>&1; then uv pip install -q --python $(PY) -r $(MODELS_LOCK); else $(PY) -m pip install -q -r $(MODELS_LOCK); fi
	$(PY) tools/models/prefetch.py

# The stage setup: API + web on loopback, models forced offline (Wi-Fi can be off). Ctrl-C stops both.
demo:
	@test -x $(PY) || { echo "run 'make setup' first"; exit 2; }
	@echo "Doublespeak demo · UI http://localhost:5173 · API http://localhost:8000/health · offline models · Ctrl-C to stop"
	@(cd services/api && DOUBLESPEAK_OFFLINE=1 exec $(VPY) -m uvicorn doublespeak.main:app --host 127.0.0.1 --port 8000$(if $(ENVFILE), $(ENVFILE),)) & API=$$!; \
	(cd apps/web && exec python3 -m http.server 5173 --bind 127.0.0.1) & WEB=$$!; \
	trap 'kill $$API $$WEB 2>/dev/null; wait' INT TERM EXIT; \
	wait

redteam:
	$(PY) tools/redteam/make_calls.py --out data/calls $(ARGS)
record:
	$(PY) tools/redteam/capture.py human --free $(ARGS)
wild:
	bash tools/redteam/degrade.sh data/calls && cd services/api && $(VPY) eval/run_eval.py --wild ../../data/calls $(ARGS)
audit:
	python3 scripts/pm.py audit
