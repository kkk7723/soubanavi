import os
import sqlite3
import sys
import time

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    TemplateNotFound,
)


# ==================================================
# importパス設定
# ==================================================

# Jupyter・通常のPythonスクリプトの両方に対応
try:
    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )
except NameError:
    base_dir = os.getcwd()


# 現在位置:
# soubanavi/scripts/generate/
#
# プロジェクトルート:
# soubanavi/
project_root = os.path.abspath(
    os.path.join(
        base_dir,
        "..",
        "..",
    )
)


if project_root not in sys.path:
    sys.path.insert(
        0,
        project_root,
    )


# importパス設定後に読み込む
from utils.config import (
    DB_PATH,
    OUTPUT_DIR,
    PROJECT_ROOT,
    SITE_DESCRIPTION,
    SITE_NAME,
    TEMPLATE_DIR,
)

from utils.db_utils import (
    SUMMARY_TABLE_NAME,
    check_table_exists,
    connect_database,
    row_to_dict,
    validate_identifier,
)

from utils.page_utils import (
    create_jinja_environment,
)

from utils.seo import (
    build_seo_data,
)

from utils.static_utils import (
    copy_common_static_files,
    copy_static_files,
)


# ==================================================
# テーブル設定
# ==================================================

PRICE_HISTORY_TABLE_NAME = (
    "price_history"
)


PRODUCT_SUMMARY_TABLE_NAME = (
    SUMMARY_TABLE_NAME
)


# ==================================================
# 出力先設定
# ==================================================

PRICE_DOWN_TODAY_OUTPUT_DIR = (
    Path(OUTPUT_DIR)
    / "price-down-today"
)


# ==================================================
# テンプレート・CSS設定
# ==================================================

PRICE_DOWN_TODAY_INDEX_TEMPLATE_NAME = (
    "price_down_today/"
    "price_down_today_index.html"
)


PRICE_DOWN_TODAY_DETAIL_TEMPLATE_NAME = (
    "price_down_today/"
    "price_down_today_detail.html"
)


PRICE_DOWN_TODAY_CSS_PATHS = (
    "css/price_down_today_index.css",
    "css/price_down_today_detail.css",
)


# ==================================================
# ページ設定
# ==================================================

PRICE_DOWN_TODAY_PAGE_LIMIT = 500


# DBのcategoryに使用される可能性がある値をまとめる。
CATEGORY_VALUES = {
    "pachinko": (
        "pachinko",
        "pachi",
        "p",
        "パチンコ",
    ),
    "slot": (
        "slot",
        "s",
        "パチスロ",
        "スロット",
    ),
}


# 総合・パチンコ・パチスロの3ページを生成する。
PRICE_DOWN_TODAY_PAGE_CONFIGS = (
    {
        "page_type": "all",
        "category_key": None,
        "slug": "",
        "heading": "本日の値下げ実機",
        "page_title": (
            "本日値下げされた"
            "パチンコ・パチスロ中古実機"
        ),
        "category_label": "総合",
        "target_label": (
            "パチンコ・パチスロ中古実機"
        ),
        "canonical_path": (
            "/price-down-today/"
        ),
    },
    {
        "page_type": "pachinko",
        "category_key": "pachinko",
        "slug": "pachinko",
        "heading": (
            "本日値下げされたパチンコ実機"
        ),
        "page_title": (
            "本日値下げされた"
            "パチンコ中古実機"
        ),
        "category_label": "パチンコ",
        "target_label": "パチンコ中古実機",
        "canonical_path": (
            "/price-down-today/pachinko/"
        ),
    },
    {
        "page_type": "slot",
        "category_key": "slot",
        "slug": "slot",
        "heading": (
            "本日値下げされたパチスロ実機"
        ),
        "page_title": (
            "本日値下げされた"
            "パチスロ中古実機"
        ),
        "category_label": "パチスロ",
        "target_label": "パチスロ中古実機",
        "canonical_path": (
            "/price-down-today/slot/"
        ),
    },
)


# ==================================================
# HTML書き込み
# ==================================================

def write_html(
    output_file_path: Path,
    html: str,
) -> None:
    """
    HTMLを指定された場所へ保存する。
    """
    output_file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file_path.write_text(
        html,
        encoding="utf-8",
        newline="",
    )


# ==================================================
# 値の調整
# ==================================================

def normalize_page_limit(
    limit: Any,
) -> int:
    """
    表示件数を正の整数へ変換する。
    """
    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        return PRICE_DOWN_TODAY_PAGE_LIMIT

    if limit_value <= 0:
        return PRICE_DOWN_TODAY_PAGE_LIMIT

    return limit_value


def format_record_date(
    record_date: str | None,
) -> str:
    """
    YYYY-MM-DD形式の日付を
    YYYY年M月D日形式へ変換する。
    """
    if not record_date:
        return ""

    try:
        date_object = datetime.strptime(
            str(record_date),
            "%Y-%m-%d",
        )
    except ValueError:
        return str(
            record_date
        )

    return (
        f"{date_object.year}年"
        f"{date_object.month}月"
        f"{date_object.day}日"
    )


def get_output_file_path(
    page_config: dict[str, Any],
) -> Path:
    """
    ページ設定からHTML出力先を作成する。

    総合:
        output/price-down-today/index.html

    パチンコ:
        output/price-down-today/pachinko/index.html

    パチスロ:
        output/price-down-today/slot/index.html
    """
    slug = str(
        page_config.get("slug")
        or ""
    ).strip()

    if not slug:
        return (
            PRICE_DOWN_TODAY_OUTPUT_DIR
            / "index.html"
        )

    return (
        PRICE_DOWN_TODAY_OUTPUT_DIR
        / slug
        / "index.html"
    )


def get_relative_prefix(
    page_config: dict[str, Any],
) -> str:
    """
    出力階層に応じた相対パスを返す。
    """
    slug = str(
        page_config.get("slug")
        or ""
    ).strip()

    if slug:
        return "../../"

    return "../"


# ==================================================
# インデックス作成
# ==================================================

def create_price_down_today_indexes(
    connection: sqlite3.Connection,
) -> None:
    """
    price_down_todayページ生成で使用する
    インデックスを作成する。

    既に存在する場合は何もしない。
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{history_table_name}_record_date
        ON {history_table_name} (
            record_date
        )
        """
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{history_table_name}_record_machine
        ON {history_table_name} (
            record_date,
            master_machine_id
        )
        """
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{history_table_name}_machine_record
        ON {history_table_name} (
            master_machine_id,
            record_date
        )
        """
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{summary_table_name}_category
        ON {summary_table_name} (
            category
        )
        """
    )

    connection.commit()


# ==================================================
# 価格履歴日取得
# ==================================================

def get_latest_record_date(
    connection: sqlite3.Connection,
) -> str | None:
    """
    price_historyに存在する
    最新のrecord_dateを取得する。
    """
    table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    sql = f"""
        SELECT
            MAX(record_date)
                AS latest_record_date

        FROM {table_name}

        WHERE
            record_date IS NOT NULL

            AND TRIM(record_date) != ''
    """

    row = connection.execute(
        sql
    ).fetchone()

    if row is None:
        return None

    latest_record_date = row[
        "latest_record_date"
    ]

    if latest_record_date is None:
        return None

    return str(
        latest_record_date
    )


def get_previous_record_date(
    connection: sqlite3.Connection,
    latest_record_date: str,
) -> str | None:
    """
    最新record_dateより前に存在する
    最も新しいrecord_dateを取得する。
    """
    table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    sql = f"""
        SELECT
            MAX(record_date)
                AS previous_record_date

        FROM {table_name}

        WHERE
            record_date IS NOT NULL

            AND TRIM(record_date) != ''

            AND record_date < ?
    """

    row = connection.execute(
        sql,
        (
            latest_record_date,
        ),
    ).fetchone()

    if row is None:
        return None

    previous_record_date = row[
        "previous_record_date"
    ]

    if previous_record_date is None:
        return None

    return str(
        previous_record_date
    )


def get_price_history_dates(
    connection: sqlite3.Connection,
) -> tuple[str | None, str | None]:
    """
    最新記録日と直前記録日を取得する。
    """
    latest_record_date = (
        get_latest_record_date(
            connection
        )
    )

    if latest_record_date is None:
        return (
            None,
            None,
        )

    previous_record_date = (
        get_previous_record_date(
            connection=connection,
            latest_record_date=(
                latest_record_date
            ),
        )
    )

    return (
        latest_record_date,
        previous_record_date,
    )


# ==================================================
# SQL条件作成
# ==================================================

def build_price_down_today_where_sql() -> str:
    """
    本日の値下げページ共通の
    対象条件SQLを返す。
    """
    return """
        current_history.master_machine_id
            IS NOT NULL

        AND TRIM(
            CAST(
                current_history.master_machine_id
                AS TEXT
            )
        ) != ''

        AND current_history.min_price
            IS NOT NULL

        AND current_history.min_price > 0

        AND previous_history.min_price
            IS NOT NULL

        AND previous_history.min_price > 0

        AND previous_history.min_price
            > current_history.min_price

        AND COALESCE(
            NULLIF(
                TRIM(
                    current_history.master_machine_name
                ),
                ''
            ),
            NULLIF(
                TRIM(
                    product_summary.master_machine_name
                ),
                ''
            )
        ) IS NOT NULL
    """


def build_category_condition(
    category_key: str | None,
) -> tuple[str, list[Any]]:
    """
    ページ種別に応じたcategory条件と
    SQLパラメータを返す。

    category_keyがNoneの場合は
    総合ページなので絞り込まない。
    """
    if category_key is None:
        return (
            "",
            [],
        )

    category_values = CATEGORY_VALUES.get(
        category_key
    )

    if not category_values:
        raise ValueError(
            "未対応のcategory_keyです: "
            f"{category_key}"
        )

    placeholders = ", ".join(
        "?"
        for _ in category_values
    )

    sql = f"""
        AND LOWER(
            TRIM(
                COALESCE(
                    product_summary.category,
                    ''
                )
            )
        ) IN ({placeholders})
    """

    parameters = [
        str(value).lower()
        for value in category_values
    ]

    return (
        sql,
        parameters,
    )


def build_query_conditions(
    category_key: str | None,
) -> tuple[str, list[Any]]:
    """
    共通条件とカテゴリ条件をまとめる。
    """
    common_where_sql = (
        build_price_down_today_where_sql()
    )

    (
        category_where_sql,
        category_parameters,
    ) = build_category_condition(
        category_key
    )

    return (
        (
            common_where_sql
            + category_where_sql
        ),
        category_parameters,
    )


# ==================================================
# DBデータ取得
# ==================================================

def get_price_down_today_machines(
    connection: sqlite3.Connection,
    latest_record_date: str,
    previous_record_date: str,
    category_key: str | None = None,
    limit: int = PRICE_DOWN_TODAY_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    """
    最新記録日と直前記録日を比較し、
    最安価格が値下げされた機種を取得する。

    並び順:
        1. 値下げ額が大きい順
        2. 値下げ率が大きい順
        3. 現在価格が安い順
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    limit_value = normalize_page_limit(
        limit
    )

    (
        where_sql,
        category_parameters,
    ) = build_query_conditions(
        category_key
    )

    sql = f"""
        SELECT
            current_history.master_machine_id,

            COALESCE(
                NULLIF(
                    TRIM(
                        current_history.master_machine_name
                    ),
                    ''
                ),
                product_summary.master_machine_name
            ) AS master_machine_name,

            COALESCE(
                NULLIF(
                    TRIM(
                        current_history.master_machine_maker
                    ),
                    ''
                ),
                product_summary.master_machine_maker
            ) AS master_machine_maker,

            product_summary.master_machine_model,
            product_summary.master_machine_type,
            product_summary.master_machine_gouki,
            product_summary.master_machine_memo,

            product_summary.master_machine_pworld_url,
            product_summary.master_machine_pworld_image_url,

            product_summary.category,
            product_summary.machine_series,

            current_history.record_date,

            previous_history.record_date
                AS previous_record_date,

            current_history.latest_price,
            current_history.min_price,
            current_history.max_price,
            current_history.avg_price,
            current_history.median_price,

            current_history.price_count,
            current_history.shop_count,

            current_history.lowest_shop_name,
            current_history.lowest_product_url,

            previous_history.latest_price
                AS previous_latest_price,

            previous_history.min_price
                AS previous_min_price,

            previous_history.max_price
                AS previous_max_price,

            previous_history.avg_price
                AS previous_avg_price,

            previous_history.median_price
                AS previous_median_price,

            previous_history.price_count
                AS previous_price_count,

            previous_history.shop_count
                AS previous_shop_count,

            previous_history.lowest_shop_name
                AS previous_lowest_shop_name,

            previous_history.lowest_product_url
                AS previous_lowest_product_url,

            (
                previous_history.min_price
                - current_history.min_price
            ) AS price_down_amount,

            ROUND(
                (
                    (
                        previous_history.min_price
                        - current_history.min_price
                    )
                    * 100.0
                )
                / previous_history.min_price,
                1
            ) AS price_down_rate,

            current_history.created_at
                AS price_history_created_at,

            current_history.updated_at
                AS price_history_updated_at,

            product_summary.first_seen,
            product_summary.last_seen,
            product_summary.latest_scraped_at,

            product_summary.created_at
                AS summary_created_at,

            product_summary.updated_at
                AS summary_updated_at

        FROM {history_table_name}
            AS current_history

        INNER JOIN {history_table_name}
            AS previous_history

            ON CAST(
                previous_history.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

            AND previous_history.record_date = ?

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

        WHERE
            current_history.record_date = ?

            AND {where_sql}

        ORDER BY
            price_down_amount DESC,
            price_down_rate DESC,
            current_history.min_price ASC,
            current_history.price_count DESC,
            current_history.shop_count DESC,

            CASE
                WHEN CAST(
                    current_history.master_machine_id
                    AS TEXT
                ) GLOB '[0-9]*'

                THEN CAST(
                    current_history.master_machine_id
                    AS INTEGER
                )

                ELSE 999999999
            END ASC,

            CAST(
                current_history.master_machine_id
                AS TEXT
            ) ASC

        LIMIT ?
    """

    parameters: list[Any] = [
        previous_record_date,
        latest_record_date,
        *category_parameters,
        limit_value,
    ]

    rows = connection.execute(
        sql,
        tuple(parameters),
    ).fetchall()

    return [
        row_to_dict(
            row
        )
        for row in rows
    ]


def get_price_down_today_machine_count(
    connection: sqlite3.Connection,
    latest_record_date: str,
    previous_record_date: str,
    category_key: str | None = None,
) -> int:
    """
    最安価格が値下げされた
    全機種数を取得する。
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    (
        where_sql,
        category_parameters,
    ) = build_query_conditions(
        category_key
    )

    sql = f"""
        SELECT
            COUNT(*) AS machine_count

        FROM {history_table_name}
            AS current_history

        INNER JOIN {history_table_name}
            AS previous_history

            ON CAST(
                previous_history.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

            AND previous_history.record_date = ?

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

        WHERE
            current_history.record_date = ?

            AND {where_sql}
    """

    parameters: list[Any] = [
        previous_record_date,
        latest_record_date,
        *category_parameters,
    ]

    row = connection.execute(
        sql,
        tuple(parameters),
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["machine_count"]
        or 0
    )


def get_empty_summary() -> dict[str, Any]:
    """
    集計結果がない場合の初期値を返す。
    """
    return {
        "machine_count": 0,
        "total_price_down_amount": 0,
        "average_price_down_amount": 0,
        "maximum_price_down_amount": 0,
        "average_price_down_rate": 0.0,
        "maximum_price_down_rate": 0.0,
        "lowest_current_price": 0,
        "highest_current_price": 0,
    }


def get_price_down_today_summary(
    connection: sqlite3.Connection,
    latest_record_date: str,
    previous_record_date: str,
    category_key: str | None = None,
) -> dict[str, Any]:
    """
    本日の値下げ情報を集計する。
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    (
        where_sql,
        category_parameters,
    ) = build_query_conditions(
        category_key
    )

    sql = f"""
        SELECT
            COUNT(*) AS machine_count,

            COALESCE(
                SUM(
                    previous_history.min_price
                    - current_history.min_price
                ),
                0
            ) AS total_price_down_amount,

            COALESCE(
                AVG(
                    previous_history.min_price
                    - current_history.min_price
                ),
                0
            ) AS average_price_down_amount,

            COALESCE(
                MAX(
                    previous_history.min_price
                    - current_history.min_price
                ),
                0
            ) AS maximum_price_down_amount,

            COALESCE(
                AVG(
                    (
                        (
                            previous_history.min_price
                            - current_history.min_price
                        )
                        * 100.0
                    )
                    / previous_history.min_price
                ),
                0
            ) AS average_price_down_rate,

            COALESCE(
                MAX(
                    (
                        (
                            previous_history.min_price
                            - current_history.min_price
                        )
                        * 100.0
                    )
                    / previous_history.min_price
                ),
                0
            ) AS maximum_price_down_rate,

            COALESCE(
                MIN(
                    current_history.min_price
                ),
                0
            ) AS lowest_current_price,

            COALESCE(
                MAX(
                    current_history.min_price
                ),
                0
            ) AS highest_current_price

        FROM {history_table_name}
            AS current_history

        INNER JOIN {history_table_name}
            AS previous_history

            ON CAST(
                previous_history.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

            AND previous_history.record_date = ?

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

        WHERE
            current_history.record_date = ?

            AND {where_sql}
    """

    parameters: list[Any] = [
        previous_record_date,
        latest_record_date,
        *category_parameters,
    ]

    row = connection.execute(
        sql,
        tuple(parameters),
    ).fetchone()

    if row is None:
        return get_empty_summary()

    summary = row_to_dict(
        row
    )

    return {
        "machine_count": int(
            summary.get("machine_count")
            or 0
        ),

        "total_price_down_amount": int(
            summary.get(
                "total_price_down_amount"
            )
            or 0
        ),

        "average_price_down_amount": int(
            round(
                float(
                    summary.get(
                        "average_price_down_amount"
                    )
                    or 0
                )
            )
        ),

        "maximum_price_down_amount": int(
            summary.get(
                "maximum_price_down_amount"
            )
            or 0
        ),

        "average_price_down_rate": round(
            float(
                summary.get(
                    "average_price_down_rate"
                )
                or 0
            ),
            1,
        ),

        "maximum_price_down_rate": round(
            float(
                summary.get(
                    "maximum_price_down_rate"
                )
                or 0
            ),
            1,
        ),

        "lowest_current_price": int(
            summary.get(
                "lowest_current_price"
            )
            or 0
        ),

        "highest_current_price": int(
            summary.get(
                "highest_current_price"
            )
            or 0
        ),
    }


def get_price_down_today_updated_at(
    connection: sqlite3.Connection,
    latest_record_date: str,
    previous_record_date: str,
    category_key: str | None = None,
) -> Any:
    """
    値下げ対象データの
    最終更新日時を取得する。
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    (
        where_sql,
        category_parameters,
    ) = build_query_conditions(
        category_key
    )

    sql = f"""
        SELECT
            COALESCE(
                MAX(
                    current_history.updated_at
                ),
                MAX(
                    product_summary.latest_scraped_at
                ),
                MAX(
                    product_summary.updated_at
                )
            ) AS price_down_today_updated_at

        FROM {history_table_name}
            AS current_history

        INNER JOIN {history_table_name}
            AS previous_history

            ON CAST(
                previous_history.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

            AND previous_history.record_date = ?

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = CAST(
                current_history.master_machine_id
                AS TEXT
            )

        WHERE
            current_history.record_date = ?

            AND {where_sql}
    """

    parameters: list[Any] = [
        previous_record_date,
        latest_record_date,
        *category_parameters,
    ]

    row = connection.execute(
        sql,
        tuple(parameters),
    ).fetchone()

    if row is None:
        return None

    return row[
        "price_down_today_updated_at"
    ]


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_price_down_today_meta_description(
    latest_record_date: str,
    machine_count: int,
    summary: dict[str, Any],
    target_label: str,
) -> str:
    """
    本日の値下げページ用の
    meta descriptionを作成する。
    """
    display_date = format_record_date(
        latest_record_date
    )

    if machine_count <= 0:
        return (
            f"{display_date}の価格記録で"
            "最安価格が値下げされた"
            f"{target_label}を掲載する"
            "価格情報ページです。"
        )

    maximum_price_down_amount = int(
        summary.get(
            "maximum_price_down_amount"
        )
        or 0
    )

    average_price_down_rate = float(
        summary.get(
            "average_price_down_rate"
        )
        or 0
    )

    return (
        f"{display_date}の価格記録で"
        "最安価格が値下げされた"
        f"{target_label}を"
        f"{machine_count:,}機種掲載しています。"
        "最大値下げ額は"
        f"{maximum_price_down_amount:,}円、"
        "平均値下げ率は"
        f"{average_price_down_rate:.1f}%です。"
        "値下げ前価格、現在価格、出品件数、"
        "販売店情報を比較できます。"
    )


# ==================================================
# ページ説明文作成
# ==================================================

def build_price_down_today_description(
    latest_record_date: str,
    previous_record_date: str,
    machine_count: int,
    target_label: str,
) -> str:
    """
    ページ内に表示する説明文を作成する。
    """
    latest_date_display = format_record_date(
        latest_record_date
    )

    previous_date_display = format_record_date(
        previous_record_date
    )

    if machine_count <= 0:
        return (
            f"{previous_date_display}と"
            f"{latest_date_display}の価格を"
            "比較した結果、最安価格の値下げが"
            f"確認された{target_label}はありません。"
        )

    return (
        f"{previous_date_display}と"
        f"{latest_date_display}の価格を比較し、"
        "最安価格が値下げされた"
        f"{target_label}を"
        f"{machine_count:,}機種掲載しています。"
        "値下げ額が大きい順に表示しています。"
    )


# ==================================================
# パンくずリスト作成
# ==================================================

def create_price_down_today_breadcrumbs(
    page_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    ページ階層に応じたパンくずリストを作成する。
    """
    slug = str(
        page_config.get("slug")
        or ""
    ).strip()

    heading = str(
        page_config.get("heading")
        or ""
    ).strip()

    category_label = str(
        page_config.get("category_label")
        or ""
    ).strip()

    if not slug:
        return [
            {
                "title": "トップ",
                "url": "../",
            },
            {
                "title": heading,
                "url": None,
            },
        ]

    return [
        {
            "title": "トップ",
            "url": "../../",
        },
        {
            "title": "本日の値下げ実機",
            "url": "../",
        },
        {
            "title": category_label,
            "url": None,
        },
    ]


# ==================================================
# カテゴリナビゲーション作成
# ==================================================

def build_category_navigation(
    current_page_type: str,
) -> list[dict[str, Any]]:
    """
    テンプレートで使用する
    総合・パチンコ・パチスロの切替リンクを作成する。
    """
    is_child_page = (
        current_page_type != "all"
    )

    return [
        {
            "key": "all",
            "label": "総合",
            "url": (
                "../"
                if is_child_page
                else "./"
            ),
            "is_current": (
                current_page_type == "all"
            ),
        },
        {
            "key": "pachinko",
            "label": "パチンコ",
            "url": (
                "../pachinko/"
                if is_child_page
                else "pachinko/"
            ),
            "is_current": (
                current_page_type == "pachinko"
            ),
        },
        {
            "key": "slot",
            "label": "パチスロ",
            "url": (
                "../slot/"
                if is_child_page
                else "slot/"
            ),
            "is_current": (
                current_page_type == "slot"
            ),
        },
    ]


# ==================================================
# 本日の値下げページ生成
# ==================================================

def generate_price_down_today_page(
    environment: Environment,
    connection: sqlite3.Connection,
    generated_at: datetime,
    latest_record_date: str,
    previous_record_date: str,
    page_config: dict[str, Any],
) -> dict[str, Any]:
    """
    指定されたページ設定に基づいて
    総合・パチンコ・パチスロのいずれかを生成する。
    """
    page_type = str(
        page_config["page_type"]
    )

    category_key = page_config.get(
        "category_key"
    )

    heading = str(
        page_config["heading"]
    )

    page_title = str(
        page_config["page_title"]
    )

    target_label = str(
        page_config["target_label"]
    )

    canonical_path = str(
        page_config["canonical_path"]
    )

    output_file_path = get_output_file_path(
        page_config
    )

    relative_prefix = get_relative_prefix(
        page_config
    )

    print(
        "[確認] 値下げ機種を取得します: "
        f"{page_type}",
        flush=True,
    )

    template = environment.get_template(
        PRICE_DOWN_TODAY_INDEX_TEMPLATE_NAME
    )

    machines = get_price_down_today_machines(
        connection=connection,
        latest_record_date=latest_record_date,
        previous_record_date=previous_record_date,
        category_key=category_key,
        limit=PRICE_DOWN_TODAY_PAGE_LIMIT,
    )

    total_machine_count = (
        get_price_down_today_machine_count(
            connection=connection,
            latest_record_date=latest_record_date,
            previous_record_date=previous_record_date,
            category_key=category_key,
        )
    )

    price_down_summary = (
        get_price_down_today_summary(
            connection=connection,
            latest_record_date=latest_record_date,
            previous_record_date=previous_record_date,
            category_key=category_key,
        )
    )

    price_down_updated_at = (
        get_price_down_today_updated_at(
            connection=connection,
            latest_record_date=latest_record_date,
            previous_record_date=previous_record_date,
            category_key=category_key,
        )
    )

    meta_description = (
        build_price_down_today_meta_description(
            latest_record_date=(
                latest_record_date
            ),
            machine_count=(
                total_machine_count
            ),
            summary=price_down_summary,
            target_label=target_label,
        )
    )

    page_description = (
        build_price_down_today_description(
            latest_record_date=(
                latest_record_date
            ),
            previous_record_date=(
                previous_record_date
            ),
            machine_count=(
                total_machine_count
            ),
            target_label=target_label,
        )
    )

    robots = (
        "index,follow"
        if total_machine_count > 0
        else "noindex,follow"
    )

    seo = build_seo_data(
        title=page_title,
        description=meta_description,
        canonical_path=canonical_path,
        robots=robots,
        og_type="website",
    )

    category_navigation = (
        build_category_navigation(
            current_page_type=page_type
        )
    )

    context = {
        **seo,

        # ==================================================
        # サイト共通
        # ==================================================

        "site_name": SITE_NAME,
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # ==================================================
        # テンプレート・CSS情報
        # ==================================================

        "detail_template_name": (
            PRICE_DOWN_TODAY_DETAIL_TEMPLATE_NAME
        ),

        # ==================================================
        # ページ情報
        # ==================================================

        "page_type": page_type,

        "category_key": category_key,

        "category_label": (
            page_config["category_label"]
        ),

        "page_title": page_title,

        "page_description": page_description,

        "price_down_today_title": heading,

        "price_down_today_description": (
            page_description
        ),

        "breadcrumbs": (
            create_price_down_today_breadcrumbs(
                page_config
            )
        ),

        "category_navigation": (
            category_navigation
        ),

        # 別名でも参照できるようにする。
        "category_tabs": (
            category_navigation
        ),

        # ==================================================
        # 記録日
        # ==================================================

        "latest_record_date": (
            latest_record_date
        ),

        "latest_record_date_display": (
            format_record_date(
                latest_record_date
            )
        ),

        "previous_record_date": (
            previous_record_date
        ),

        "previous_record_date_display": (
            format_record_date(
                previous_record_date
            )
        ),

        # ==================================================
        # 機種一覧
        # ==================================================

        "machines": machines,

        # テンプレートへ実際に渡した表示件数
        "machine_count": len(
            machines
        ),

        # LIMIT適用前の対象件数
        "total_machine_count": (
            total_machine_count
        ),

        "page_limit": (
            PRICE_DOWN_TODAY_PAGE_LIMIT
        ),

        # ==================================================
        # 集計情報
        # ==================================================

        "price_down_summary": (
            price_down_summary
        ),

        "total_price_down_amount": (
            price_down_summary[
                "total_price_down_amount"
            ]
        ),

        "average_price_down_amount": (
            price_down_summary[
                "average_price_down_amount"
            ]
        ),

        "maximum_price_down_amount": (
            price_down_summary[
                "maximum_price_down_amount"
            ]
        ),

        "average_price_down_rate": (
            price_down_summary[
                "average_price_down_rate"
            ]
        ),

        "maximum_price_down_rate": (
            price_down_summary[
                "maximum_price_down_rate"
            ]
        ),

        "lowest_current_price": (
            price_down_summary[
                "lowest_current_price"
            ]
        ),

        "highest_current_price": (
            price_down_summary[
                "highest_current_price"
            ]
        ),

        # ==================================================
        # 更新日時
        # ==================================================

        "generated_at": generated_at,

        "updated_at": (
            price_down_updated_at
            or generated_at
        ),

        # ==================================================
        # 相対パス
        # ==================================================

        "root_prefix": relative_prefix,
        "asset_prefix": relative_prefix,
    }

    html = template.render(
        **context
    )

    write_html(
        output_file_path=output_file_path,
        html=html,
    )

    relative_output_path = (
        output_file_path.relative_to(
            Path(OUTPUT_DIR)
        )
    )

    print(
        "[生成] "
        f"{relative_output_path.as_posix()}"
        f" - 表示{len(machines):,}機種"
        f" / 対象{total_machine_count:,}機種"
    )

    print(
        "  比較元日: "
        f"{previous_record_date}"
    )

    print(
        "  最新記録日: "
        f"{latest_record_date}"
    )

    print(
        "  title: "
        f"{context['page_title']}"
    )

    print(
        "  canonical: "
        f"{context['canonical_url']}"
    )

    print(
        "  robots: "
        f"{robots}"
    )

    return {
        "page_type": page_type,
        "output_file_path": (
            output_file_path
        ),
        "display_machine_count": len(
            machines
        ),
        "total_machine_count": (
            total_machine_count
        ),
        "robots": robots,
    }


# ==================================================
# 全ページ生成
# ==================================================

def generate_price_down_today() -> None:
    """
    本日の値下げページを生成する。

    生成対象:
        /price-down-today/
        /price-down-today/pachinko/
        /price-down-today/slot/
    """
    start_time = time.perf_counter()

    generated_at = datetime.now()

    PRICE_DOWN_TODAY_OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy_common_static_files(
        PROJECT_ROOT,
        OUTPUT_DIR,
    )

    copy_static_files(
        PROJECT_ROOT,
        OUTPUT_DIR,
        relative_paths=(
            PRICE_DOWN_TODAY_CSS_PATHS
        ),
    )

    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
    )

    with connect_database(
        DB_PATH
    ) as connection:
        check_table_exists(
            connection,
            PRICE_HISTORY_TABLE_NAME,
        )

        check_table_exists(
            connection,
            PRODUCT_SUMMARY_TABLE_NAME,
        )

        print(
            "[確認] インデックスを確認します。",
            flush=True,
        )

        create_price_down_today_indexes(
            connection
        )

        print(
            "[確認] 価格履歴日を取得します。",
            flush=True,
        )

        (
            latest_record_date,
            previous_record_date,
        ) = get_price_history_dates(
            connection
        )

        if latest_record_date is None:
            raise ValueError(
                "price_historyに価格履歴がありません。"
            )

        if previous_record_date is None:
            raise ValueError(
                "値下げ比較に必要な直前日の"
                "価格履歴がありません。"
            )

        print(
            "  最新記録日: "
            f"{latest_record_date}",
            flush=True,
        )

        print(
            "  直前記録日: "
            f"{previous_record_date}",
            flush=True,
        )

        generation_results: list[
            dict[str, Any]
        ] = []

        for page_config in (
            PRICE_DOWN_TODAY_PAGE_CONFIGS
        ):
            result = (
                generate_price_down_today_page(
                    environment=environment,
                    connection=connection,
                    generated_at=generated_at,
                    latest_record_date=(
                        latest_record_date
                    ),
                    previous_record_date=(
                        previous_record_date
                    ),
                    page_config=page_config,
                )
            )

            generation_results.append(
                result
            )

    elapsed_time = (
        time.perf_counter()
        - start_time
    )

    print("=" * 70)

    print(
        "本日の値下げページを生成しました。"
    )

    for result in generation_results:
        output_file_path = Path(
            result["output_file_path"]
        )

        relative_output_path = (
            output_file_path.relative_to(
                Path(OUTPUT_DIR)
            )
        )

        print(
            f"{result['page_type']}: "
            f"{relative_output_path.as_posix()}"
            " / "
            f"表示{result['display_machine_count']:,}件"
            " / "
            f"対象{result['total_machine_count']:,}件"
        )

    print(
        "最新記録日: "
        f"{latest_record_date}"
    )

    print(
        "比較元記録日: "
        f"{previous_record_date}"
    )

    print(
        "1ページの表示上限: "
        f"{PRICE_DOWN_TODAY_PAGE_LIMIT:,}件"
    )

    print(
        f"処理時間: {elapsed_time:.2f}秒"
    )

    print("=" * 70)


# ==================================================
# 実行
# ==================================================

if __name__ == "__main__":
    try:
        generate_price_down_today()

    except sqlite3.Error as error:
        print("-" * 70)

        print(
            "SQLite処理で"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    except TemplateNotFound as error:
        print("-" * 70)

        print(
            "Jinja2テンプレートが"
            "見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            "一覧テンプレート名: "
            f"{PRICE_DOWN_TODAY_INDEX_TEMPLATE_NAME}"
        )

        print(
            "詳細テンプレート名: "
            f"{PRICE_DOWN_TODAY_DETAIL_TEMPLATE_NAME}"
        )

        raise

    except FileNotFoundError as error:
        print("-" * 70)

        print(
            "本日の値下げページ用の"
            "静的ファイルが見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        for css_path in (
            PRICE_DOWN_TODAY_CSS_PATHS
        ):
            print(
                "確認するCSS: "
                f"{Path(PROJECT_ROOT) / 'static' / css_path}"
            )

        raise

    except (KeyError, TypeError, ValueError) as error:
        print("-" * 70)

        print(
            "本日の値下げページ設定に"
            "エラーがあります。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    except Exception as error:
        print("-" * 70)

        print(
            "本日の値下げページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise