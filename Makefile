test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m aixsecurity audit examples/demo --output runs/demo.json

install:
	python3 -m pip install -e .
