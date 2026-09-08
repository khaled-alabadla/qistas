# Qistas — dev shortcuts. All real work happens inside Docker (docs/adr/0023).
DC = docker compose
RUN = $(DC) run --rm web

.PHONY: help build up down logs shell migrate makemigrations test lint fmt css \
        messages compilemessages sync-roles check-deploy superuser

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

build: ## Build the web image
	$(DC) build

up: ## Start the stack
	$(DC) up

down: ## Stop the stack
	$(DC) down

logs: ## Tail web logs
	$(DC) logs -f web

shell: ## Django shell
	$(RUN) python manage.py shell

migrate: ## Apply migrations
	$(RUN) python manage.py migrate

makemigrations: ## Create migrations
	$(RUN) python manage.py makemigrations

test: ## Run the test suite
	$(RUN) pytest

lint: ## ruff check + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt: ## ruff auto-fix + format
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

css: ## Rebuild Tailwind CSS
	$(RUN) ./bin/tailwindcss -i static/src/app.css -o static/css/app.css --minify

messages: ## Extract translatable strings (ar)
	$(RUN) python manage.py makemessages -l ar --no-location

compilemessages: ## Compile .po -> .mo
	$(RUN) python manage.py compilemessages

sync-roles: ## Sync groups -> permissions
	$(RUN) python manage.py sync_roles

check-deploy: ## Production deploy checklist
	$(RUN) env DJANGO_SETTINGS_MODULE=config.settings.prod \
	  DJANGO_SECRET_KEY=x DJANGO_ALLOWED_HOSTS=example.ps \
	  python manage.py check --deploy

superuser: ## Create a superuser
	$(RUN) python manage.py createsuperuser
