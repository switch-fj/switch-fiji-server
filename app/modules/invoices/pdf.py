import base64
import io
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
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
from app.modules.invoices.schema import InvoiceLineItemEnum, InvoiceMeterLabelEnum
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

    @staticmethod
    def _fmt_date(
        dt: datetime,
        date_fmt: str,
        time_fmt: str,
        show_time: bool = False,
        show_year: bool = True,
    ) -> str:
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
            DateFormatEnum.DMY: "%-d %b %Y" if show_year else "%-d %b",
            DateFormatEnum.MDY: "%b %-d %Y" if show_year else "%b %-d",
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
        return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"

    @staticmethod
    def _render_donut_chart_base64(
        labels: list[str],
        values: list[float],
        title: Optional[str] = "",
    ) -> str:
        """Render a donut chart with outside labels and leader lines."""
        colors = ["#00CA47", "#FA4F19", "#024159", "#00AEEF"]
        total = sum(values)
        if total == 0:
            return ""

        fig, ax = plt.subplots(figsize=(7, 4), dpi=300)
        ax.set_aspect("equal")
        ax.axis("off")

        gap_deg = 3
        inner_r = 0.55
        outer_r = 1.0
        label_r = 1.35
        line_r = 1.12

        start_angle = 180.0
        legend_handles = []

        for value, color, label in zip(values, colors[: len(values)], labels):
            sweep = (value / total) * 360 - gap_deg
            end_angle = start_angle + sweep
            mid_angle = (start_angle + end_angle) / 2

            theta = np.linspace(np.radians(start_angle), np.radians(end_angle), 60)
            outer_x = np.append(outer_r * np.cos(theta), inner_r * np.cos(theta[::-1]))
            outer_y = np.append(outer_r * np.sin(theta), inner_r * np.sin(theta[::-1]))
            ax.fill(outer_x, outer_y, color=color)

            mid_rad = np.radians(mid_angle)
            x0 = outer_r * np.cos(mid_rad)
            y0 = outer_r * np.sin(mid_rad)
            x1 = line_r * np.cos(mid_rad)
            y1 = line_r * np.sin(mid_rad)
            ax.plot([x0, x1], [y0, y1], color=color, linewidth=0.8)

            xl = label_r * np.cos(mid_rad)
            yl = label_r * np.sin(mid_rad)
            ha = "left" if xl >= 0 else "right"
            pct = (value / total) * 100
            ax.text(
                xl,
                yl,
                f"{value:.1f} kWh\n({pct:.1f}%)",
                ha=ha,
                va="center",
                fontsize=8,
                fontweight="bold",
                color=color,
            )

            legend_handles.append(mpatches.Patch(color=color, label=label))
            start_angle = end_angle + gap_deg

        ax.set_xlim(-2.0, 2.0)
        ax.set_ylim(-1.6, 1.6)

        ax.legend(
            handles=legend_handles,
            loc="center left",
            bbox_to_anchor=(1.0, 0.5),
            fontsize=8,
            frameon=False,
        )

        if title:
            ax.set_title(title, fontsize=9, fontweight="bold", pad=10)

        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig)
        buf.seek(0)

        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"

    @staticmethod
    def _get_ppa_off_grid_daily_usage(
        invoice_snapshots: list[InvoiceSnapshot],
        line_items: list[InvoiceLineItem],
        date_fmt: str,
        time_fmt: str,
    ):
        data = [
            {
                "date": InvoicePDF._fmt_date(
                    dt=item.period_start_at,
                    date_fmt=date_fmt,
                    time_fmt=time_fmt,
                    show_year=False,
                ),
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

        targets = {
            InvoiceLineItemEnum.OFF_SOLAR_ENERGY_SUPPLIED.value: "night",
            InvoiceLineItemEnum.ON_SOLAR_ENERGY_SUPPLIED.value: "day",
        }

        lines = {
            targets[item.description]: {"total": item.energy_kwh, "amount": item.amount}
            for item in line_items
            if item.description in targets
        }

        night_item = lines.get("night")
        day_item = lines.get("day")

        return {"meter": data, "day_item": day_item, "night_item": night_item}

    @staticmethod
    def _render_bar_chart_base64(daily: dict, title: str = "") -> str:
        dates = list(daily.keys())
        series_keys = ["gen_night", "gen_day", "solar_night", "solar_day"]
        series_labels = ["Gen Night", "Gen Day", "Solar Night", "Solar Day"]
        colors = ["#00CA47", "#FA4F19", "#024159", "#00AEEF"]

        x = np.arange(len(dates))
        bar_width = 0.5

        fig, ax = plt.subplots(figsize=(7.17, 4), dpi=300)

        bottoms = np.zeros(len(dates))

        for key, label, color in zip(series_keys, series_labels, colors):
            values = np.array([daily[date][key] for date in dates])
            bars = ax.bar(
                x,
                values,
                bar_width,
                bottom=bottoms,
                label=label,
                color=color,
            )

            for bar, val in zip(bars, values):
                if val > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{val:.1f}",
                        ha="center",
                        va="center",
                        fontsize=6,
                        color="white",
                        fontweight="bold",
                    )

            bottoms += values

        ax.set_title(title, fontsize=8, fontweight="bold", pad=10)
        ax.set_xticks(x)
        ax.set_xticklabels(dates, rotation=0, ha="center", fontsize=6, color="#1D1D1D")
        ax.set_yticks(ax.get_yticks())
        ax.set_yticklabels([f"{int(y)} kWh" for y in ax.get_yticks()], fontsize=6, color="#1D1D1D")
        ax.legend(
            ncol=4,
            columnspacing=2.0,
            loc="upper center",
            fontsize=6,
            labelcolor="#1D1D1D",
        )
        ax.yaxis.grid(True, linestyle="--", alpha=0.5)
        ax.set_axisbelow(True)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
        plt.close(fig)
        buf.seek(0)

        return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"

    @staticmethod
    def _get_ppa_off_grid_bar_chart_data(
        invoice_snapshots: list[InvoiceSnapshot], date_fmt: str, time_fmt: str
    ) -> dict:
        label_map = {
            InvoiceMeterLabelEnum.GEN_METER_NIGHT.value: "gen_night",
            InvoiceMeterLabelEnum.GEN_METER_DAY.value: "gen_day",
            InvoiceMeterLabelEnum.SITE_METER_NIGHT.value: "solar_night",
            InvoiceMeterLabelEnum.SITE_METER_DAY.value: "solar_day",
        }

        daily = {}

        for snapshot in invoice_snapshots:
            day_label = InvoicePDF._fmt_date(
                snapshot.period_start_at,
                date_fmt=date_fmt,
                time_fmt=time_fmt,
                show_year=False,
            )

            if day_label not in daily:
                daily[day_label] = {
                    "gen_night": 0,
                    "gen_day": 0,
                    "solar_night": 0,
                    "solar_day": 0,
                }

            for meter in snapshot.meter_data:
                series = label_map.get(meter.label)
                if series:
                    daily[day_label][series] += float(meter.usage)

        return daily

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

        pie_chart_data = {
            "day": [
                {"label": "Solar day", "usage": 0},
                {"label": "Gen day", "usage": 0},
            ],
            "night": [
                {"label": "Solar night", "usage": 0},
                {"label": "Gen night", "usage": 0},
            ],
        }

        for datum in meter_data:
            if datum.label == InvoiceMeterLabelEnum.GEN_METER_DAY.value:
                pie_chart_data["day"][1]["usage"] = datum.usage
            elif datum.label == InvoiceMeterLabelEnum.GEN_METER_NIGHT.value:
                pie_chart_data["night"][1]["usage"] = datum.usage
            elif datum.label == InvoiceMeterLabelEnum.SITE_METER_DAY.value:
                pie_chart_data["day"][0]["usage"] = datum.usage
            elif datum.label == InvoiceMeterLabelEnum.SITE_METER_NIGHT.value:
                pie_chart_data["night"][0]["usage"] = datum.usage

        day_chart_labels = [item["label"] for item in pie_chart_data["day"]]
        day_chart_values = [float(item["usage"]) for item in pie_chart_data["day"]]

        night_chart_labels = [item["label"] for item in pie_chart_data["night"]]
        night_chart_values = [float(item["usage"]) for item in pie_chart_data["night"]]

        day_pie_chart_usage = (
            cls._render_donut_chart_base64(
                labels=day_chart_labels,
                values=day_chart_values,
                title="Total Day consumption",
            )
            if any(v > 0 for v in day_chart_values)
            else None
        )

        night_pie_chart_usage = (
            cls._render_donut_chart_base64(
                labels=night_chart_labels,
                values=night_chart_values,
                title="Total Night consumption",
            )
            if any(v > 0 for v in night_chart_values)
            else None
        )

        ppa_off_grid_daily_usage = cls._get_ppa_off_grid_daily_usage(
            invoice_snapshots=invoice_snapshots,
            line_items=line_items,
            date_fmt=date_fmt,
            time_fmt=time_fmt,
        )
        ppa_off_grid_daily_bar_chart_dict = cls._get_ppa_off_grid_bar_chart_data(
            invoice_snapshots=invoice_snapshots,
            date_fmt=date_fmt,
            time_fmt=time_fmt,
        )
        ppa_off_grid_bar_chart = cls._render_bar_chart_base64(
            daily=ppa_off_grid_daily_bar_chart_dict, title="Billing Period usage"
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
            "day_pie_chart_usage": day_pie_chart_usage,
            "night_pie_chart_usage": night_pie_chart_usage,
            "ppa_off_grid_daily_usage": ppa_off_grid_daily_usage,
            "ppa_off_grid_bar_chart": ppa_off_grid_bar_chart,
        }

        html_content = _env.get_template("invoice.html").render(get_template_context(**context))
        return HTML(string=html_content).write_pdf(
            stylesheets=[
                CSS(filename=str(_registry.STATIC_DIR / "css" / "invoice.css")),
            ]
        )
