
.PHONY: test install shell migrations


install:
	pip install --upgrade pip
	pip install -e .[dev]
	python setup.py develop

test:
	cd tests; python manage.py test triplets --keepdb

coverage:
	cd tests; coverage run manage.py test triplets --keepdb; coverage report

shell:
	cd tests; python manage.py shell

migrations:
	cd tests; python manage.py makemigrations
