# Personal Makefile for ha-matrix-e2ee
# Mirrors .github/workflows/tests.yml so `make check` == CI.
# All Python runs through `uv run` (project venv, Python 3.14) per AGENTS.md.

SHELL      := /bin/sh
UV         := uv
PY         := $(UV) run python
MANIFEST   := custom_components/matrix_e2ee/manifest.json
COMPONENT  := custom_components/matrix_e2ee
COV_MIN   ?= 81
DIST       := dist

# Version handling: CURRENT is read from the manifest (single source of truth);
# VERSION defaults to CURRENT and is overridden by `make <target> VERSION=x.y.z`.
CURRENT := $(shell test -d .venv && $(PY) -c "import json;print(json.load(open('$(MANIFEST)'))['version'])" 2>/dev/null || echo unknown)
VERSION ?= $(CURRENT)

.DEFAULT_GOAL := help
.PHONY: help setup check-python lint format format-check test test-file cov-html audit check version bump dist release clean distclean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} \
		/^[a-zA-Z_-]+:.*?##/ {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)}' $(MAKEFILE_LIST)

##@ Setup
setup: check-python ## Create .venv (Python 3.14) and install dev dependencies
	@test -d .venv || $(UV) venv --python 3.14 .venv
	$(UV) pip install -r requirements-dev.txt
	@$(PY) -c "import homeassistant; print('homeassistant', homeassistant.__version__)"

check-python: ## Verify the project venv really is Python 3.14.x
	@v=$$($(PY) --version 2>/dev/null | awk '{print $$2}'); \
	case $$v in \
		3.14.*) echo "python $$v (ok)" ;; \
		*) echo "ERROR: expected Python 3.14.x, got '$$v'."; \
		   echo "Fix with: rm -rf .venv && $(UV) venv --python 3.14 .venv && $(MAKE) setup"; exit 1 ;; \
	esac

##@ Quality (CI parity)
lint: check-python ## Ruff lint (same as CI)
	$(UV) run ruff check custom_components/ tests/

format: check-python ## Ruff format (writes changes)
	$(UV) run ruff format custom_components/ tests/

format-check: check-python ## Ruff format check (same as CI)
	$(UV) run ruff format --check custom_components/ tests/

test: check-python ## Run tests with coverage (same as CI, COV_MIN=$(COV_MIN))
	$(PY) -m pytest --cov=$(COMPONENT) --cov-fail-under=$(COV_MIN)

test-file: check-python ## Run a single test file: make test-file T=tests/test_options_flow.py
	@test -n "$(T)" || { echo "usage: make test-file T=tests/test_x.py[::test_name]"; exit 2; }
	$(PY) -m pytest --no-cov -x -q $(T)

cov-html: test ## Generate and open the HTML coverage report
	$(PY) -m coverage html
	@open htmlcov/index.html 2>/dev/null || echo "report at htmlcov/index.html"

audit: check-python ## pip-audit runtime deps from manifest.json (same as CI)
	@mkdir -p $(DIST)
	@$(PY) -c "import json; print('\n'.join(json.load(open('$(MANIFEST)'))['requirements']))" > $(DIST)/runtime-requirements.txt
	$(UV) run pip-audit --requirement $(DIST)/runtime-requirements.txt

check: lint format-check test audit ## Run everything CI runs - do this before pushing

##@ Release
version: ## Print the current version from manifest.json
	@echo "$(VERSION)"

bump: check-python ## Bump manifest version only: make bump VERSION=x.y.z
	@test "$(CURRENT)" != "unknown" || { echo "ERROR: cannot read current version from $(MANIFEST)"; exit 1; }
	@test "$(origin VERSION)" = "command line" || { echo "usage: make bump VERSION=x.y.z"; exit 2; }
	@test "$(VERSION)" != "$(CURRENT)" || { echo "ERROR: VERSION=$(VERSION) is already the current version"; exit 1; }
	@case "$(VERSION)" in [0-9]*.[0-9]*.[0-9]*) ;; *) echo "ERROR: VERSION must be x.y.z, got '$(VERSION)'"; exit 1;; esac
	@$(PY) -c "import json,re,sys; m='$(MANIFEST)'; new=sys.argv[1]; json.load(open(m)); s=open(m).read(); s,n=re.subn(r'\"version\": \"[^\"]+\"', '\"version\": \"'+new+'\"', s); assert n==1, 'version key not found'; open(m,'w').write(s)" $(VERSION)
	@echo "manifest.json: $(CURRENT) -> $(VERSION) (update CHANGELOG.md and commit)"

dist: ## Package the component zip: dist/matrix_e2ee-v$(VERSION).zip
	@test "$(CURRENT)" != "unknown" || { echo "ERROR: cannot read version from $(MANIFEST)"; exit 1; }
	@mkdir -p $(DIST)
	cd custom_components && zip -qr ../$(DIST)/matrix_e2ee-v$(VERSION).zip matrix_e2ee -x '*/__pycache__/*' '*.pyc'
	@echo "$(DIST)/matrix_e2ee-v$(VERSION).zip"

release: ## Full release: checks, bump, zip, commit, tag: make release VERSION=x.y.z
	@test -n "$(filter command line,$(origin VERSION))" || { echo "usage: make release VERSION=x.y.z"; exit 2; }
	@$(MAKE) --no-print-directory check
	@$(MAKE) --no-print-directory bump VERSION=$(VERSION)
	@$(MAKE) --no-print-directory dist
	git add $(MANIFEST)
	git commit -m "release: publish v$(VERSION)"
	git tag "v$(VERSION)"
	@echo ""
	@echo "Release v$(VERSION) committed and tagged. When ready:"
	@echo "  git push origin main v$(VERSION)   # then upload $(DIST)/matrix_e2ee-v$(VERSION).zip"

##@ Maintenance
clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov $(DIST)

distclean: clean ## Also remove the venv (full reset: make distclean setup)
	rm -rf .venv
