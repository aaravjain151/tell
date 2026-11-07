.PHONY: setup lock test eval api web demo models redteam record wild audit
PY=./.venv/bin/python
LOCK=services/api/requirements.lock
MODELS_LOCK=services/api/requirements-models.lock

# Pinned install. Uses uv when present (fast), plain venv + pip otherwise. Additive: never removes `make models` deps.
setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv -q --allow-existing .venv && uv pip install -q --python $(PY) -r $(LOCK); \
	else \
		python3 -m venv .venv && $(PY) -m pip install -q -r $(LOCK); \
	fi
	@echo "setup ok: $$($(PY) --version), deps from $(LOCK)"

# Re-pin after editing services/api/requirements*.txt or tools/redteam/requirements.txt (the tests import the red-team engines). Needs uv; commit both .lock files.
lock:
	cd services/api && uv pip compile -q --universal --python-version 3.11 requirements.txt ../../tools/redteam/requirements.txt -o requirements.lock
	cd services/api && uv pip compile -q --universal --python-version 3.11 requirements-models.txt ../../tools/redteam/requirements.txt -o requirements-models.lock

test:
	cd services/api && ../../.venv/bin/python -m pytest -q
eval:
	cd services/api && ../../.venv/bin/python eval/run_eval.py $(ARGS)
api:
	cd services/api && ../../.venv/bin/python -m uvicorn doublespeak.main:app --reload --port 8000 --env-file ../../.env
web:
	cd apps/web && python3 -m http.server 5173 --bind 127.0.0.1

# Heavy local voters: install their pinned packages, then download weights once (online). Then set DOUBLESPEAK_OFFLINE=1.
models:
	@if command -v uv >/dev/null 2>&1; then uv pip install -q --python $(PY) -r $(MODELS_LOCK); else $(PY) -m pip install -q -r $(MODELS_LOCK); fi
	$(PY) tools/models/prefetch.py

# The stage setup: API + web on loopback, models forced offline (Wi-Fi can be off). Ctrl-C stops both.
demo:
	@test -x $(PY) || { echo "run 'make setup' first"; exit 2; }
	@echo "Doublespeak demo · UI http://localhost:5173 · API http://localhost:8000/health · offline models · Ctrl-C to stop"
	@trap 'kill 0' INT TERM EXIT; \
	(cd services/api && DOUBLESPEAK_OFFLINE=1 ../../.venv/bin/python -m uvicorn doublespeak.main:app --host 127.0.0.1 --port 8000 --env-file ../../.env) & \
	(cd apps/web && python3 -m http.server 5173 --bind 127.0.0.1) & \
	wait

redteam:
	$(PY) tools/redteam/make_calls.py --out data/calls $(ARGS)
record:
	$(PY) tools/redteam/capture.py human --free $(ARGS)
wild:
	bash tools/redteam/degrade.sh data/calls && cd services/api && ../../.venv/bin/python eval/run_eval.py --wild ../../data/calls $(ARGS)
audit:
	python3 scripts/pm.py audit
