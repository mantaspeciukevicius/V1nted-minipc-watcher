PYTHON ?= python3

.PHONY: test check

test:
	PYTHONPATH=app $(PYTHON) -m unittest discover -s tests -v

check:
	docker compose config -q
