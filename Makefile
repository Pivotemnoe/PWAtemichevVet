PYTHON ?= .venv/bin/python

.PHONY: run check

run:
	$(PYTHON) -m app.main

check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app scripts
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_project.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_api.py
	node --check web/app.js
	$(PYTHON) -m json.tool web/manifest.webmanifest >/dev/null
