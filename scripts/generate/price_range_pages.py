#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sqlite3
import sys
import time

from datetime import datetime
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
# 出力先設定
# ==================================================

PRICE_RANGE_OUTPUT_DIR = os.path.join(
    OUTPUT_DIR,
    "price-range",
)


# ==================================================
# テンプレート設定
# ==================================================

PRICE_RANGE_INDEX_TEMPLATE_NAME = (
    "price_range/price_range_index.html"
)

PRICE_RANGE_DETAIL_TEMPLATE_NAME = (
    "price_range/price_range_detail.html"
)


# ==================================================
# CSS設定
# ==================================================

PRICE_RANGE_INDEX_CSS_PATH = (
    "css/price_range_index.css"
)

PRICE_RANGE_DETAIL_CSS_PATH = (
    "css/price_range_detail.css"
)


# ==================================================
# 価格帯ページ設定
# ==================================================

PRICE_RANGE_PAGE_LIMIT = 500


PRICE_RANGE_DEFINITIONS = (
    {
        "key": "10000-19999",
        "label": "1万円台",
        "short_label": "1万円台",
        "heading": (
            "1万円台で買える中古実機"
        ),
        "page_title": (
            "1万円台で買える"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が1万円台の"
            "パチンコ・パチスロ中古実機を、"
            "価格が安い順に掲載しています。"
        ),
        "min_price": 10000,
        "max_price": 20000,
        "range_text": (
            "10,000円以上20,000円未満"
        ),
    },
    {
        "key": "20000-29999",
        "label": "2万円台",
        "short_label": "2万円台",
        "heading": (
            "2万円台で買える中古実機"
        ),
        "page_title": (
            "2万円台で買える"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が2万円台の"
            "パチンコ・パチスロ中古実機を、"
            "価格が安い順に掲載しています。"
        ),
        "min_price": 20000,
        "max_price": 30000,
        "range_text": (
            "20,000円以上30,000円未満"
        ),
    },
    {
        "key": "30000-39999",
        "label": "3万円台",
        "short_label": "3万円台",
        "heading": (
            "3万円台で買える中古実機"
        ),
        "page_title": (
            "3万円台で買える"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が3万円台の"
            "パチンコ・パチスロ中古実機を、"
            "価格が安い順に掲載しています。"
        ),
        "min_price": 30000,
        "max_price": 40000,
        "range_text": (
            "30,000円以上40,000円未満"
        ),
    },
    {
        "key": "40000-59999",
        "label": "4万円～6万円未満",
        "short_label": "4万～6万円",
        "heading": (
            "4万円以上6万円未満で買える中古実機"
        ),
        "page_title": (
            "4万円以上6万円未満で買える"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が4万円以上"
            "6万円未満のパチンコ・パチスロ"
            "中古実機を、価格が安い順に"
            "掲載しています。"
        ),
        "min_price": 40000,
        "max_price": 60000,
        "range_text": (
            "40,000円以上60,000円未満"
        ),
    },
    {
        "key": "60000-99999",
        "label": "6万円～10万円未満",
        "short_label": "6万～10万円",
        "heading": (
            "6万円以上10万円未満で買える中古実機"
        ),
        "page_title": (
            "6万円以上10万円未満で買える"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が6万円以上"
            "10万円未満のパチンコ・パチスロ"
            "中古実機を、価格が安い順に"
            "掲載しています。"
        ),
        "min_price": 60000,
        "max_price": 100000,
        "range_text": (
            "60,000円以上100,000円未満"
        ),
    },
    {
        "key": "100000-199999",
        "label": "10万円～20万円未満",
        "short_label": "10万～20万円",
        "heading": (
            "10万円以上20万円未満の中古実機"
        ),
        "page_title": (
            "10万円以上20万円未満の"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が10万円以上"
            "20万円未満のパチンコ・パチスロ"
            "中古実機を、価格が安い順に"
            "掲載しています。"
        ),
        "min_price": 100000,
        "max_price": 200000,
        "range_text": (
            "100,000円以上200,000円未満"
        ),
    },
    {
        "key": "200000-499999",
        "label": "20万円～50万円未満",
        "short_label": "20万～50万円",
        "heading": (
            "20万円以上50万円未満の中古実機"
        ),
        "page_title": (
            "20万円以上50万円未満の"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が20万円以上"
            "50万円未満のパチンコ・パチスロ"
            "中古実機を、価格が安い順に"
            "掲載しています。"
        ),
        "min_price": 200000,
        "max_price": 500000,
        "range_text": (
            "200,000円以上500,000円未満"
        ),
    },
    {
        "key": "500000-over",
        "label": "50万円以上",
        "short_label": "50万円以上",
        "heading": (
            "50万円以上の中古実機"
        ),
        "page_title": (
            "50万円以上の"
            "パチンコ・パチスロ中古実機"
        ),
        "description": (
            "現在の最安価格が50万円以上の"
            "パチンコ・パチスロ中古実機を、"
            "価格が安い順に掲載しています。"
        ),
        "min_price": 500000,
        "max_price": None,
        "range_text": (
            "500,000円以上"
        ),
    },
)


# ==================================================
# HTML書き込み
# ==================================================

def write_html(
    output_file_path: str,
    html: str,
) -> None:
    """
    HTMLを指定された場所へ保存する。
    """
    output_parent_dir = os.path.dirname(
        output_file_path
    )

    os.makedirs(
        output_parent_dir,
        exist_ok=True,
    )

    with open(
        output_file_path,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        file.write(
            html
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
        return PRICE_RANGE_PAGE_LIMIT

    if limit_value <= 0:
        return PRICE_RANGE_PAGE_LIMIT

    return limit_value


def validate_price_range_definition(
    definition: dict[str, Any],
) -> None:
    """
    価格帯設定に問題がないか確認する。
    """
    required_keys = (
        "key",
        "label",
        "short_label",
        "heading",
        "page_title",
        "description",
        "min_price",
        "max_price",
        "range_text",
    )

    for required_key in required_keys:
        if required_key not in definition:
            raise ValueError(
                "価格帯設定に必要な項目がありません: "
                f"{required_key}"
            )

    key = str(
        definition["key"]
    ).strip()

    if not key:
        raise ValueError(
            "価格帯設定のkeyが空です。"
        )

    label = str(
        definition["label"]
    ).strip()

    if not label:
        raise ValueError(
            "価格帯設定のlabelが空です。"
        )

    short_label = str(
        definition["short_label"]
    ).strip()

    if not short_label:
        raise ValueError(
            "価格帯設定のshort_labelが空です。"
        )

    min_price = int(
        definition["min_price"]
    )

    max_price = definition[
        "max_price"
    ]

    if min_price < 0:
        raise ValueError(
            "min_priceは0以上で指定してください。"
        )

    if max_price is not None:
        max_price = int(
            max_price
        )

        if max_price <= min_price:
            raise ValueError(
                "max_priceはmin_priceより"
                "大きい値を指定してください。"
            )


def validate_all_price_range_definitions(
) -> None:
    """
    すべての価格帯設定を検証する。

    keyの重複と、
    価格範囲の重複も確認する。
    """
    used_keys: set[str] = set()
    previous_max_price: int | None = None

    for index, definition in enumerate(
        PRICE_RANGE_DEFINITIONS
    ):
        validate_price_range_definition(
            definition
        )

        key = str(
            definition["key"]
        ).strip()

        if key in used_keys:
            raise ValueError(
                "価格帯設定のkeyが重複しています: "
                f"{key}"
            )

        used_keys.add(
            key
        )

        min_price = int(
            definition["min_price"]
        )

        raw_max_price = definition[
            "max_price"
        ]

        max_price = (
            int(raw_max_price)
            if raw_max_price is not None
            else None
        )

        if (
            index > 0
            and previous_max_price is None
        ):
            raise ValueError(
                "上限なしの価格帯は"
                "最後に配置してください。"
            )

        if (
            previous_max_price is not None
            and min_price < previous_max_price
        ):
            raise ValueError(
                "価格帯設定が重複しています: "
                f"{key}"
            )

        previous_max_price = (
            max_price
        )


# ==================================================
# SQL条件作成
# ==================================================

def build_common_where_sql() -> str:
    """
    価格帯ページ共通の対象条件SQLを返す。
    """
    return """
        master_machine_id IS NOT NULL

        AND TRIM(
            CAST(
                master_machine_id AS TEXT
            )
        ) != ''

        AND master_machine_name IS NOT NULL
        AND TRIM(master_machine_name) != ''

        AND min_price IS NOT NULL
        AND min_price > 0
    """


def build_price_range_where_sql(
    min_price: int,
    max_price: int | None,
) -> tuple[str, tuple[int, ...]]:
    """
    価格帯条件SQLと
    バインドパラメータを返す。

    max_priceは未満として扱う。
    """
    common_where_sql = (
        build_common_where_sql()
    )

    if max_price is None:
        where_sql = f"""
            {common_where_sql}

            AND min_price >= ?
        """

        parameters = (
            int(min_price),
        )

        return (
            where_sql,
            parameters,
        )

    where_sql = f"""
        {common_where_sql}

        AND min_price >= ?
        AND min_price < ?
    """

    parameters = (
        int(min_price),
        int(max_price),
    )

    return (
        where_sql,
        parameters,
    )


# ==================================================
# DBデータ取得
# ==================================================

def get_price_range_machines(
    connection: sqlite3.Connection,
    min_price: int,
    max_price: int | None,
    limit: int = PRICE_RANGE_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    """
    指定価格帯に該当する機種を取得する。

    判定対象:
        min_price

    並び順:
        最安価格が安い順
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    limit_value = normalize_page_limit(
        limit
    )

    (
        where_sql,
        where_parameters,
    ) = build_price_range_where_sql(
        min_price=min_price,
        max_price=max_price,
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

        FROM {table_name}

        WHERE
            {where_sql}

        ORDER BY
            min_price ASC,
            price_count DESC,
            shop_count DESC,

            CASE
                WHEN CAST(
                    master_machine_id AS TEXT
                ) GLOB '[0-9]*'
                THEN CAST(
                    master_machine_id AS INTEGER
                )
                ELSE 999999999
            END ASC,

            master_machine_id ASC

        LIMIT ?
    """

    parameters = (
        *where_parameters,
        limit_value,
    )

    rows = connection.execute(
        sql,
        parameters,
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]


def get_price_range_machine_count(
    connection: sqlite3.Connection,
    min_price: int,
    max_price: int | None,
) -> int:
    """
    指定価格帯に該当する
    全機種数を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    (
        where_sql,
        parameters,
    ) = build_price_range_where_sql(
        min_price=min_price,
        max_price=max_price,
    )

    sql = f"""
        SELECT
            COUNT(*) AS machine_count

        FROM {table_name}

        WHERE
            {where_sql}
    """

    row = connection.execute(
        sql,
        parameters,
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["machine_count"]
        or 0
    )


def get_price_range_updated_at(
    connection: sqlite3.Connection,
    min_price: int,
    max_price: int | None,
) -> Any:
    """
    指定価格帯に該当するデータの
    最終更新日時を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    (
        where_sql,
        parameters,
    ) = build_price_range_where_sql(
        min_price=min_price,
        max_price=max_price,
    )

    sql = f"""
        SELECT
            MAX(
                COALESCE(
                    latest_scraped_at,
                    updated_at
                )
            ) AS price_range_updated_at

        FROM {table_name}

        WHERE
            {where_sql}
    """

    row = connection.execute(
        sql,
        parameters,
    ).fetchone()

    if row is None:
        return None

    return row[
        "price_range_updated_at"
    ]


def get_all_price_range_updated_at(
    connection: sqlite3.Connection,
) -> Any:
    """
    価格帯一覧ページ用の
    最終更新日時を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    common_where_sql = (
        build_common_where_sql()
    )

    sql = f"""
        SELECT
            MAX(
                COALESCE(
                    latest_scraped_at,
                    updated_at
                )
            ) AS price_range_updated_at

        FROM {table_name}

        WHERE
            {common_where_sql}
    """

    row = connection.execute(
        sql
    ).fetchone()

    if row is None:
        return None

    return row[
        "price_range_updated_at"
    ]


# ==================================================
# 価格帯一覧データ作成
# ==================================================

def build_price_range_index_items(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """
    価格帯一覧ページに表示する
    価格帯情報を作成する。
    """
    items: list[dict[str, Any]] = []

    for definition in (
        PRICE_RANGE_DEFINITIONS
    ):
        validate_price_range_definition(
            definition
        )

        min_price = int(
            definition["min_price"]
        )

        raw_max_price = definition[
            "max_price"
        ]

        max_price = (
            int(raw_max_price)
            if raw_max_price is not None
            else None
        )

        machine_count = (
            get_price_range_machine_count(
                connection=connection,
                min_price=min_price,
                max_price=max_price,
            )
        )

        item = {
            **definition,

            "min_price": min_price,
            "max_price": max_price,
            "machine_count": machine_count,

            # /price-range/index.htmlから見た相対URL
            "url": (
                f"{definition['key']}/"
            ),
        }

        items.append(
            item
        )

    return items


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_price_range_meta_description(
    definition: dict[str, Any],
    machine_count: int,
) -> str:
    """
    価格帯詳細ページ用の
    meta descriptionを作成する。
    """
    range_text = str(
        definition["range_text"]
    )

    label = str(
        definition["label"]
    )

    if machine_count > 0:
        return (
            "現在の最安価格が"
            f"{range_text}のパチンコ・パチスロ"
            f"中古実機を{machine_count:,}機種掲載しています。"
            f"{label}で購入できる機種について、"
            "最安値、平均価格、出品件数、"
            "販売店情報を比較できます。"
        )

    return (
        "現在の最安価格が"
        f"{range_text}のパチンコ・パチスロ"
        "中古実機を掲載する価格帯別ページです。"
    )


def build_price_range_index_meta_description(
    total_machine_count: int,
) -> str:
    """
    価格帯一覧ページ用の
    meta descriptionを作成する。
    """
    if total_machine_count > 0:
        return (
            "中古パチンコ・パチスロ実機を"
            "価格帯別に探せます。"
            "1万円台、2万円台、3万円台から"
            "50万円以上まで、現在の最安価格を"
            f"基準に{total_machine_count:,}機種を"
            "分類して掲載しています。"
        )

    return (
        "中古パチンコ・パチスロ実機を、"
        "現在の最安価格を基準とした"
        "価格帯別に探せる一覧ページです。"
    )


# ==================================================
# パンくずリスト作成
# ==================================================

def create_price_range_index_breadcrumbs(
) -> list[dict[str, Any]]:
    """
    価格帯一覧ページの
    パンくずを作成する。
    """
    return [
        {
            "title": "トップ",
            "url": "../",
        },
        {
            "title": "価格帯から探す",
            "url": None,
        },
    ]


def create_price_range_detail_breadcrumbs(
    page_title: str,
) -> list[dict[str, Any]]:
    """
    価格帯詳細ページの
    パンくずを作成する。
    """
    return [
        {
            "title": "トップ",
            "url": "../../",
        },
        {
            "title": "価格帯から探す",
            "url": "../",
        },
        {
            "title": page_title,
            "url": None,
        },
    ]


# ==================================================
# 出力パス作成
# ==================================================

def get_price_range_index_output_file_path(
) -> str:
    """
    価格帯一覧ページの
    出力ファイルパスを返す。
    """
    return os.path.join(
        PRICE_RANGE_OUTPUT_DIR,
        "index.html",
    )


def get_price_range_detail_output_file_path(
    price_range_key: str,
) -> str:
    """
    価格帯詳細ページの
    出力ファイルパスを返す。
    """
    return os.path.join(
        PRICE_RANGE_OUTPUT_DIR,
        price_range_key,
        "index.html",
    )


def get_price_range_detail_canonical_path(
    price_range_key: str,
) -> str:
    """
    価格帯詳細ページの
    canonicalパスを返す。
    """
    return (
        f"/price-range/{price_range_key}/"
    )


# ==================================================
# 価格帯一覧ページ生成
# ==================================================

def generate_price_range_index_page(
    environment: Environment,
    connection: sqlite3.Connection,
    generated_at: datetime,
) -> int:
    """
    価格帯一覧ページを生成する。

    出力:
        /price-range/index.html
    """
    template = environment.get_template(
        PRICE_RANGE_INDEX_TEMPLATE_NAME
    )

    price_ranges = (
        build_price_range_index_items(
            connection=connection,
        )
    )

    total_machine_count = sum(
        int(
            item["machine_count"]
            or 0
        )
        for item in price_ranges
    )

    price_range_updated_at = (
        get_all_price_range_updated_at(
            connection=connection,
        )
    )

    meta_description = (
        build_price_range_index_meta_description(
            total_machine_count=(
                total_machine_count
            ),
        )
    )

    robots = (
        "index,follow"
        if total_machine_count > 0
        else "noindex,follow"
    )

    seo = build_seo_data(
        title=(
            "価格帯から中古パチンコ・"
            "パチスロ実機を探す"
        ),
        description=meta_description,
        canonical_path="/price-range/",
        robots=robots,
        og_type="website",
    )

    context = {
        **seo,

        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        "breadcrumbs": (
            create_price_range_index_breadcrumbs()
        ),

        "price_range_title": (
            "価格帯から中古実機を探す"
        ),
        "price_range_description": (
            "現在の最安価格を基準に、"
            "中古パチンコ・パチスロ実機を"
            "価格帯別に掲載しています。"
        ),

        "price_ranges": price_ranges,
        "price_range_count": len(
            price_ranges
        ),
        "total_machine_count": (
            total_machine_count
        ),

        "generated_at": generated_at,
        "updated_at": (
            price_range_updated_at
            or generated_at
        ),

        # /price-range/index.htmlから
        # サイトルートへの相対パス
        "root_prefix": "../",
        "asset_prefix": "../",
    }

    html = template.render(
        **context
    )

    output_file_path = (
        get_price_range_index_output_file_path()
    )

    write_html(
        output_file_path=output_file_path,
        html=html,
    )

    print(
        "[生成] price-range/index.html"
        f" - {len(price_ranges):,}価格帯"
        f" / 対象{total_machine_count:,}機種"
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

    return total_machine_count


# ==================================================
# 価格帯詳細ページ生成
# ==================================================

def generate_price_range_detail_page(
    environment: Environment,
    connection: sqlite3.Connection,
    generated_at: datetime,
    definition: dict[str, Any],
) -> int:
    """
    1つの価格帯詳細ページを生成する。
    """
    validate_price_range_definition(
        definition
    )

    price_range_key = str(
        definition["key"]
    )

    min_price = int(
        definition["min_price"]
    )

    raw_max_price = definition[
        "max_price"
    ]

    max_price = (
        int(raw_max_price)
        if raw_max_price is not None
        else None
    )

    template = environment.get_template(
        PRICE_RANGE_DETAIL_TEMPLATE_NAME
    )

    machines = get_price_range_machines(
        connection=connection,
        min_price=min_price,
        max_price=max_price,
        limit=PRICE_RANGE_PAGE_LIMIT,
    )

    total_machine_count = (
        get_price_range_machine_count(
            connection=connection,
            min_price=min_price,
            max_price=max_price,
        )
    )

    price_range_updated_at = (
        get_price_range_updated_at(
            connection=connection,
            min_price=min_price,
            max_price=max_price,
        )
    )

    meta_description = (
        build_price_range_meta_description(
            definition=definition,
            machine_count=total_machine_count,
        )
    )

    canonical_path = (
        get_price_range_detail_canonical_path(
            price_range_key
        )
    )

    robots = (
        "index,follow"
        if total_machine_count > 0
        else "noindex,follow"
    )

    seo = build_seo_data(
        title=str(
            definition["page_title"]
        ),
        description=meta_description,
        canonical_path=canonical_path,
        robots=robots,
        og_type="website",
    )

    context = {
        **seo,

        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        "breadcrumbs": (
            create_price_range_detail_breadcrumbs(
                str(
                    definition["heading"]
                )
            )
        ),

        "price_range_key": price_range_key,
        "price_range_label": str(
            definition["label"]
        ),
        "price_range_short_label": str(
            definition["short_label"]
        ),
        "price_range_title": str(
            definition["heading"]
        ),
        "price_range_description": str(
            definition["description"]
        ),
        "price_range_text": str(
            definition["range_text"]
        ),

        "price_min": min_price,
        "price_max": max_price,

        "machines": machines,
        "machine_count": len(
            machines
        ),
        "total_machine_count": (
            total_machine_count
        ),
        "page_limit": (
            PRICE_RANGE_PAGE_LIMIT
        ),

        "generated_at": generated_at,
        "updated_at": (
            price_range_updated_at
            or generated_at
        ),

        # /price-range/{key}/index.htmlから
        # サイトルートへの相対パス
        "root_prefix": "../../",
        "asset_prefix": "../../",
    }

    html = template.render(
        **context
    )

    output_file_path = (
        get_price_range_detail_output_file_path(
            price_range_key
        )
    )

    write_html(
        output_file_path=output_file_path,
        html=html,
    )

    print(
        "[生成] "
        f"price-range/{price_range_key}/index.html"
        f" - {len(machines):,}機種"
        f" / 対象{total_machine_count:,}機種"
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

    return len(
        machines
    )


# ==================================================
# 全価格帯ページ生成
# ==================================================

def generate_all_price_range_pages() -> None:
    """
    価格帯一覧ページと
    すべての価格帯詳細ページを生成する。
    """
    start_time = time.perf_counter()

    generated_at = datetime.now()

    validate_all_price_range_definitions()

    os.makedirs(
        PRICE_RANGE_OUTPUT_DIR,
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
            PRICE_RANGE_INDEX_CSS_PATH,
            PRICE_RANGE_DETAIL_CSS_PATH,
        ),
    )

    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
    )

    generated_page_count = 0
    detail_page_count = 0
    total_display_machine_count = 0
    total_index_machine_count = 0

    with connect_database(
        DB_PATH
    ) as connection:
        check_table_exists(
            connection,
            SUMMARY_TABLE_NAME,
        )

        # 価格帯一覧ページ
        total_index_machine_count = (
            generate_price_range_index_page(
                environment=environment,
                connection=connection,
                generated_at=generated_at,
            )
        )

        generated_page_count += 1

        # 価格帯詳細ページ
        for definition in (
            PRICE_RANGE_DEFINITIONS
        ):
            display_machine_count = (
                generate_price_range_detail_page(
                    environment=environment,
                    connection=connection,
                    generated_at=generated_at,
                    definition=definition,
                )
            )

            generated_page_count += 1
            detail_page_count += 1

            total_display_machine_count += (
                display_machine_count
            )

    elapsed_time = (
        time.perf_counter()
        - start_time
    )

    print("=" * 60)

    print(
        "価格帯別ページを生成しました。"
    )

    print(
        "出力ディレクトリ: "
        f"{PRICE_RANGE_OUTPUT_DIR}"
    )

    print(
        "生成ページ数: "
        f"{generated_page_count:,}ページ"
    )

    print(
        "価格帯一覧ページ: "
        "1ページ"
    )

    print(
        "価格帯詳細ページ: "
        f"{detail_page_count:,}ページ"
    )

    print(
        "一覧ページ対象機種数: "
        f"{total_index_machine_count:,}機種"
    )

    print(
        "詳細ページ掲載件数合計: "
        f"{total_display_machine_count:,}件"
    )

    print(
        "1ページの表示上限: "
        f"{PRICE_RANGE_PAGE_LIMIT:,}件"
    )

    print(
        f"処理時間: {elapsed_time:.2f}秒"
    )

    print("=" * 60)


# ==================================================
# 実行
# ==================================================

if __name__ == "__main__":
    try:
        generate_all_price_range_pages()

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

    except TemplateNotFound as error:
        print("-" * 60)

        print(
            "Jinja2テンプレートが"
            "見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            "価格帯一覧テンプレート: "
            f"{PRICE_RANGE_INDEX_TEMPLATE_NAME}"
        )

        print(
            "価格帯詳細テンプレート: "
            f"{PRICE_RANGE_DETAIL_TEMPLATE_NAME}"
        )

        raise

    except FileNotFoundError as error:
        print("-" * 60)

        print(
            "価格帯ページ用の静的ファイルが"
            "見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            "確認するCSS: "
            f"{os.path.join(PROJECT_ROOT, 'static', PRICE_RANGE_INDEX_CSS_PATH)}"
        )

        print(
            "確認するCSS: "
            f"{os.path.join(PROJECT_ROOT, 'static', PRICE_RANGE_DETAIL_CSS_PATH)}"
        )

        raise

    except (TypeError, ValueError) as error:
        print("-" * 60)

        print(
            "価格帯設定に"
            "エラーがあります。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    except Exception as error:
        print("-" * 60)

        print(
            "価格帯別ページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


# In[ ]:




