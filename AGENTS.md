# Repository Guidelines

## Project Structure & Module Organization

This repository is a Django monolith. Project configuration lives in `config/`, while business domains live under `apps/`, including `inventory`, `sales`, `partners`, `companies`, `users`, and versioned APIs in `apps/api/v1/`. Keep models, forms, selectors, services, URLs, and views inside the owning domain. HTML templates are grouped by feature in `templates/`; browser assets belong in `static/css/` and `static/js/`. Tests sit in `apps/<app>/tests/`. Commit schema changes as Django migrations.

## Build, Test, and Development Commands

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
pip install -r requirements.txt
```

Copy `.env.example` to `.env` before running locally. Common commands are:

- `python manage.py migrate` — apply database migrations.
- `python manage.py runserver` — serve the app at `http://127.0.0.1:8000/`.
- `python manage.py test` — run the full Django test suite.
- `python manage.py test apps.inventory` — run one app's tests.
- `python manage.py makemigrations --check --dry-run` — detect missing migrations.
- `docker compose -f docker-compose_apudig.yml up --build` — run Django with PostgreSQL.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants. Keep views thin; place workflows in `services.py` and reusable queries in `selectors.py`. Name templates by feature, for example `templates/inventory/product_form.html`. No formatter or linter is configured, so match nearby code.

## Testing Guidelines

Tests use Django's `TestCase` and `test_*.py` discovery. Name test methods for observable behavior, such as `test_entry_increases_stock`. Add focused tests for service rules, model constraints, permissions, and HTTP responses. Run the relevant app tests during development and the full suite before opening a pull request. No coverage threshold is enforced; changes should nevertheless cover regressions and important branches.

## Commit & Pull Request Guidelines

Recent history mixes concise imperative messages with Conventional Commit-style subjects such as `fix(product): ...` and `feat(inventory): ...`. Prefer the latter: `type(scope): imperative summary`. Keep commits focused and include migrations with their model changes. Pull requests should explain the problem and solution, list verification commands, link the issue when available, and include screenshots for template or UI changes. Call out migrations, environment changes, and backward-compatibility concerns explicitly.

## Security & Configuration

Never commit `.env`, credentials, or production data. Add new settings to `.env.example` with safe placeholders. Treat `db.sqlite3` as local development data and validate company/store scoping when changing queries or permissions.
