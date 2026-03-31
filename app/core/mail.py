from pathlib import Path
from typing import Dict, List, Optional, Union

import resend
from fastapi import UploadFile
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Environment, FileSystemLoader
from pydantic import EmailStr

from app.core.config import Config
from app.core.template_registry import TemplateRegistry
from app.shared.schema import MailTypes
from app.templates.libs.context import get_template_context

_registry = TemplateRegistry()

templates_env = Environment(loader=FileSystemLoader(str(_registry.TEMPLATES_DIR)))

ROOT_DIR = Path(__file__).resolve().parent.parent

resend.api_key = Config.RESEND_API_KEY

mail_config = ConnectionConfig(
    MAIL_USERNAME=Config.MAIL_USERNAME,
    MAIL_PASSWORD=Config.MAIL_PASSWORD,
    MAIL_FROM=Config.MAIL_FROM,
    MAIL_PORT=int(Config.MAIL_PORT),
    MAIL_SERVER=Config.MAIL_SERVER,
    MAIL_STARTTLS=Config.MAIL_STARTTLS in [True, "True", "true", 1, "1"],
    MAIL_SSL_TLS=Config.MAIL_SSL_TLS in [True, "True", "true", 1, "1"],
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(ROOT_DIR, "templates"),
)


class Mailer:
    mail = FastMail(config=mail_config)
    use_resend = Config.USE_RESEND in [True, "True", "true", 1, "1"]

    @staticmethod
    def _render_template(template_name: str, context: dict) -> str:
        template = templates_env.get_template(template_name)
        return template.render(**context)

    @staticmethod
    def _send_via_resend(to: str, subject: str, template_name: str, context: dict):
        html = Mailer._render_template(template_name, context)
        resend.Emails.send(
            {
                "from": "switch.fj <noreply@contact.switch.com.fj>",
                "to": to,
                "subject": subject,
                "html": html,
            }
        )

    @staticmethod
    def _create_message(
        recipients: List[EmailStr],
        attachments: List[Union[UploadFile, Dict, str]] = [],
        subject: str = "",
        body: Optional[Union[List, str]] = None,
        template_body: Optional[Union[List, str]] = None,
    ) -> MessageSchema:
        return MessageSchema(
            recipients=recipients,
            attachments=attachments,
            subject=subject,
            body=body,
            template_body=template_body,
            subtype=MessageType.html,
        )

    @staticmethod
    async def send_email_verification(email: str, verification_url: str):
        context = get_template_context(verification_url=verification_url)

        if Mailer.use_resend:
            Mailer._send_via_resend(
                to=email,
                subject=MailTypes.EMAIL_VERIFICATION.subject,
                template_name=MailTypes.EMAIL_VERIFICATION.template,
                context=context,
            )
            return

        message = Mailer._create_message(
            recipients=[email],
            subject=MailTypes.EMAIL_VERIFICATION.subject,
            template_body=context,
        )
        await Mailer.mail.send_message(message=message, template_name=MailTypes.EMAIL_VERIFICATION.template)

    @staticmethod
    async def send_password_reset(email: str, reset_url: str):
        context = get_template_context(reset_url=reset_url)

        if Mailer.use_resend:
            Mailer._send_via_resend(
                to=email,
                subject=MailTypes.PWD_RESET.subject,
                template_name=MailTypes.PWD_RESET.template,
                context=context,
            )
            return

        message = Mailer._create_message(
            recipients=[email],
            subject=MailTypes.PWD_RESET.subject,
            template_body=context,
        )
        await Mailer.mail.send_message(message=message, template_name=MailTypes.PWD_RESET.template)

    @staticmethod
    async def send_verify_login(email: str, text: str):
        context = get_template_context(email=email, text=text)

        if Mailer.use_resend:
            Mailer._send_via_resend(
                to=email,
                subject=MailTypes.VERIFY_LOGIN.subject,
                template_name=MailTypes.VERIFY_LOGIN.template,
                context=context,
            )
            return

        message = Mailer._create_message(
            recipients=[email],
            subject=MailTypes.VERIFY_LOGIN.subject,
            template_body=context,
        )
        await Mailer.mail.send_message(message=message, template_name=MailTypes.VERIFY_LOGIN.template)
