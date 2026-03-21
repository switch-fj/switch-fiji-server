dev:
	uv run fastapi dev app/main.py

prod:
	uv run fastapi run app/main.py

lint:
	uv run ruff check . --fix
	uv run ruff format .

alembic-gen:
	uv run alembic revision --autogenerate -m "$(m)"

alembic-up:
	uv run alembic upgrade head

mail-preview:
	uv run fastapi dev app/templates/email_app.py
