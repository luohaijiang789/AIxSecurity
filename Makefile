.PHONY: test check install

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

check:
	python3 scripts/check_project.py

install:
	python3 -m pip install -e .
