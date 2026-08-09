#!/usr/bin/env python
# coding: utf-8

# In[22]:


import os
import re
import sqlite3
import sys
import time
import calendar

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import TemplateNotFound


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
    ASSET_PREFIX,
    DB_PATH,
    OUTPUT_DIR,
    PROJECT_ROOT,
    ROOT_PREFIX,
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
# ページ設定
# ==================================================

TEMPLATE_FILE_NAME = "index.html"

OUTPUT_FILE_PATH = (
    Path(OUTPUT_DIR)
    / "index.html"
)


# ==================================================
# テーブル設定
# ==================================================

MACHINE_MASTER_TABLE_NAME = "machine_master"
PRICE_HISTORY_TABLE_NAME = "price_history"


# ==================================================
# トップページ表示件数
# ==================================================

TODAY_PRICE_DROP_MACHINE_LIMIT = 10
LOWEST_PRICE_MACHINE_LIMIT = 10
HIGHEST_AVG_PRICE_MACHINE_LIMIT = 10
RECENT_MACHINE_LIMIT = 10
RECENT_MONTHS = 10

# ==================================================
# 共通処理
# ==================================================

def normalize_limit(
    limit: int,
    default_value: int,
) -> int:
    """
    LIMITへ渡す値を安全な正の整数へ変換する。

    Parameters
    ----------
    limit : int
        指定された取得件数。

    default_value : int
        不正な値だった場合に使用する件数。

    Returns
    -------
    int
        1以上の取得件数。
    """
    try:
        limit_value = int(
            limit
        )

    except (TypeError, ValueError):
        return default_value


    if limit_value <= 0:
        return default_value


    return limit_value


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
    safe_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )


    sql = f"""
        SELECT
            MAX(record_date)
                AS latest_record_date

        FROM {safe_table_name}

        WHERE record_date IS NOT NULL
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
    最新記録日より前に存在する
    最も新しいrecord_dateを取得する。
    """
    safe_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )


    sql = f"""
        SELECT
            MAX(record_date)
                AS previous_record_date

        FROM {safe_table_name}

        WHERE record_date IS NOT NULL
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
# 本日の値下げ機種取得
# ==================================================

def get_today_price_drop_machines(
    connection: sqlite3.Connection,
    latest_record_date: str,
    previous_record_date: str,
    limit: int = TODAY_PRICE_DROP_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    """
    最新記録日と直前記録日を比較し、
    最安価格が値下げされた機種を取得する。

    判定対象:
        min_price

    並び順:
        1. 値下げ額が大きい順
        2. 値下げ率が大きい順
        3. 現在価格が安い順
    """
    history_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    limit_value = normalize_limit(
        limit,
        TODAY_PRICE_DROP_MACHINE_LIMIT,
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

            product_summary.master_machine_pworld_image_url,

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
            ) AS price_down_rate

        FROM {history_table_name}
            AS current_history

        INNER JOIN {history_table_name}
            AS previous_history

            ON previous_history.master_machine_id
                = current_history.master_machine_id

            AND previous_history.record_date = ?

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = current_history.master_machine_id

        WHERE current_history.record_date = ?

          AND current_history.master_machine_id
                IS NOT NULL

          AND TRIM(
                current_history.master_machine_id
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

        ORDER BY
            price_down_amount DESC,
            price_down_rate DESC,
            current_history.min_price ASC,

            COALESCE(
                current_history.price_count,
                0
            ) DESC,

            COALESCE(
                current_history.shop_count,
                0
            ) DESC,

            CASE
                WHEN current_history.master_machine_id
                    GLOB '[0-9]*'

                THEN CAST(
                    current_history.master_machine_id
                    AS INTEGER
                )

                ELSE 999999999
            END ASC,

            current_history.master_machine_id ASC

        LIMIT ?
    """


    rows = connection.execute(
        sql,
        (
            previous_record_date,
            latest_record_date,
            limit_value,
        ),
    ).fetchall()


    return [
        row_to_dict(
            row
        )
        for row in rows
    ]


# ==================================================
# 最安価格ランキング取得
# ==================================================

def get_cheapest_machines(
    connection: sqlite3.Connection,
    limit: int = LOWEST_PRICE_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    """
    最安価格が安い順に機種を取得する。

    min_priceがNULLまたは0以下の機種は除外する。
    """
    safe_table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    limit_value = normalize_limit(
        limit,
        LOWEST_PRICE_MACHINE_LIMIT,
    )


    sql = f"""
        SELECT
            master_machine_id,
            master_machine_name,
            master_machine_maker,
            master_machine_pworld_image_url,

            latest_price,
            min_price,
            max_price,
            avg_price,
            median_price,

            price_count,
            shop_count,

            lowest_shop_name,
            lowest_product_url,

            latest_scraped_at,
            updated_at

        FROM {safe_table_name}

        WHERE master_machine_id IS NOT NULL

          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''

          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''

          AND min_price IS NOT NULL
          AND min_price > 0

        ORDER BY
            min_price ASC,

            COALESCE(
                price_count,
                0
            ) DESC,

            COALESCE(
                shop_count,
                0
            ) DESC,

            master_machine_id ASC

        LIMIT ?
    """


    rows = connection.execute(
        sql,
        (
            limit_value,
        ),
    ).fetchall()


    return [
        row_to_dict(
            row
        )
        for row in rows
    ]


# ==================================================
# 平均価格上位取得
# ==================================================

def get_highest_average_price_machines(
    connection: sqlite3.Connection,
    limit: int = HIGHEST_AVG_PRICE_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    """
    平均価格が高い順に機種を取得する。

    avg_priceがNULLまたは0以下の機種は除外する。
    """
    safe_table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    limit_value = normalize_limit(
        limit,
        HIGHEST_AVG_PRICE_MACHINE_LIMIT,
    )


    sql = f"""
        SELECT
            master_machine_id,
            master_machine_name,
            master_machine_maker,
            master_machine_pworld_image_url,

            latest_price,
            min_price,
            max_price,
            avg_price,
            median_price,

            price_count,
            shop_count,

            lowest_shop_name,
            lowest_product_url,

            latest_scraped_at,
            updated_at

        FROM {safe_table_name}

        WHERE master_machine_id IS NOT NULL

          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''

          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''

          AND avg_price IS NOT NULL
          AND avg_price > 0

        ORDER BY
            avg_price DESC,

            COALESCE(
                price_count,
                0
            ) DESC,

            COALESCE(
                shop_count,
                0
            ) DESC,

            master_machine_id ASC

        LIMIT ?
    """


    rows = connection.execute(
        sql,
        (
            limit_value,
        ),
    ).fetchall()


    return [
        row_to_dict(
            row
        )
        for row in rows
    ]



# ==================================================
# 最近導入された機種用共通処理
# ==================================================

def clean_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_integer(
    value: Any,
    default: int = 0,
) -> int:
    if value is None:
        return default

    try:
        text = str(
            value
        ).replace(
            ",",
            "",
        ).strip()

        if not text:
            return default

        return int(
            float(
                text
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def normalize_machine_id(
    value: Any,
) -> str:
    machine_id = clean_text(
        value
    )

    if not machine_id:
        return ""

    return re.sub(
        r'[\\/:*?"<>|]',
        "_",
        machine_id,
    )


def subtract_months(
    value: datetime,
    months: int,
) -> datetime:
    total_months = (
        value.year * 12
        + value.month
        - 1
        - months
    )

    target_year = (
        total_months
        // 12
    )

    target_month = (
        total_months
        % 12
        + 1
    )

    last_day = calendar.monthrange(
        target_year,
        target_month,
    )[1]

    target_day = min(
        value.day,
        last_day,
    )

    return value.replace(
        year=target_year,
        month=target_month,
        day=target_day,
    )


def parse_introduced_date(
    value: Any,
) -> datetime | None:
    text = clean_text(
        value
    )

    if not text:
        return None

    text = re.sub(
        r"[（(]\s*[月火水木金土日]\s*[）)]",
        "",
        text,
    ).strip()

    date_patterns = (
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}年\d{1,2}月",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{4}/\d{1,2}",
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{4}-\d{1,2}",
    )

    for pattern in date_patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            text = match.group(
                0
            )
            break

    date_formats = (
        "%Y年%m月%d日",
        "%Y年%m月",
        "%Y/%m/%d",
        "%Y/%m",
        "%Y-%m-%d",
        "%Y-%m",
    )

    for date_format in date_formats:
        try:
            return datetime.strptime(
                text,
                date_format,
            )

        except ValueError:
            continue

    return None


def format_introduced_date(
    introduced_date: datetime,
    original_value: Any,
) -> str:
    original_text = clean_text(
        original_value
    )

    has_day = bool(
        re.search(
            (
                r"\d{4}年\d{1,2}月\d{1,2}日"
                r"|"
                r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
            ),
            original_text,
        )
    )

    if has_day:
        return introduced_date.strftime(
            "%Y年%m月%d日"
        )

    return introduced_date.strftime(
        "%Y年%m月"
    )


def get_all_machine_rows(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    master_table_name = validate_identifier(
        MACHINE_MASTER_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    sql = f"""
        SELECT
            machine_master.master_machine_id,
            machine_master.master_machine_category,
            machine_master.master_machine_name,
            machine_master.master_machine_maker,
            machine_master.master_machine_model,
            machine_master.master_machine_type,
            machine_master.master_machine_gouki,
            machine_master.master_machine_introduced_date,
            machine_master.master_machine_pworld_image_url,

            product_summary.latest_price,
            product_summary.min_price,
            product_summary.max_price,
            product_summary.avg_price,
            product_summary.median_price,

            COALESCE(
                product_summary.price_count,
                0
            ) AS price_count,

            COALESCE(
                product_summary.shop_count,
                0
            ) AS shop_count,

            product_summary.lowest_shop_name,
            product_summary.lowest_product_url,
            product_summary.latest_scraped_at,
            product_summary.updated_at

        FROM {master_table_name}
            AS machine_master

        LEFT JOIN {summary_table_name}
            AS product_summary

            ON CAST(
                product_summary.master_machine_id
                AS TEXT
            ) = CAST(
                machine_master.master_machine_id
                AS TEXT
            )

        WHERE
            machine_master.master_machine_id
                IS NOT NULL

            AND TRIM(
                CAST(
                    machine_master.master_machine_id
                    AS TEXT
                )
            ) != ''

            AND machine_master.master_machine_name
                IS NOT NULL

            AND TRIM(
                machine_master.master_machine_name
            ) != ''

            AND machine_master.master_machine_introduced_date
                IS NOT NULL

            AND TRIM(
                machine_master.master_machine_introduced_date
            ) != ''
    """

    rows = connection.execute(
        sql
    ).fetchall()

    return [
        row_to_dict(
            row
        )
        for row in rows
    ]


def get_recent_machines(
    connection: sqlite3.Connection,
    generated_at: datetime,
    recent_months: int = RECENT_MONTHS,
    limit: int = RECENT_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    limit_value = normalize_limit(
        limit,
        RECENT_MACHINE_LIMIT,
    )

    all_machines = get_all_machine_rows(
        connection
    )

    today = generated_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    period_start = subtract_months(
        today,
        recent_months,
    )

    recent_machines: list[
        dict[str, Any]
    ] = []

    for machine in all_machines:
        original_introduced_date = machine.get(
            "master_machine_introduced_date"
        )

        introduced_date = parse_introduced_date(
            original_introduced_date
        )

        if introduced_date is None:
            continue

        introduced_date = introduced_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        if introduced_date > today:
            continue

        if introduced_date < period_start:
            continue

        machine_file_id = normalize_machine_id(
            machine.get(
                "master_machine_id"
            )
        )

        if not machine_file_id:
            continue

        price_count = normalize_integer(
            machine.get(
                "price_count"
            )
        )

        shop_count = normalize_integer(
            machine.get(
                "shop_count"
            )
        )

        machine_data = dict(
            machine
        )

        machine_data.update(
            {
                "machine_file_id": machine_file_id,
                "detail_url": (
                    "machines/"
                    f"{machine_file_id}.html"
                ),
                "introduced_date_value": introduced_date,
                "introduced_date_iso": (
                    introduced_date.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "introduced_date_display": (
                    format_introduced_date(
                        introduced_date=(
                            introduced_date
                        ),
                        original_value=(
                            original_introduced_date
                        ),
                    )
                ),
                "price_count": price_count,
                "shop_count": shop_count,
                "has_products": (
                    price_count > 0
                ),
            }
        )

        recent_machines.append(
            machine_data
        )

    recent_machines.sort(
        key=lambda machine: (
            machine.get(
                "introduced_date_value"
            )
            or datetime.min,
            normalize_integer(
                machine.get(
                    "price_count"
                )
            ),
            normalize_integer(
                machine.get(
                    "shop_count"
                )
            ),
            normalize_integer(
                machine.get(
                    "master_machine_id"
                ),
                default=-1,
            ),
        ),
        reverse=True,
    )

    return recent_machines[
        :limit_value
    ]


# ==================================================
# テンプレート用データ作成
# ==================================================

def build_index_page_context(
    today_price_drop_machines: list[
        dict[str, Any]
    ],
    recent_machines: list[
        dict[str, Any]
    ],
    lowest_price_machines: list[
        dict[str, Any]
    ],
    highest_avg_price_machines: list[
        dict[str, Any]
    ],
    generated_at: datetime,
    latest_record_date: str | None,
    previous_record_date: str | None,
) -> dict[str, Any]:
    """
    index.htmlへ渡す
    テンプレート変数を作成する。
    """
    seo = build_seo_data(
        title=(
            "実機相場ナビ｜"
            "パチンコ・パチスロ中古実機の価格比較"
        ),
        description=(
            "パチンコ・パチスロ実機の中古価格、"
            "最安価格、平均価格、値下げ情報を確認できる"
            "実機相場情報サイトです。"
        ),
        canonical_path="/",
        robots="index,follow",
        og_type="website",
    )


    return {
        # SEO情報
        **seo,

        # 共通テンプレート用
        "site_name": SITE_NAME,
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": True,

        # トップページではパンくずを表示しない
        "breadcrumbs": [],

        # 本日の値下げ
        "today_price_drop_machines": (
            today_price_drop_machines
        ),

        "today_price_drop_machine_count": len(
            today_price_drop_machines
        ),

        "latest_record_date": (
            latest_record_date
        ),

        "previous_record_date": (
            previous_record_date
        ),

        # 最近導入された機種
        "recent_machines": (
            recent_machines
        ),

        "recent_machine_count": len(
            recent_machines
        ),

        # ランキング
        "lowest_price_machines": (
            lowest_price_machines
        ),

        "highest_avg_price_machines": (
            highest_avg_price_machines
        ),

        # 日時情報
        "generated_at": generated_at,
        "updated_at": generated_at,

        # output/index.htmlから見た相対パス
        "root_prefix": "",
        "asset_prefix": "",
    }


# ==================================================
# 静的ファイルコピー
# ==================================================

def copy_index_static_files() -> None:
    """
    トップページで使用する静的ファイルを
    staticからoutputへコピーする。
    """
    copy_common_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
    )


    copy_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
        relative_paths=(
            "css/index.css",
        ),
    )


# ==================================================
# HTML生成
# ==================================================

def generate_index_page() -> None:
    """
    templates/index.htmlを使用して、
    output/index.htmlを生成する。

    機種一覧ページや機種詳細ページは変更しない。
    """
    start_time = time.time()
    generated_at = datetime.now()


    Path(OUTPUT_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )


    # 静的ファイルをコピー
    copy_index_static_files()


    # Jinja2環境を作成
    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
        root_prefix=ROOT_PREFIX,
        asset_prefix=ASSET_PREFIX,
    )


    try:
        template = environment.get_template(
            TEMPLATE_FILE_NAME
        )

    except TemplateNotFound as error:
        raise FileNotFoundError(
            "Jinja2テンプレートが"
            "見つかりません: "
            f"{error.name}"
        ) from error


    # ==========================================
    # 初期値
    # ==========================================

    latest_record_date: str | None = None
    previous_record_date: str | None = None

    today_price_drop_machines: list[
        dict[str, Any]
    ] = []

    recent_machines: list[
        dict[str, Any]
    ] = []

    lowest_price_machines: list[
        dict[str, Any]
    ] = []

    highest_avg_price_machines: list[
        dict[str, Any]
    ] = []


    # ==========================================
    # DBデータ取得
    # ==========================================

    with connect_database(
        DB_PATH
    ) as connection:

        connection.row_factory = sqlite3.Row


        check_table_exists(
            connection,
            MACHINE_MASTER_TABLE_NAME,
        )


        check_table_exists(
            connection,
            SUMMARY_TABLE_NAME,
        )


        check_table_exists(
            connection,
            PRICE_HISTORY_TABLE_NAME,
        )


        (
            latest_record_date,
            previous_record_date,
        ) = get_price_history_dates(
            connection
        )


        if (
            latest_record_date is not None
            and previous_record_date is not None
        ):
            today_price_drop_machines = (
                get_today_price_drop_machines(
                    connection=connection,
                    latest_record_date=(
                        latest_record_date
                    ),
                    previous_record_date=(
                        previous_record_date
                    ),
                    limit=(
                        TODAY_PRICE_DROP_MACHINE_LIMIT
                    ),
                )
            )


        recent_machines = get_recent_machines(
            connection=connection,
            generated_at=generated_at,
            recent_months=RECENT_MONTHS,
            limit=RECENT_MACHINE_LIMIT,
        )


        lowest_price_machines = (
            get_cheapest_machines(
                connection,
                limit=LOWEST_PRICE_MACHINE_LIMIT,
            )
        )


        highest_avg_price_machines = (
            get_highest_average_price_machines(
                connection,
                limit=(
                    HIGHEST_AVG_PRICE_MACHINE_LIMIT
                ),
            )
        )


    # ==========================================
    # テンプレート変数作成
    # ==========================================

    context = build_index_page_context(
        today_price_drop_machines=(
            today_price_drop_machines
        ),
        recent_machines=(
            recent_machines
        ),
        lowest_price_machines=(
            lowest_price_machines
        ),
        highest_avg_price_machines=(
            highest_avg_price_machines
        ),
        generated_at=generated_at,
        latest_record_date=(
            latest_record_date
        ),
        previous_record_date=(
            previous_record_date
        ),
    )


    # ==========================================
    # HTML生成
    # ==========================================

    html = template.render(
        **context
    )


    OUTPUT_FILE_PATH.write_text(
        html,
        encoding="utf-8",
        newline="",
    )


    elapsed_time = (
        time.time()
        - start_time
    )


    # ==========================================
    # 実行結果表示
    # ==========================================

    print("=" * 60)

    print(
        "トップページを生成しました。"
    )

    print(
        "出力先: "
        f"{OUTPUT_FILE_PATH}"
    )

    print(
        "テンプレート: "
        f"{Path(TEMPLATE_DIR) / TEMPLATE_FILE_NAME}"
    )

    print("-" * 60)


    print(
        "本日の値下げ: "
        f"{len(today_price_drop_machines):,}件"
    )

    print(
        "値下げ比較日: "
        f"{previous_record_date}"
        " → "
        f"{latest_record_date}"
    )

    print(
        "最近導入された機種: "
        f"{len(recent_machines):,}件"
    )

    print(
        "最安価格ランキング: "
        f"{len(lowest_price_machines):,}件"
    )

    print(
        "平均価格上位: "
        f"{len(highest_avg_price_machines):,}件"
    )

    print("-" * 60)

    print(
        "処理時間: "
        f"{elapsed_time:.2f}秒"
    )

    print("=" * 60)


# ==================================================
# 実行
# ==================================================

def main() -> None:
    """
    トップページ生成処理を実行する。
    """
    try:
        generate_index_page()

    except sqlite3.Error as error:
        print("-" * 60)

        print(
            "SQLite処理で"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    except Exception as error:
        print("-" * 60)

        print(
            "トップページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


if __name__ == "__main__":
    main()


# In[ ]:




