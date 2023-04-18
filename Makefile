POETRY ?= $(HOME)/.local/bin/poetry

.PHONY: install-poetry
install-poetry:
	curl -sSL https://install.python-poetry.org | python3 -

.PHONY: install-packages
install-packages:
	$(POETRY) install -vv $(opts)

.PHONY: install
install: install-poetry install-packages

.PHONY: run-server
run-server: 
	$(POETRY) run python manage.py runserver
