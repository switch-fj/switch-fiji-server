dev:
	uv run fastapi dev app/main.py

prod:
	uv run fastapi run app/main.py

lint:
	uv run ruff check . --fix
	uv run ruff format .
