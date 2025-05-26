UV ?= $(HOME)/.local/bin/uv

.PHONY: install-uv
install-uv:
	curl -LsSf https://astral.sh/uv/install.sh | sh

.PHONY: install-packages
install-packages:
	$(UV) sync -vv $(opts)

.PHONY: install
install: install-uv install-packages

.PHONY: run-server
run-server: 
	$(UV) run python manage.py runserver

.PHONY: uvicorn-server
uvicorn-server:
	$(UV) run uvicorn account.asgi:application --host 0.0.0.0
