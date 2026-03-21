from pathlib import Path

import fastapi
import fastapi.responses
import fastapi.templating

from app.core.template_registry import TemplateRegistry
from app.shared.mail import EmailTemplates
from app.templates.libs.context import get_template_context

ROOT_DIR = Path(__file__).resolve().parent.parent

email_app = fastapi.FastAPI(title="Email Template Preview")
template_registry = TemplateRegistry()

templates = fastapi.templating.Jinja2Templates(directory=str(template_registry.TEMPLATES_DIR))
template_registry.mount_static(app=email_app)
email_templates = EmailTemplates()


@email_app.get("/dashboard", response_class=fastapi.responses.HTMLResponse)
async def home(request: fastapi.Request, t: str = email_templates.EMAIL_VERIFICATION.slug):
    all_email_templates = email_templates.all_templates()
    context = get_template_context(
        request=request,
        all_email_templates=all_email_templates,
        slug=t,
    )
    return templates.TemplateResponse("/email_index.html", context=context)


@email_app.get("/render_email", response_class=fastapi.responses.HTMLResponse)
async def email_template(request: fastapi.Request, t: str = email_templates.EMAIL_VERIFICATION.slug):
    selected_template = email_templates.get_template_by_slug(t)
    context = get_template_context(
        request=request,
        slug=t,
        **selected_template.body,
    )
    return templates.TemplateResponse(selected_template.template, context=context)


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("📧 Email Template Preview Server")
    print("=" * 50)
    print("🚀 Running on: http://127.0.0.1:8001")
    print("📝 Available routes:")
    print("   • http://127.0.0.1:8001/")
    print("   • http://127.0.0.1:8001/preview/verification")
    print("=" * 50)
    uvicorn.run(email_app, host="0.0.0.0", port=8080)
