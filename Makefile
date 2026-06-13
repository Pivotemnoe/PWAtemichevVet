PYTHON ?= .venv/bin/python
NODE ?= node

.PHONY: run check

run:
	$(PYTHON) -m app.main

check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app scripts
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_project.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_api.py
	$(NODE) --check web/app.js
	$(NODE) --check web/sw.js
	$(PYTHON) -m json.tool web/manifest.webmanifest >/dev/null
