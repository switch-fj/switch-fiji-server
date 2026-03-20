dev:
	uv run fastapi dev app/main.py

prod:
	uv run fastapi run app/main.py

lint:
	uv run ruff check . --fix
	uv run ruff format .

m ?= "auto migration"

alembic-gen:
	uv run alembic revision --autogenerate -m "$(m)"

alembic-up:
	uv run alembic upgrade head