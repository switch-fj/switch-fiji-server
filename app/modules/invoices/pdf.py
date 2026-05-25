import base64
import io
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
from weasyprint import CSS

from app.core.logger import setup_logger
from app.core.template_registry import TemplateRegistry
from app.modules.contracts.model import Contract
from app.modules.invoices.model import (
    Invoice,
    InvoiceLineItem,
    InvoiceMeterData,
    InvoiceSnapshot,
)
from app.modules.invoices.schema import InvoiceMeterLabelEnum
from app.modules.settings.model import ContractSettings
from app.shared.schema import DateFormatEnum, TimeFormatEnum
from app.templates.libs.context import get_template_context

logger = setup_logger(__name__)

matplotlib.use("Agg")
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

    def _fmt_date(self, dt: datetime, date_fmt: str, time_fmt: str, show_time: bool = False) -> str:
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

    def _fmt_decimal(self, value) -> str:
        """Format a numeric value as a trimmed decimal string (trailing zeros removed).

        Args:
            value: A numeric value (int, float, or Decimal) to format.

        Returns:
            A string with up to four decimal places and trailing zeros stripped.
        """
        return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"

    def _render_pie_chart_base64(
        self,
        labels: list[str],
        values: list[float],
        title: Optional[str] = "",
    ) -> str:
        """Render a pie chart and return it as a base64 PNG data URI."""
        fig, ax = plt.subplots(figsize=(3.5, 3), dpi=300)
        ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=180,
        )
        if title:
            ax.set_title(title)
        ax.axis("equal")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()

        pie_chart = f"data:image/png;base64,{b64}"
        return pie_chart

    def _get_ppa_off_grid_daily_usage(
        self,
        invoice_snapshots: list[InvoiceSnapshot],
        date_fmt: str,
        time_fmt: str,
    ):
        data = [
            {
                "date": self._fmt_date(dt=item.period_start_at, date_fmt=date_fmt, time_fmt=time_fmt),
                "day": f"Day {idx + 1}",
                "meter_data": {
                    k: v
                    for meter in item.meter_data
                    if meter.label
                    in (
                        InvoiceMeterLabelEnum.SITE_METER_DAY.value,
                        InvoiceMeterLabelEnum.SITE_METER_NIGHT.value,
                    )
                    for k, v in (
                        {"day_usage": meter.usage}
                        if meter.label == InvoiceMeterLabelEnum.SITE_METER_DAY.value
                        else {"night_usage": meter.usage}
                    ).items()
                },
            }
            for idx, item in enumerate(invoice_snapshots)
        ]

        return data

    @classmethod
    def render_invoice_pdf(
        cls,
        invoice: Invoice,
        contract: Contract,
        line_items: list[InvoiceLineItem],
        meter_data: list[InvoiceMeterData],
        invoice_snapshots: list[InvoiceSnapshot],
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
        vat_amount = invoice.vat_amount
        total = invoice.total
        date_fmt = contract_settings.date_format
        time_fmt = contract_settings.time_format
        contract_timezone = contract.timezone
        tz = ZoneInfo(contract_timezone)
        currency = contract.currency
        ppa_off_grid_daily_usage = None

        chart_labels = [datum.label for datum in meter_data if datum.usage]
        chart_values = [float(datum.usage) for datum in meter_data if datum.usage]

        usage_pie_chart = (
            InvoicePDF._render_pie_chart_base64(
                labels=chart_labels,
                values=chart_values,
            )
            if chart_values
            else None
        )

        ppa_off_grid_daily_usage = cls._get_ppa_off_grid_daily_usage(
            invoice_snapshots=invoice_snapshots, date_fmt=date_fmt, time_fmt=time_fmt
        )

        context = {
            "base64_logo": fetch_logo_base64(),
            "invoice_ref": invoice.invoice_ref,
            "currency": currency,
            "period_start_at": cls._fmt_date(
                dt=invoice.period_start_at.astimezone(tz=tz),
                date_fmt=date_fmt,
                time_fmt=time_fmt,
            ),
            "period_end_at": cls._fmt_date(
                dt=invoice.period_end_at.astimezone(tz=tz),
                date_fmt=date_fmt,
                time_fmt=time_fmt,
            ),
            "client_name": contract.client.client_name if contract.client else "—",
            "site_name": (contract.site.site_name or contract.site.gateway_id if contract.site else "—"),
            "subtotal": cls._fmt_decimal(subtotal),
            "vat_amount": cls._fmt_decimal(vat_amount),
            "total": cls._fmt_decimal(total),
            "generated_at": cls._fmt_date(
                dt=datetime.now(tz=tz),
                date_fmt=date_fmt,
                time_fmt=time_fmt,
                show_time=True,
            ),
            "line_items": [
                {
                    "description": item.description,
                    "energy_kwh": (cls._fmt_decimal(item.energy_kwh) if item.energy_kwh else "—"),
                    "tariff_rate": (cls._fmt_decimal(item.tariff_rate) if item.tariff_rate else "—"),
                    "amount": cls._fmt_decimal(item.amount),
                }
                for item in line_items
            ],
            "meter_data": [
                {
                    "label": meter.label,
                    "period_start_reading": cls._fmt_decimal(meter.period_start_reading),
                    "period_end_reading": cls._fmt_decimal(meter.period_end_reading),
                    "usage": cls._fmt_decimal(meter.period_end_reading - meter.period_start_reading),
                }
                for meter in meter_data
            ],
            "usage_pie_chart": usage_pie_chart,
            "ppa_off_grid_daily_usage": ppa_off_grid_daily_usage,
        }

        html_content = _env.get_template("invoice.html").render(get_template_context(**context))
        return HTML(string=html_content).write_pdf(
            stylesheets=[
                CSS(filename=str(_registry.STATIC_DIR / "css" / "invoice.css")),
            ]
        )
