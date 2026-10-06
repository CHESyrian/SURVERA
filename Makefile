.PHONY: help install migrate run test lint format makemessages compilemessages

help:
	@echo "SURVERA – common commands"
	@echo ""
	@echo "  make install     Install dependencies (editable + dev)"
	@echo "  make migrate     Run database migrations"
	@echo "  make run         Start development server"
	@echo "  make test        Run tests"
	@echo "  make lint        Run ruff check"
	@echo "  make format      Run ruff format"

install:
	pip install -e ".[dev]"

migrate:
	python manage.py migrate

run:
	python manage.py runserver

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

makemessages:
	django-admin makemessages -l ar -l en --ignore=.venv --ignore=staticfiles --ignore=media

compilemessages:
	django-admin compilemessages --ignore=.venv
