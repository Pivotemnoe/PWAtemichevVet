PYTHON ?= .venv/bin/python
NODE ?= node

.PHONY: run check max-webhook

run:
	$(PYTHON) -m app.main

max-webhook:
	$(PYTHON) scripts/setup_max_webhook.py

check:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m compileall -q app scripts
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_project.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_api.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_retention.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_billing.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/test_monitor_public.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest scripts.test_llm_model_routing
	$(NODE) scripts/test_frontend_attribution.mjs
	$(NODE) scripts/test_check_save_flow.mjs
	$(NODE) scripts/test_check_save_validation.mjs
	$(PYTHON) -m unittest scripts.test_mobile_api scripts.test_pet_photos_offline
	$(NODE) --test scripts/test_mobile.mjs scripts/test_offline.mjs
	$(NODE) --check web/app.js
	$(NODE) --check web/retention.js
	$(NODE) --check web/sw.js
	$(PYTHON) -m json.tool web/manifest.webmanifest >/dev/null
