class EmailType:
    def __init__(self, name: str, slug: str, subject: str, template: str, body: dict):
        self.name = name
        self.slug = slug
        self.subject = subject
        self.template = template
        self.body = body


class EmailTemplates:
    EMAIL_VERIFICATION = EmailType(
        name="Email verification",
        slug="email_verification",
        subject="Confirm your email.",
        template="email_verification.html",
        body={"first_name": "John", "verification_url": "https://sample.com"},
    )
    PWD_RESET = EmailType(
        name="Password reset",
        slug="password_reset",
        subject="Password reset",
        template="pwd_reset.html",
        body={"first_name": "John", "reset_url": "https://sample.com"},
    )

    def all_templates(self):
        return {
            self.EMAIL_VERIFICATION.name: self.EMAIL_VERIFICATION,
            self.PWD_RESET.name: self.PWD_RESET,
        }

    def get_template_by_slug(self, slug: str):
        return next(
            (template for _, template in self.all_templates().items() if template.slug == slug),
            None,
        )
