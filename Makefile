SRC := wanderer.py plot.py

.PHONY: lint
lint: $(SRC)
	flake8 $^ || echo '[!] flake8 failed'
	mypy $^ || echo '[!] mypy failed'
