
.PHONY: install check test coverage coverage-html profile shell migrations


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

coverage-html:
	cd tests; coverage run manage.py test triplets --keepdb; coverage html
	echo Open: "file://`pwd`/tests/htmlcov/index.html"

profile:
	cd tests; kernprof -l manage.py test triplets
	python -m line_profiler tests/manage.py.lprof

shell:
	cd tests; python manage.py shell

migrations:
	cd tests; python manage.py makemigrations
