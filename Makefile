.PHONY: install doctor reindex test lint

install:
	./install.sh

doctor:
	./install.sh --doctor

reindex:
	./install.sh --reindex

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check moodlist/ tests/
