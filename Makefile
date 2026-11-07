.PHONY: setup test eval api web redteam record wild audit
PY=./.venv/bin/python
setup:
	python3 -m venv .venv && ./.venv/bin/pip install -q -r services/api/requirements.txt
test:
	cd services/api && ../../.venv/bin/python -m pytest -q
eval:
	cd services/api && ../../.venv/bin/python eval/run_eval.py $(ARGS)
api:
	cd services/api && ../../.venv/bin/python -m uvicorn tell.main:app --reload --port 8000 --env-file ../../.env
web:
	cd apps/web && python3 -m http.server 5173
redteam:
	$(PY) tools/redteam/make_calls.py --out data/calls $(ARGS)
audit:
	python3 scripts/pm.py audit
