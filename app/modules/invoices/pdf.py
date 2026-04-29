import base64
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader

from app.core.template_registry import TemplateRegistry
from app.modules.contracts.model import Contract
from app.modules.invoices.model import Invoice, InvoiceLineItem, InvoiceMeterData
from app.modules.settings.model import ContractSettings
from app.shared.schema import DateFormatEnum, TimeFormatEnum
from app.templates.libs.context import get_template_context

_registry = TemplateRegistry()
_env = Environment(
    loader=FileSystemLoader(str(_registry.TEMPLATES_DIR / "invoices")),
    autoescape=True,
)


@lru_cache(maxsize=1)
def fetch_logo_base64() -> str:
    """Read the company logo from disk and encode it as a base64 data URI (cached).

    Returns:
        A data URI string suitable for embedding directly in HTML.
    """
    logo_path = _registry.STATIC_DIR / "images" / "logo-blue.png"
    b64 = base64.b64encode(logo_path.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


class InvoicePDF:
    """Utility class for rendering invoice data into a PDF via Jinja2 and WeasyPrint."""

    @staticmethod
    def _fmt_date(dt: datetime, date_fmt: str, time_fmt: str, show_time: bool = False) -> str:
        """Format a datetime object according to the configured date and time format settings.

        Args:
            dt: The datetime to format.
            date_fmt: A DateFormatEnum value controlling day/month order.
            time_fmt: A TimeFormatEnum value controlling 12h vs 24h time display.
            show_time: If True, appends the time to the formatted date string.

        Returns:
            A formatted date (and optionally time) string.
        """
        date_formats = {
            DateFormatEnum.DMY: "%-d %b %Y",
            DateFormatEnum.MDY: "%b %-d %Y",
        }
        time_formats = {
            TimeFormatEnum.TWELVE: "%I:%M %p",
            TimeFormatEnum.TWENTY_FOUR: "%H:%M",
        }

        fmt = date_formats[date_fmt]

        if show_time:
            fmt = fmt + " " + time_formats[time_fmt]

        return dt.strftime(fmt)

    @staticmethod
    def _fmt_decimal(value) -> str:
        """Format a numeric value as a trimmed decimal string (trailing zeros removed).

        Args:
            value: A numeric value (int, float, or Decimal) to format.

        Returns:
            A string with up to four decimal places and trailing zeros stripped.
        """
        return f"{Decimal(str(value)):.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def render_invoice_pdf(
        invoice: Invoice,
        contract: Contract,
        line_items: list[InvoiceLineItem],
        meter_data: list[InvoiceMeterData],
        contract_settings: ContractSettings,
    ) -> bytes:
        """
        Renders the invoice as PDF bytes.

        Args:
            invoice: Invoice ORM object
            contract: Contract ORM object (with .client and .site loaded)
            line_items: list of InvoiceLineItem ORM objects
            meter_data: list of InvoiceMeterData ORM objects
            contract_settings: contract general settings ORM objects

        Returns:
            PDF as bytes — ready for FastAPI Response or email attachment
        """
        from weasyprint import HTML

        subtotal = invoice.subtotal
        vat_rate = invoice.vat_rate
        vat_amount = subtotal * vat_rate
        total = subtotal + vat_amount
        date_fmt = contract_settings.date_format
        time_fmt = contract_settings.time_format

        context = {
            "base64_logo": fetch_logo_base64(),
            "invoice_ref": invoice.invoice_ref,
            "period_start_at": InvoicePDF._fmt_date(dt=invoice.period_start_at, date_fmt=date_fmt, time_fmt=time_fmt),
            "period_end_at": InvoicePDF._fmt_date(dt=invoice.period_end_at, date_fmt=date_fmt, time_fmt=time_fmt),
            "client_name": contract.client.client_name if contract.client else "—",
            "site_name": (contract.site.site_name or contract.site.gateway_id if contract.site else "—"),
            "subtotal": InvoicePDF._fmt_decimal(subtotal),
            "vat_amount": InvoicePDF._fmt_decimal(vat_amount),
            "total": InvoicePDF._fmt_decimal(total),
            "generated_at": InvoicePDF._fmt_date(
                dt=datetime.now(timezone.utc),
                date_fmt=date_fmt,
                time_fmt=time_fmt,
                show_time=True,
            ),
            "line_items": [
                {
                    "description": item.description,
                    "energy_kwh": (InvoicePDF._fmt_decimal(item.energy_kwh) if item.energy_kwh else "—"),
                    "tariff_rate": (InvoicePDF._fmt_decimal(item.tariff_rate) if item.tariff_rate else "—"),
                    "amount": InvoicePDF._fmt_decimal(item.amount),
                }
                for item in line_items
            ],
            "meter_data": [
                {
                    "label": meter.label,
                    "period_start_reading": InvoicePDF._fmt_decimal(meter.period_start_reading),
                    "period_end_reading": InvoicePDF._fmt_decimal(meter.period_end_reading),
                    "usage": InvoicePDF._fmt_decimal(meter.period_end_reading - meter.period_start_reading),
                }
                for meter in meter_data
            ],
        }

        html_content = _env.get_template("invoice.html").render(get_template_context(**context))
        return HTML(string=html_content).write_pdf()
