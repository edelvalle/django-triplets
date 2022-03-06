
.PHONY: install check test coverage profile shell migrations


install:
	pip install --upgrade pip
	pip install -e .[dev]
	python setup.py develop

check:
	black --check --diff triplets/
	pyright

test:
	cd tests; python manage.py test triplets

coverage:
	cd tests; coverage run manage.py test triplets --keepdb; coverage report

profile:
	cd tests; kernprof -l manage.py test triplets
	python -m line_profiler tests/manage.py.lprof

shell:
	cd tests; python manage.py shell

migrations:
	cd tests; python manage.py makemigrations
