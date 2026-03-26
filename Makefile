dev:
	uv run fastapi dev app/main.py

prod:
	uv run fastapi run app/main.py

lint:
	uv run ruff check . --fix
	uv run ruff format .

worker:
	uv run celery -A app.jobs.celery worker --loglevel=INFO --pool=solo --without-gossip --without-mingle --without-heartbeat

beat:
	uv run celery -A app.jobs.celery beat --loglevel=INFO

alembic-gen:
	uv run alembic revision --autogenerate -m "$(m)"

alembic-up:
	uv run alembic upgrade head

mail-preview:
	uv run fastapi dev app/templates/email_app.py
