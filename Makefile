dev:
	uv run fastapi dev app

lint:
	uv run ruff check . --fix
	uv run ruff format .

worker:
	redis-cli FLUSHALL && uv run celery -A app.jobs.celery worker --loglevel=INFO --pool=solo --without-gossip --without-mingle --without-heartbeat

beat:
	uv run celery -A app.jobs.celery beat --loglevel=INFO

alembic-gen:
	uv run alembic revision --autogenerate -m "$(m)"

alembic-upgrade:
	uv run alembic upgrade head

alembic-stamp:
	uv run alembic stamp head

mail-preview:
	uv run fastapi dev app/templates/email_app.py
