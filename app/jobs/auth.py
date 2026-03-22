from app.core.mail import Mailer
from app.jobs.async_runner import run_async
from app.jobs.celery import celery_app


@celery_app.task(name="send_email_verification_task", bind=True, max_retries=3, default_retry_delay=5)
def send_email_verification_task(self, *args, **kwargs):
    email = kwargs.get("email") or args[0]
    verification_url = kwargs.get("verification_url") or args[1]

    try:
        run_async(Mailer.send_email_verification(email=email, verification_url=verification_url))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="send_password_reset_task", bind=True, max_retries=3, default_retry_delay=5)
def send_password_reset_task(self, *args, **kwargs):
    email = kwargs.get("email") or args[0]
    reset_url = kwargs.get("reset_url") or args[1]
    try:
        run_async(Mailer.send_password_reset(email=email, reset_url=reset_url))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="send_verify_login_task", bind=True, max_retries=3, default_retry_delay=5)
def send_verify_login_task(self, *args, **kwargs):
    email = kwargs.get("email") or args[0]
    text = kwargs.get("text") or args[1]
    try:
        run_async(Mailer.send_verify_login(email=email, text=text))
    except Exception as exc:
        raise self.retry(exc=exc)
