# Jinja2環境・表示フォーマット

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)


DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
)


def to_integer(
    value: Any,
    default: int = 0,
) -> int:
    if value is None:
        return default

    try:
        text = str(value).replace(",", "").strip()

        if not text:
            return default

        return int(
            float(text)
        )

    except (TypeError, ValueError):
        return default


def format_price(
    value: Any,
) -> str:
    if value is None:
        return "価格情報なし"

    try:
        text = str(value).replace(",", "").strip()

        if not text:
            return "価格情報なし"

        return f"{int(float(text)):,}円"

    except (TypeError, ValueError):
        return "価格情報なし"


def format_number(
    value: Any,
) -> str:
    return f"{to_integer(value):,}"


def parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(
        value,
        datetime,
    ):
        return value

    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        pass

    for datetime_format in DATETIME_FORMATS:
        try:
            return datetime.strptime(
                text,
                datetime_format,
            )

        except ValueError:
            continue

    return None


def format_date(
    value: Any,
) -> str:
    """
    日付を「YYYY年M月D日」形式へ変換する。
    """
    if value is None:
        return "-"

    parsed = parse_datetime(
        value
    )

    if parsed is None:
        return (
            str(value).strip()
            or "-"
        )

    return (
        f"{parsed.year}年"
        f"{parsed.month}月"
        f"{parsed.day}日"
    )


def format_datetime(
    value: Any,
) -> str:
    """
    日時を「YYYY年M月D日 HH:MM」形式へ変換する。
    """
    if value is None:
        return "-"

    parsed = parse_datetime(
        value
    )

    if parsed is None:
        return (
            str(value).strip()
            or "-"
        )

    return (
        f"{parsed.year}年"
        f"{parsed.month}月"
        f"{parsed.day}日 "
        f"{parsed.hour:02d}:"
        f"{parsed.minute:02d}"
    )


def create_jinja_environment(
    template_dir: str | Path,
    *,
    site_name: str,
    site_description: str,
    root_prefix: str = "/",
    asset_prefix: str = "/",
) -> Environment:
    environment = Environment(
        loader=FileSystemLoader(
            str(template_dir)
        ),
        autoescape=select_autoescape(
            enabled_extensions=(
                "html",
                "xml",
            ),
            default_for_string=True,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )

    environment.filters.update(
        {
            "price": format_price,
            "number": format_number,
            "date_format": format_date,
            "datetime_format": format_datetime,
        }
    )

    environment.globals.update(
        {
            "site_name": site_name,
            "site_description": site_description,
            "root_prefix": root_prefix,
            "asset_prefix": asset_prefix,
        }
    )

    return environment