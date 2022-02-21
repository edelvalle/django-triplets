
.PHONY: test install


install:
	pip install --upgrade pip
	pip install -e .[dev]
	python setup.py develop

test:
	cd tests; python manage.py test triplets
