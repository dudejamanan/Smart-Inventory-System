.PHONY: install test build simulate hardware scenarios markers
PYTHON ?= python
install:
	$(PYTHON) -m pip install -r backend/requirements.lock.txt
	npm ci --prefix frontend
test:
	$(PYTHON) -m pytest -q
build:
	npm run build --prefix frontend
simulate:
	cd backend && $(PYTHON) -m app --simulate
hardware:
	cd backend && $(PYTHON) -m app
scenarios:
	$(PYTHON) tools/fake_scenarios.py
markers:
	$(PYTHON) tools/print_markers.py --output data/markers.pdf
