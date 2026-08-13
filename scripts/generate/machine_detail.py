import os
from collections import defaultdict
import sqlite3
import sys
import time
import re

from datetime import date, datetime, timedelta
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
    SITE_URL,
    TEMPLATE_DIR,
)

from utils.breadcrumb_utils import (
    create_machine_detail_breadcrumbs,
)

from utils.db_utils import (
    PRICE_HISTORY_TABLE_NAME,
    PRODUCT_TABLE_NAME,
    SUMMARY_TABLE_NAME,
    check_tables_exist,
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
# 初期設定
# ==================================================

START_TIME = time.time()


# ==================================================
# ページ設定
# ==================================================

TEMPLATE_FILE_NAME = (
    "machines/machine_detail.html"
)

OUTPUT_MACHINE_DIR = (
    Path(OUTPUT_DIR)
    / "machines"
)

PRICE_HISTORY_DAYS = 90


# 関連機種表示数
RELATED_MACHINE_LIMIT = 6

# 同シリーズ
RELATED_SERIES_LIMIT = 6

# 価格が近い機種
NEAR_PRICE_MACHINE_LIMIT = 6

# 同タイプ
RELATED_TYPE_LIMIT = 6


# ==================================================
# 機種ID整形
# ==================================================

def normalize_machine_id(
    value: Any,
) -> str:
    """
    master_machine_idを
    HTMLファイル名として使用できる文字列へ変換する。
    """
    if value is None:
        return ""

    machine_id = str(value).strip()

    if not machine_id:
        return ""

    return re.sub(
        r'[\\/:*?"<>|]',
        "_",
        machine_id,
    )


# ==================================================
# 関連機種データ作成
# ==================================================

def normalize_maker_name(
    value: Any,
) -> str:
    """
    メーカー名を比較用文字列へ変換する。
    """
    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_series_name(
    value: Any,
) -> str:
    """
    シリーズ名を比較用文字列へ変換する。
    """
    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_machine_type(
    value: Any,
) -> str:
    """
    機種タイプを比較用文字列へ変換する。
    """
    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_integer(
    value: Any,
    default: int = 0,
) -> int:
    """
    値を整数へ変換する。

    変換できない場合はdefaultを返す。
    """
    try:
        return int(
            float(value)
        )
    except (TypeError, ValueError):
        return default


def normalize_related_price(
    value: Any,
) -> int | None:
    """
    関連機種の価格比較用に、
    正の整数価格へ変換する。
    """
    if value is None:
        return None

    try:
        price = int(
            float(value)
        )
    except (TypeError, ValueError):
        return None

    if price <= 0:
        return None

    return price


def related_machine_sort_key(
    machine: dict[str, Any],
) -> tuple[int, int, str]:
    """
    関連機種の基本並び順を作成する。

    優先順位:
    1. 出品件数が多い
    2. 機種IDの数値が小さい
    3. 機種IDの文字列順
    """
    price_count = normalize_integer(
        machine.get("price_count")
    )

    machine_id_text = str(
        machine.get("master_machine_id")
        or ""
    ).strip()

    machine_id_number = normalize_integer(
        machine_id_text,
        default=999999999,
    )

    return (
        -price_count,
        machine_id_number,
        machine_id_text,
    )


def prepare_related_machine(
    machine: dict[str, Any],
) -> dict[str, Any]:
    """
    関連機種をテンプレート表示用に整形する。
    """
    related_machine = dict(
        machine
    )

    machine_file_id = normalize_machine_id(
        machine.get(
            "master_machine_id"
        )
    )

    static_image_path = (
        Path(PROJECT_ROOT)
        / "static"
        / "img"
        / "machines"
        / f"{machine_file_id}.webp"
    )

    if static_image_path.is_file():
        machine_image_path = (
            f"../img/machines/"
            f"{machine_file_id}.webp"
        )
    else:
        machine_image_path = (
            "../img/no_image.webp"
        )

    related_machine.update(
        {
            "machine_file_id": (
                machine_file_id
            ),
            "detail_url": (
                f"{machine_file_id}.html"
            ),
            "machine_image_path": (
                machine_image_path
            ),
        }
    )

    return related_machine


# ==================================================
# 同メーカー関連機種
# ==================================================

def build_related_machine_index(
    machines: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    全機種をメーカー別にまとめる。

    戻り値:
        {
            "サミー": [機種データ, ...],
            "山佐": [機種データ, ...],
        }
    """
    related_machine_index: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    seen_machine_ids: dict[
        str,
        set[str]
    ] = {}

    for machine in machines:
        maker_name = normalize_maker_name(
            machine.get(
                "master_machine_maker"
            )
        )

        machine_id = str(
            machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if not maker_name or not machine_id:
            continue

        if maker_name not in related_machine_index:
            related_machine_index[
                maker_name
            ] = []

            seen_machine_ids[
                maker_name
            ] = set()

        if (
            machine_id
            in seen_machine_ids[maker_name]
        ):
            continue

        seen_machine_ids[
            maker_name
        ].add(
            machine_id
        )

        related_machine_index[
            maker_name
        ].append(
            machine
        )

    for maker_machines in (
        related_machine_index.values()
    ):
        maker_machines.sort(
            key=related_machine_sort_key
        )

    return related_machine_index


def get_related_machines(
    machine: dict[str, Any],
    related_machine_index: dict[
        str,
        list[dict[str, Any]]
    ],
    limit: int = RELATED_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    """
    現在の機種と同じメーカーの関連機種を取得する。

    現在表示中の機種は除外する。
    """
    maker_name = normalize_maker_name(
        machine.get(
            "master_machine_maker"
        )
    )

    current_machine_id = str(
        machine.get(
            "master_machine_id"
        )
        or ""
    ).strip()

    if (
        not maker_name
        or not current_machine_id
    ):
        return []

    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        limit_value = RELATED_MACHINE_LIMIT

    if limit_value <= 0:
        return []

    maker_machines = (
        related_machine_index.get(
            maker_name,
            [],
        )
    )

    related_machines: list[
        dict[str, Any]
    ] = []

    for related_machine in maker_machines:
        related_machine_id = str(
            related_machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if (
            not related_machine_id
            or related_machine_id
            == current_machine_id
        ):
            continue

        related_machines.append(
            prepare_related_machine(
                related_machine
            )
        )

        if (
            len(related_machines)
            >= limit_value
        ):
            break

    return related_machines


# ==================================================
# 同シリーズ関連機種
# ==================================================

def build_series_machine_index(
    machines: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    全機種をシリーズ別にまとめる。

    master_machine_seriesが空の機種は対象外。
    """
    series_machine_index: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    seen_machine_ids: dict[
        str,
        set[str]
    ] = {}

    for machine in machines:
        series_name = normalize_series_name(
            machine.get(
                "master_machine_series"
            )
        )

        machine_id = str(
            machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if (
            not series_name
            or not machine_id
        ):
            continue

        if (
            series_name
            not in series_machine_index
        ):
            series_machine_index[
                series_name
            ] = []

            seen_machine_ids[
                series_name
            ] = set()

        if (
            machine_id
            in seen_machine_ids[
                series_name
            ]
        ):
            continue

        seen_machine_ids[
            series_name
        ].add(
            machine_id
        )

        series_machine_index[
            series_name
        ].append(
            machine
        )

    for series_machines in (
        series_machine_index.values()
    ):
        series_machines.sort(
            key=related_machine_sort_key
        )

    return series_machine_index


def get_series_related_machines(
    machine: dict[str, Any],
    series_machine_index: dict[
        str,
        list[dict[str, Any]]
    ],
    limit: int = RELATED_SERIES_LIMIT,
) -> list[dict[str, Any]]:
    """
    現在の機種と同じシリーズの機種を取得する。

    現在表示中の機種は除外する。
    """
    series_name = normalize_series_name(
        machine.get(
            "master_machine_series"
        )
    )

    current_machine_id = str(
        machine.get(
            "master_machine_id"
        )
        or ""
    ).strip()

    if (
        not series_name
        or not current_machine_id
    ):
        return []

    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        limit_value = RELATED_SERIES_LIMIT

    if limit_value <= 0:
        return []

    series_machines = (
        series_machine_index.get(
            series_name,
            [],
        )
    )

    related_machines: list[
        dict[str, Any]
    ] = []

    for related_machine in series_machines:
        related_machine_id = str(
            related_machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if (
            not related_machine_id
            or related_machine_id
            == current_machine_id
        ):
            continue

        related_machines.append(
            prepare_related_machine(
                related_machine
            )
        )

        if (
            len(related_machines)
            >= limit_value
        ):
            break

    return related_machines


# ==================================================
# 同タイプ関連機種
# ==================================================

def build_type_machine_index(
    machines: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    全機種をmaster_machine_type別にまとめる。

    master_machine_typeが空の機種は対象外。
    """
    type_machine_index: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    seen_machine_ids: dict[
        str,
        set[str]
    ] = {}

    for machine in machines:
        machine_type = normalize_machine_type(
            machine.get(
                "master_machine_type"
            )
        )

        machine_id = str(
            machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if (
            not machine_type
            or not machine_id
        ):
            continue

        if (
            machine_type
            not in type_machine_index
        ):
            type_machine_index[
                machine_type
            ] = []

            seen_machine_ids[
                machine_type
            ] = set()

        if (
            machine_id
            in seen_machine_ids[
                machine_type
            ]
        ):
            continue

        seen_machine_ids[
            machine_type
        ].add(
            machine_id
        )

        type_machine_index[
            machine_type
        ].append(
            machine
        )

    for type_machines in (
        type_machine_index.values()
    ):
        type_machines.sort(
            key=related_machine_sort_key
        )

    return type_machine_index


def get_type_related_machines(
    machine: dict[str, Any],
    type_machine_index: dict[
        str,
        list[dict[str, Any]]
    ],
    limit: int = RELATED_TYPE_LIMIT,
) -> list[dict[str, Any]]:
    """
    現在の機種と同じmaster_machine_typeの
    関連機種を取得する。

    現在表示中の機種は除外する。
    """
    machine_type = normalize_machine_type(
        machine.get(
            "master_machine_type"
        )
    )

    current_machine_id = str(
        machine.get(
            "master_machine_id"
        )
        or ""
    ).strip()

    if (
        not machine_type
        or not current_machine_id
    ):
        return []

    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        limit_value = RELATED_TYPE_LIMIT

    if limit_value <= 0:
        return []

    type_machines = (
        type_machine_index.get(
            machine_type,
            [],
        )
    )

    related_machines: list[
        dict[str, Any]
    ] = []

    for related_machine in type_machines:
        related_machine_id = str(
            related_machine.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if (
            not related_machine_id
            or related_machine_id
            == current_machine_id
        ):
            continue

        related_machines.append(
            prepare_related_machine(
                related_machine
            )
        )

        if (
            len(related_machines)
            >= limit_value
        ):
            break

    return related_machines


# ==================================================
# 価格が近い機種
# ==================================================

def near_price_machine_sort_key(
    machine: dict[str, Any],
    current_price: int,
) -> tuple[
    int,
    int,
    int,
    int,
    str,
]:
    """
    価格が近い機種の並び順を作成する。

    優先順位:
    1. 現在機種との価格差が小さい
    2. 出品件数が多い
    3. 最安価格が安い
    4. 機種IDの数値が小さい
    5. 機種ID文字列順
    """
    candidate_price = (
        normalize_related_price(
            machine.get("min_price")
        )
    )

    if candidate_price is None:
        price_difference = (
            999999999999
        )
        candidate_price_value = (
            999999999999
        )
    else:
        price_difference = abs(
            candidate_price
            - current_price
        )

        candidate_price_value = (
            candidate_price
        )

    price_count = normalize_integer(
        machine.get(
            "price_count"
        )
    )

    machine_id_text = str(
        machine.get(
            "master_machine_id"
        )
        or ""
    ).strip()

    machine_id_number = normalize_integer(
        machine_id_text,
        default=999999999,
    )

    return (
        price_difference,
        -price_count,
        candidate_price_value,
        machine_id_number,
        machine_id_text,
    )


def get_near_price_machines(
    machine: dict[str, Any],
    machines: list[dict[str, Any]],
    limit: int = NEAR_PRICE_MACHINE_LIMIT,
) -> list[dict[str, Any]]:
    """
    現在の機種と最安価格が近い機種を取得する。

    判定:
        abs(
            候補機種のmin_price
            - 現在機種のmin_price
        )

    現在機種と価格なし機種は除外する。
    """
    current_machine_id = str(
        machine.get(
            "master_machine_id"
        )
        or ""
    ).strip()

    current_price = (
        normalize_related_price(
            machine.get(
                "min_price"
            )
        )
    )

    if (
        not current_machine_id
        or current_price is None
    ):
        return []

    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        limit_value = (
            NEAR_PRICE_MACHINE_LIMIT
        )

    if limit_value <= 0:
        return []

    candidates: list[
        dict[str, Any]
    ] = []

    seen_machine_ids: set[str] = set()

    for candidate in machines:
        candidate_machine_id = str(
            candidate.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if not candidate_machine_id:
            continue

        if (
            candidate_machine_id
            == current_machine_id
        ):
            continue

        if (
            candidate_machine_id
            in seen_machine_ids
        ):
            continue

        candidate_price = (
            normalize_related_price(
                candidate.get(
                    "min_price"
                )
            )
        )

        # 価格なし機種は除外
        if candidate_price is None:
            continue

        seen_machine_ids.add(
            candidate_machine_id
        )

        candidates.append(
            candidate
        )

    candidates.sort(
        key=lambda candidate: (
            near_price_machine_sort_key(
                machine=candidate,
                current_price=current_price,
            )
        )
    )

    return [
        prepare_related_machine(
            candidate
        )
        for candidate in (
            candidates[
                :limit_value
            ]
        )
    ]


# ==================================================
# DBデータ取得
# ==================================================

def get_machines(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:

    sql = """
    SELECT

        m.master_machine_id,
        m.master_machine_name,
        m.master_machine_maker,
        m.master_machine_model,
        m.master_machine_type,
        m.master_machine_gouki,
        m.master_machine_memo,
        m.master_machine_introduced_date,
        m.master_machine_game_system,

        -- 補足情報
        m.master_machine_ptown_name_kana,
        m.master_machine_alias,
        m.master_machine_series,
        m.master_machine_short_name,

        s.latest_price,
        s.min_price,
        s.max_price,
        s.avg_price,
        s.median_price,
        s.price_count,
        s.shop_count,
        s.lowest_shop_name,
        s.lowest_product_url,
        s.first_seen,
        s.last_seen,
        s.latest_scraped_at,
        s.created_at,
        s.updated_at

    FROM machine_master AS m

    LEFT JOIN product_summary AS s
      ON m.master_machine_id = s.master_machine_id

    ORDER BY
        CAST(m.master_machine_id AS INTEGER),
        m.master_machine_id
    """

    rows = connection.execute(
        sql
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]


def normalize_machine_lookup_key(
    value: Any,
) -> str:
    """
    master_machine_idを辞書検索用の文字列へ変換する。

    SQLite側の値が数値型・文字列型のどちらでも、
    同じ機種IDとして検索できるようにする。
    """
    if value is None:
        return ""

    return str(
        value
    ).strip()


def get_all_products_by_machine(
    connection: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    """
    全機種の商品を1回のSQLで取得し、
    master_machine_idごとの辞書にまとめる。

    同一機種内で同じproduct_urlが複数ある場合は、
    scraped_date、updated_at、idの順で
    最新の1件だけを残す。

    product_urlが空の場合は重複扱いせず、
    各レコードをそのまま取得する。
    """
    safe_table_name = validate_identifier(
        PRODUCT_TABLE_NAME
    )

    sql = f"""
        WITH ranked_products AS (
            SELECT
                id,
                sku,
                shop_name,
                shop_product_id,
                machine_name,
                master_machine_id,
                master_machine_name,
                master_machine_maker,
                price,
                product_url,
                image_url,
                status,
                scraped_date,
                created_at,
                updated_at,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        CAST(master_machine_id AS TEXT),
                        CASE
                            WHEN product_url IS NOT NULL
                             AND TRIM(product_url) != ''
                            THEN TRIM(product_url)

                            ELSE
                                '__NO_URL__'
                                || CAST(id AS TEXT)
                        END

                    ORDER BY
                        CASE
                            WHEN scraped_date IS NULL
                                THEN 1
                            ELSE 0
                        END,

                        scraped_date DESC,

                        CASE
                            WHEN updated_at IS NULL
                                THEN 1
                            ELSE 0
                        END,

                        updated_at DESC,
                        id DESC
                ) AS row_number

            FROM {safe_table_name}

            WHERE master_machine_id IS NOT NULL
              AND TRIM(
                    CAST(master_machine_id AS TEXT)
                  ) != ''
              AND price IS NOT NULL
              AND price > 0
        )

        SELECT
            id,
            sku,
            shop_name,
            shop_product_id,
            machine_name,
            master_machine_id,
            master_machine_name,
            master_machine_maker,
            price,
            product_url,
            image_url,
            status,
            scraped_date,
            created_at,
            updated_at

        FROM ranked_products

        WHERE row_number = 1

        ORDER BY
            CAST(master_machine_id AS TEXT) ASC,
            price ASC,

            CASE
                WHEN scraped_date IS NULL
                    THEN 1
                ELSE 0
            END,

            scraped_date DESC,
            id DESC
    """

    rows = connection.execute(
        sql
    ).fetchall()

    products_by_machine: dict[
        str,
        list[dict[str, Any]]
    ] = defaultdict(list)

    for row in rows:
        product = row_to_dict(
            row
        )

        machine_key = (
            normalize_machine_lookup_key(
                product.get(
                    "master_machine_id"
                )
            )
        )

        if not machine_key:
            continue

        products_by_machine[
            machine_key
        ].append(
            product
        )

    return dict(
        products_by_machine
    )


def get_all_price_history_by_machine(
    connection: sqlite3.Connection,
    days: int = PRICE_HISTORY_DAYS,
) -> dict[str, list[dict[str, Any]]]:
    """
    全機種の価格履歴を1回のSQLで取得し、
    master_machine_idごとの辞書にまとめる。

    各機種について最新日付順で最大days件を取得し、
    テンプレートへ渡す際は古い日付順に並べる。
    """
    safe_table_name = validate_identifier(
        PRICE_HISTORY_TABLE_NAME
    )

    try:
        limit_value = int(
            days
        )
    except (TypeError, ValueError):
        limit_value = (
            PRICE_HISTORY_DAYS
        )

    if limit_value <= 0:
        limit_value = (
            PRICE_HISTORY_DAYS
        )

    sql = f"""
        WITH ranked_history AS (
            SELECT
                id,
                master_machine_id,
                record_date,
                min_price,
                avg_price,
                median_price,
                max_price,
                latest_price,
                price_count,
                shop_count,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        CAST(master_machine_id AS TEXT)

                    ORDER BY
                        record_date DESC,
                        id DESC
                ) AS row_number

            FROM {safe_table_name}

            WHERE master_machine_id IS NOT NULL
              AND TRIM(
                    CAST(master_machine_id AS TEXT)
                  ) != ''
        )

        SELECT
            master_machine_id,
            record_date,
            min_price,
            avg_price,
            median_price,
            max_price,
            latest_price,
            price_count,
            shop_count

        FROM ranked_history

        WHERE row_number <= ?

        ORDER BY
            CAST(master_machine_id AS TEXT) ASC,
            record_date ASC,
            row_number DESC
    """

    rows = connection.execute(
        sql,
        (
            limit_value,
        ),
    ).fetchall()

    history_by_machine: dict[
        str,
        list[dict[str, Any]]
    ] = defaultdict(list)

    for row in rows:
        history = row_to_dict(
            row
        )

        machine_key = (
            normalize_machine_lookup_key(
                history.get(
                    "master_machine_id"
                )
            )
        )

        if not machine_key:
            continue

        history.pop(
            "master_machine_id",
            None,
        )

        history_by_machine[
            machine_key
        ].append(
            history
        )

    return dict(
        history_by_machine
    )


def get_all_time_price_range_by_machine(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, int | None]]:
    """
    price_historyの全期間を対象に、
    各機種の過去最安価格・過去最高価格を取得する。

    過去最安:
        全期間のmin_priceの最小値

    過去最高:
        全期間のmin_priceの最大値

    PRICE_HISTORY_DAYSの制限は受けない。
    """
    safe_table_name = (
        validate_identifier(
            PRICE_HISTORY_TABLE_NAME
        )
    )

    sql = f"""
        SELECT
            master_machine_id,

            MIN(
                CASE
                    WHEN min_price > 0
                    THEN min_price
                    ELSE NULL
                END
            ) AS all_time_min_price,

            MAX(
                CASE
                    WHEN min_price > 0
                    THEN min_price
                    ELSE NULL
                END
            ) AS all_time_max_price

        FROM {safe_table_name}

        WHERE master_machine_id IS NOT NULL
          AND TRIM(
                CAST(master_machine_id AS TEXT)
              ) != ''

        GROUP BY
            CAST(master_machine_id AS TEXT)
    """

    rows = connection.execute(
        sql
    ).fetchall()

    price_range_by_machine: dict[
        str,
        dict[str, int | None]
    ] = {}

    for row in rows:
        price_range = row_to_dict(
            row
        )

        machine_key = (
            normalize_machine_lookup_key(
                price_range.get(
                    "master_machine_id"
                )
            )
        )

        if not machine_key:
            continue

        all_time_min_price = (
            normalize_related_price(
                price_range.get(
                    "all_time_min_price"
                )
            )
        )

        all_time_max_price = (
            normalize_related_price(
                price_range.get(
                    "all_time_max_price"
                )
            )
        )

        price_range_by_machine[
            machine_key
        ] = {
            "all_time_min_price": (
                all_time_min_price
            ),
            "all_time_max_price": (
                all_time_max_price
            ),
        }

    return price_range_by_machine


# ==================================================
# 価格履歴コンテンツ用データ作成
# ==================================================

def normalize_history_date(
    value: Any,
) -> date | None:
    """
    price_historyのrecord_dateをdateへ変換する。
    """
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    value_text = str(
        value
    ).strip()

    if not value_text:
        return None

    try:
        return datetime.fromisoformat(
            value_text
        ).date()
    except ValueError:
        pass

    for date_format in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(
                value_text,
                date_format,
            ).date()
        except ValueError:
            continue

    return None


def normalize_history_price(
    value: Any,
) -> int | None:
    """
    価格履歴の価格を正の整数へ変換する。
    """
    if value is None:
        return None

    try:
        price = int(
            float(value)
        )
    except (TypeError, ValueError):
        return None

    if price <= 0:
        return None

    return price


def get_latest_valid_history_record(
    price_history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    日付と最安価格が有効な最新履歴を取得する。
    """
    for history in reversed(
        price_history
    ):
        record_date = (
            normalize_history_date(
                history.get(
                    "record_date"
                )
            )
        )

        min_price = (
            normalize_history_price(
                history.get(
                    "min_price"
                )
            )
        )

        if (
            record_date is None
            or min_price is None
        ):
            continue

        return history

    return None


def find_history_record_by_date(
    price_history: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    """
    指定日と一致する価格履歴を取得する。

    別日の価格で代用せず、
    対象日の履歴がない場合はNoneを返す。
    """
    for history in reversed(
        price_history
    ):
        record_date = (
            normalize_history_date(
                history.get(
                    "record_date"
                )
            )
        )

        if record_date == target_date:
            return history

    return None


def calculate_price_change(
    current_price: Any,
    previous_price: Any,
) -> tuple[
    int | None,
    float | None,
]:
    """
    現在価格と過去価格から、
    差額と変動率を計算する。
    """
    current_value = (
        normalize_history_price(
            current_price
        )
    )

    previous_value = (
        normalize_history_price(
            previous_price
        )
    )

    if (
        current_value is None
        or previous_value is None
    ):
        return (
            None,
            None,
        )

    change_amount = (
        current_value
        - previous_value
    )

    change_rate = (
        change_amount
        / previous_value
        * 100
    )

    return (
        change_amount,
        change_rate,
    )


def calculate_90_day_statistics(
    price_history: list[dict[str, Any]],
) -> tuple[
    int | None,
    date | None,
    int | None,
    date | None,
    int | None,
    int,
]:
    """
    price_history内の最安価格を使って、
    最大90日分の価格統計を計算する。
    """
    valid_history: list[
        tuple[date, int]
    ] = []

    for history in price_history:
        record_date = (
            normalize_history_date(
                history.get(
                    "record_date"
                )
            )
        )

        min_price = (
            normalize_history_price(
                history.get(
                    "min_price"
                )
            )
        )

        if (
            record_date is None
            or min_price is None
        ):
            continue

        valid_history.append(
            (
                record_date,
                min_price,
            )
        )

    if not valid_history:
        return (
            None,
            None,
            None,
            None,
            None,
            0,
        )

    period_min_price = min(
        price
        for _, price
        in valid_history
    )

    period_max_price = max(
        price
        for _, price
        in valid_history
    )

    period_min_date = max(
        record_date
        for (
            record_date,
            price,
        ) in valid_history
        if price
        == period_min_price
    )

    period_max_date = max(
        record_date
        for (
            record_date,
            price,
        ) in valid_history
        if price
        == period_max_price
    )

    period_avg_price = round(
        sum(
            price
            for _, price
            in valid_history
        )
        / len(valid_history)
    )

    return (
        period_min_price,
        period_min_date,
        period_max_price,
        period_max_date,
        period_avg_price,
        len(valid_history),
    )


def calculate_price_position(
    current_price: Any,
    period_min_price: Any,
    period_max_price: Any,
) -> tuple[
    float | None,
    str,
]:
    """
    現在価格が90日価格帯の
    どの位置にあるかを計算する。
    """
    current_value = (
        normalize_history_price(
            current_price
        )
    )

    min_value = (
        normalize_history_price(
            period_min_price
        )
    )

    max_value = (
        normalize_history_price(
            period_max_price
        )
    )

    if (
        current_value is None
        or min_value is None
        or max_value is None
    ):
        return (
            None,
            "",
        )

    if max_value == min_value:
        return (
            50.0,
            "横ばい",
        )

    position = (
        current_value
        - min_value
    ) / (
        max_value
        - min_value
    ) * 100

    position = max(
        0.0,
        min(
            100.0,
            position,
        ),
    )

    if position <= 33.333333:
        level = "安値圏"

    elif position <= 66.666666:
        level = "中間圏"

    else:
        level = "高値圏"

    return (
        position,
        level,
    )


def build_recent_price_changes(
    price_history: list[dict[str, Any]],
    limit: int = 7,
) -> list[dict[str, Any]]:
    """
    最近の日別最安価格と前日比を作成する。

    前日データが存在しない日は、
    差額・変動率をNoneにする。

    表示順は新しい日付から古い日付。
    """
    history_by_date: dict[
        date,
        int,
    ] = {}

    for history in price_history:
        record_date = (
            normalize_history_date(
                history.get(
                    "record_date"
                )
            )
        )

        min_price = (
            normalize_history_price(
                history.get(
                    "min_price"
                )
            )
        )

        if (
            record_date is None
            or min_price is None
        ):
            continue

        history_by_date[
            record_date
        ] = min_price

    valid_history = sorted(
        history_by_date.items(),
        key=lambda item: item[0],
    )

    if not valid_history:
        return []

    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        limit_value = 7

    if limit_value <= 0:
        return []

    recent_rows: list[
        dict[str, Any]
    ] = []

    for (
        record_date,
        min_price,
    ) in reversed(
        valid_history[
            -limit_value:
        ]
    ):
        previous_date = (
            record_date
            - timedelta(days=1)
        )

        previous_price = (
            history_by_date.get(
                previous_date
            )
        )

        (
            change_amount,
            change_rate,
        ) = calculate_price_change(
            current_price=min_price,
            previous_price=previous_price,
        )

        recent_rows.append(
            {
                "record_date": (
                    record_date
                ),
                "min_price": (
                    min_price
                ),
                "previous_price": (
                    previous_price
                ),
                "change_amount": (
                    change_amount
                ),
                "change_rate": (
                    change_rate
                ),
            }
        )

    return recent_rows


# ==================================================
# 価格相場解説文作成
# ==================================================

def build_price_market_commentary(
    machine_name: str,
    current_price: Any,
    price_7_days_ago: Any,
    price_change_7d: int | None,
    price_change_rate_7d: float | None,
    price_30_days_ago: Any,
    price_change_30d: int | None,
    price_change_rate_30d: float | None,
    period_90_min_price: Any,
    period_90_max_price: Any,
    period_90_avg_price: Any,
    period_90_days: int,
    price_level_label: str,
) -> list[str]:
    """
    既存の価格履歴集計結果から、
    機種詳細ページへ表示する
    価格相場の解説文を作成する。

    推測や主観的な「買い時」判定は行わず、
    現在価格・過去比較・90日統計・価格水準の
    事実だけを文章化する。
    """
    commentary: list[str] = []

    normalized_current_price = (
        normalize_history_price(
            current_price
        )
    )

    normalized_7_days_ago = (
        normalize_history_price(
            price_7_days_ago
        )
    )

    normalized_30_days_ago = (
        normalize_history_price(
            price_30_days_ago
        )
    )

    normalized_90_min_price = (
        normalize_history_price(
            period_90_min_price
        )
    )

    normalized_90_max_price = (
        normalize_history_price(
            period_90_max_price
        )
    )

    normalized_90_avg_price = (
        normalize_history_price(
            period_90_avg_price
        )
    )

    clean_machine_name = str(
        machine_name
        or ""
    ).strip()

    # ----------------------------------------------
    # 現在価格
    # ----------------------------------------------
    if normalized_current_price is not None:
        if clean_machine_name:
            commentary.append(
                f"{clean_machine_name}の中古実機は、"
                f"現在の最安価格が"
                f"{normalized_current_price:,}円です。"
            )
        else:
            commentary.append(
                "現在の中古実機の最安価格は"
                f"{normalized_current_price:,}円です。"
            )

    # ----------------------------------------------
    # 7日前との比較
    # ----------------------------------------------
    if (
        normalized_7_days_ago is not None
        and price_change_7d is not None
        and price_change_rate_7d is not None
    ):
        change_amount = abs(
            int(price_change_7d)
        )

        change_rate = abs(
            float(price_change_rate_7d)
        )

        if price_change_7d < 0:
            commentary.append(
                "7日前の最安価格"
                f"{normalized_7_days_ago:,}円と比べて、"
                f"{change_amount:,}円"
                f"（{change_rate:.1f}%）"
                "下落しています。"
            )

        elif price_change_7d > 0:
            commentary.append(
                "7日前の最安価格"
                f"{normalized_7_days_ago:,}円と比べて、"
                f"{change_amount:,}円"
                f"（{change_rate:.1f}%）"
                "上昇しています。"
            )

        else:
            commentary.append(
                "7日前の最安価格"
                f"{normalized_7_days_ago:,}円から"
                "変動していません。"
            )

    # ----------------------------------------------
    # 30日前との比較
    # ----------------------------------------------
    if (
        normalized_30_days_ago is not None
        and price_change_30d is not None
        and price_change_rate_30d is not None
    ):
        change_amount = abs(
            int(price_change_30d)
        )

        change_rate = abs(
            float(price_change_rate_30d)
        )

        if price_change_30d < 0:
            commentary.append(
                "30日前の最安価格"
                f"{normalized_30_days_ago:,}円と比べて、"
                f"{change_amount:,}円"
                f"（{change_rate:.1f}%）"
                "下落しています。"
            )

        elif price_change_30d > 0:
            commentary.append(
                "30日前の最安価格"
                f"{normalized_30_days_ago:,}円と比べて、"
                f"{change_amount:,}円"
                f"（{change_rate:.1f}%）"
                "上昇しています。"
            )

        else:
            commentary.append(
                "30日前の最安価格"
                f"{normalized_30_days_ago:,}円から"
                "変動していません。"
            )

    # ----------------------------------------------
    # 90日価格統計
    # ----------------------------------------------
    if (
        period_90_days > 0
        and normalized_90_min_price is not None
        and normalized_90_max_price is not None
    ):
        if normalized_90_avg_price is not None:
            commentary.append(
                f"直近{period_90_days:,}日間の"
                "日次最安価格は、"
                f"{normalized_90_min_price:,}円から"
                f"{normalized_90_max_price:,}円の範囲で推移し、"
                f"平均は{normalized_90_avg_price:,}円です。"
            )
        else:
            commentary.append(
                f"直近{period_90_days:,}日間の"
                "日次最安価格は、"
                f"{normalized_90_min_price:,}円から"
                f"{normalized_90_max_price:,}円の範囲で"
                "推移しています。"
            )

    # ----------------------------------------------
    # 現在の価格水準
    # ----------------------------------------------
    if (
        normalized_current_price is not None
        and price_level_label
        and period_90_days > 0
    ):
        commentary.append(
            "現在の最安価格は、"
            f"直近{period_90_days:,}日間の価格帯では"
            f"「{price_level_label}」に位置しています。"
        )

    return commentary


# ==================================================
# SEO用テキスト作成
# ==================================================

def format_price_for_seo(
    value: Any,
) -> str:
    """
    SEO文面で使用する価格を整形する。
    """
    if value is None:
        return ""

    try:
        price = int(
            float(value)
        )
    except (TypeError, ValueError):
        return ""

    if price <= 0:
        return ""

    return (
        f"{price:,}円"
    )


def build_machine_meta_description(
    machine: dict[str, Any],
    product_count: int,
) -> str:
    """
    機種詳細ページ用の
    meta descriptionを作成する。
    """
    machine_name = str(
        machine.get(
            "master_machine_name"
        )
        or ""
    ).strip()

    maker_name = str(
        machine.get(
            "master_machine_maker"
        )
        or ""
    ).strip()

    min_price = (
        format_price_for_seo(
            machine.get(
                "min_price"
            )
        )
    )

    avg_price = (
        format_price_for_seo(
            machine.get(
                "avg_price"
            )
        )
    )

    description_parts: list[
        str
    ] = []

    if maker_name:
        description_parts.append(
            f"{maker_name}「{machine_name}」"
        )
    else:
        description_parts.append(
            f"「{machine_name}」"
        )

    if min_price:
        description_parts.append(
            f"中古実機の最安値は{min_price}"
        )

    if avg_price:
        description_parts.append(
            f"平均価格は{avg_price}"
        )

    if product_count > 0:
        description_parts.append(
            f"現在{product_count:,}件の出品情報を掲載"
        )

    if len(
        description_parts
    ) == 1:
        description_parts.append(
            "中古価格、相場、出品情報、価格推移を確認できます"
        )
    else:
        description_parts.append(
            "価格推移や販売店ごとの出品情報を比較できます"
        )

    return (
        "。".join(
            description_parts
        )
        + "。"
    )


# ==================================================
# テンプレート用データ作成
# ==================================================

def build_machine_page_context(
    machine: dict[str, Any],
    products: list[dict[str, Any]],
    price_history: list[dict[str, Any]],

    # 既存: 同メーカー
    related_machines: list[
        dict[str, Any]
    ],

    # 新規: 同シリーズ
    series_related_machines: list[
        dict[str, Any]
    ],

    # 新規: 価格が近い
    near_price_machines: list[
        dict[str, Any]
    ],

    # 新規: 同タイプ
    type_related_machines: list[
        dict[str, Any]
    ],

    all_time_price_range: dict[
        str,
        int | None,
    ],

    generated_at: datetime,
) -> dict[str, Any]:
    """
    machine_detail.htmlへ渡す
    テンプレート変数を作成する。
    """
    lowest_product = (
        products[0]
        if products
        else None
    )

    page_updated_at = (
        machine.get(
            "latest_scraped_at"
        )
        or machine.get(
            "last_seen"
        )
        or machine.get(
            "updated_at"
        )
        or generated_at
    )

    machine_name = str(
        machine.get(
            "master_machine_name"
        )
        or ""
    ).strip()

    machine_file_id = (
        normalize_machine_id(
            machine.get(
                "master_machine_id"
            )
        )
    )

    product_count = len(
        products
    )

    # ----------------------------------------------
    # 全期間の過去最安・過去最高
    # ----------------------------------------------

    all_time_min_price = (
        all_time_price_range.get(
            "all_time_min_price"
        )
    )

    all_time_max_price = (
        all_time_price_range.get(
            "all_time_max_price"
        )
    )


    # ----------------------------------------------
    # 価格履歴から追加コンテンツ用データを作成
    # ----------------------------------------------

    latest_history = (
        get_latest_valid_history_record(
            price_history
        )
    )

    if latest_history:
        latest_history_date = (
            normalize_history_date(
                latest_history.get(
                    "record_date"
                )
            )
        )

        current_history_min_price = (
            normalize_history_price(
                latest_history.get(
                    "min_price"
                )
            )
        )

    else:
        latest_history_date = None

        current_history_min_price = (
            None
        )


    previous_day_price = None
    price_7_days_ago = None
    price_30_days_ago = None


    if latest_history_date is not None:

        previous_day_history = (
            find_history_record_by_date(
                price_history=price_history,
                target_date=(
                    latest_history_date
                    - timedelta(
                        days=1
                    )
                ),
            )
        )

        history_7_days_ago = (
            find_history_record_by_date(
                price_history=price_history,
                target_date=(
                    latest_history_date
                    - timedelta(
                        days=7
                    )
                ),
            )
        )

        history_30_days_ago = (
            find_history_record_by_date(
                price_history=price_history,
                target_date=(
                    latest_history_date
                    - timedelta(
                        days=30
                    )
                ),
            )
        )


        if previous_day_history:
            previous_day_price = (
                normalize_history_price(
                    previous_day_history.get(
                        "min_price"
                    )
                )
            )


        if history_7_days_ago:
            price_7_days_ago = (
                normalize_history_price(
                    history_7_days_ago.get(
                        "min_price"
                    )
                )
            )


        if history_30_days_ago:
            price_30_days_ago = (
                normalize_history_price(
                    history_30_days_ago.get(
                        "min_price"
                    )
                )
            )


    (
        price_change_1d,
        price_change_rate_1d,
    ) = calculate_price_change(
        current_price=(
            current_history_min_price
        ),
        previous_price=(
            previous_day_price
        ),
    )


    (
        price_change_7d,
        price_change_rate_7d,
    ) = calculate_price_change(
        current_price=(
            current_history_min_price
        ),
        previous_price=(
            price_7_days_ago
        ),
    )


    (
        price_change_30d,
        price_change_rate_30d,
    ) = calculate_price_change(
        current_price=(
            current_history_min_price
        ),
        previous_price=(
            price_30_days_ago
        ),
    )


    (
        period_90_min_price,
        period_90_min_date,
        period_90_max_price,
        period_90_max_date,
        period_90_avg_price,
        period_90_days,
    ) = calculate_90_day_statistics(
        price_history
    )


    (
        price_position_percent,
        price_level_label,
    ) = calculate_price_position(
        current_price=(
            current_history_min_price
        ),
        period_min_price=(
            period_90_min_price
        ),
        period_max_price=(
            period_90_max_price
        ),
    )


    recent_price_changes = (
        build_recent_price_changes(
            price_history=(
                price_history
            ),
            limit=30,
        )
    )


    # ----------------------------------------------
    # 価格相場の文章による解説
    # ----------------------------------------------

    price_market_commentary = (
        build_price_market_commentary(
            machine_name=(
                machine_name
            ),
            current_price=(
                current_history_min_price
                if current_history_min_price is not None
                else machine.get(
                    "min_price"
                )
            ),
            price_7_days_ago=(
                price_7_days_ago
            ),
            price_change_7d=(
                price_change_7d
            ),
            price_change_rate_7d=(
                price_change_rate_7d
            ),
            price_30_days_ago=(
                price_30_days_ago
            ),
            price_change_30d=(
                price_change_30d
            ),
            price_change_rate_30d=(
                price_change_rate_30d
            ),
            period_90_min_price=(
                period_90_min_price
            ),
            period_90_max_price=(
                period_90_max_price
            ),
            period_90_avg_price=(
                period_90_avg_price
            ),
            period_90_days=(
                period_90_days
            ),
            price_level_label=(
                price_level_label
            ),
        )
    )


    meta_description = (
        build_machine_meta_description(
            machine=machine,
            product_count=(
                product_count
            ),
        )
    )


    static_machine_image_path = (
        Path(PROJECT_ROOT)
        / "static"
        / "img"
        / "machines"
        / f"{machine_file_id}.webp"
    )


    if (
        static_machine_image_path.is_file()
    ):
        machine_image_path = (
            f"../img/machines/"
            f"{machine_file_id}.webp"
        )

        machine_image_og_path = (
            f"/img/machines/"
            f"{machine_file_id}.webp"
        )

    else:
        machine_image_path = (
            "../img/no_image.webp"
        )

        machine_image_og_path = (
            "/img/no_image.webp"
        )


    canonical_path = (
        f"/machines/"
        f"{machine_file_id}.html"
    )

    canonical_url = (
        f"{SITE_URL.rstrip('/')}"
        f"{canonical_path}"
    )


    share_title = (
        f"{machine_name}の中古実機価格・相場"
        f"｜{SITE_NAME}"
    )

    share_text = (
        f"{machine_name}の中古実機価格、"
        "最安値、平均価格、出品情報を掲載しています。"
    )


    seo = build_seo_data(
        title=(
            f"{machine_name}の中古実機価格・相場"
        ),
        description=(
            meta_description
        ),
        canonical_path=(
            canonical_path
        ),
        robots=(
            "index,follow"
        ),
        og_image=(
            machine_image_og_path
        ),
        og_type=(
            "article"
        ),
        og_image_alt=(
            f"{machine_name}の実機画像"
        ),
    )


    return {
        # SEO情報
        **seo,

        # SNSシェア用
        "share_url": (
            canonical_url
        ),
        "share_title": (
            share_title
        ),
        "share_text": (
            share_text
        ),

        # 共通テンプレート用
        "site_description": (
            SITE_DESCRIPTION
        ),
        "current_year": (
            generated_at.year
        ),
        "is_top_page": (
            False
        ),

        # パンくずリスト
        "breadcrumbs": (
            create_machine_detail_breadcrumbs(
                machine_name
            )
        ),

        # output/machines/*.htmlから見た相対パス
        "root_prefix": (
            "../"
        ),
        "asset_prefix": (
            "../"
        ),

        # 機種詳細ページ用
        "machine": (
            machine
        ),
        "machine_image_path": (
            machine_image_path
        ),
        "products": (
            products
        ),
        "lowest_product": (
            lowest_product
        ),
        "product_count": (
            product_count
        ),

        # ------------------------------------------
        # 関連機種
        # ------------------------------------------

        # 同メーカー
        "related_machines": (
            related_machines
        ),
        "related_machine_count": len(
            related_machines
        ),

        # 同シリーズ
        "series_related_machines": (
            series_related_machines
        ),
        "series_related_machine_count": len(
            series_related_machines
        ),

        # 価格が近い機種
        "near_price_machines": (
            near_price_machines
        ),
        "near_price_machine_count": len(
            near_price_machines
        ),

        # 同タイプ
        "type_related_machines": (
            type_related_machines
        ),
        "type_related_machine_count": len(
            type_related_machines
        ),

        # ------------------------------------------
        # 価格推移
        # ------------------------------------------

        "price_history": (
            price_history
        ),

        # 全期間価格
        "all_time_min_price": (
            all_time_min_price
        ),
        "all_time_max_price": (
            all_time_max_price
        ),

        # 価格比較
        "latest_history_date": (
            latest_history_date
        ),
        "current_history_min_price": (
            current_history_min_price
        ),
        "previous_day_price": (
            previous_day_price
        ),
        "price_7_days_ago": (
            price_7_days_ago
        ),
        "price_30_days_ago": (
            price_30_days_ago
        ),
        "price_change_1d": (
            price_change_1d
        ),
        "price_change_rate_1d": (
            price_change_rate_1d
        ),
        "price_change_7d": (
            price_change_7d
        ),
        "price_change_rate_7d": (
            price_change_rate_7d
        ),
        "price_change_30d": (
            price_change_30d
        ),
        "price_change_rate_30d": (
            price_change_rate_30d
        ),

        # 90日価格統計
        "period_90_min_price": (
            period_90_min_price
        ),
        "period_90_min_date": (
            period_90_min_date
        ),
        "period_90_max_price": (
            period_90_max_price
        ),
        "period_90_max_date": (
            period_90_max_date
        ),
        "period_90_avg_price": (
            period_90_avg_price
        ),
        "period_90_days": (
            period_90_days
        ),

        # 現在の価格水準
        "price_position_percent": (
            price_position_percent
        ),
        "price_level_label": (
            price_level_label
        ),

        # 最近の日別価格変動
        "recent_price_changes": (
            recent_price_changes
        ),

        # 価格相場の文章による解説
        "price_market_commentary": (
            price_market_commentary
        ),

        # 更新日時
        "generated_at": (
            generated_at
        ),
        "updated_at": (
            page_updated_at
        ),
    }


# ==================================================
# 静的ファイルコピー
# ==================================================

def copy_machine_detail_static_files() -> None:
    """
    共通ファイルと機種詳細ページ専用ファイルを
    staticからoutputへコピーする。
    """
    copy_common_static_files(
        project_root_dir=(
            PROJECT_ROOT
        ),
        output_root_dir=(
            OUTPUT_DIR
        ),
    )

    copy_static_files(
        project_root_dir=(
            PROJECT_ROOT
        ),
        output_root_dir=(
            OUTPUT_DIR
        ),
        relative_paths=(
            "css/machine_detail.css",
            "js/machine_detail.js",
        ),
    )


# ==================================================
# HTML生成
# ==================================================

def generate_machine_pages() -> None:
    """
    product_summaryに登録された全機種について、
    機種詳細ページを生成する。

    出力例:
        output/machines/101.html
    """
    generated_at = (
        datetime.now()
    )

    OUTPUT_MACHINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy_machine_detail_static_files()


    environment = (
        create_jinja_environment(
            template_dir=(
                TEMPLATE_DIR
            ),
            site_name=(
                SITE_NAME
            ),
            site_description=(
                SITE_DESCRIPTION
            ),
            root_prefix=(
                ROOT_PREFIX
            ),
            asset_prefix=(
                ASSET_PREFIX
            ),
        )
    )


    try:
        template = (
            environment.get_template(
                TEMPLATE_FILE_NAME
            )
        )

    except TemplateNotFound as error:
        raise FileNotFoundError(
            "Jinja2テンプレートが見つかりません: "
            f"{error.name}"
        ) from error


    generated_count = 0
    error_count = 0
    product_total_count = 0


    with connect_database(
        DB_PATH
    ) as connection:

        check_tables_exist(
            connection,
            (
                SUMMARY_TABLE_NAME,
                PRODUCT_TABLE_NAME,
                PRICE_HISTORY_TABLE_NAME,
            ),
        )


        machines = get_machines(
            connection
        )


        # ==========================================
        # 関連機種インデックス
        # ==========================================

        # 同メーカー
        related_machine_index = (
            build_related_machine_index(
                machines
            )
        )

        # 同シリーズ
        series_machine_index = (
            build_series_machine_index(
                machines
            )
        )

        # 同タイプ
        type_machine_index = (
            build_type_machine_index(
                machines
            )
        )


        # ==========================================
        # 商品・価格履歴
        # ==========================================

        products_by_machine = (
            get_all_products_by_machine(
                connection
            )
        )


        history_by_machine = (
            get_all_price_history_by_machine(
                connection=connection,
                days=(
                    PRICE_HISTORY_DAYS
                ),
            )
        )


        # ==========================================
        # 全期間価格
        # ==========================================

        all_time_price_range_by_machine = (
            get_all_time_price_range_by_machine(
                connection
            )
        )


        print(
            "=" * 70
        )

        print(
            "使用テンプレート: "
            f"{Path(TEMPLATE_DIR) / TEMPLATE_FILE_NAME}"
        )

        print(
            "ページ生成対象: "
            f"{len(machines):,}機種"
        )

        print(
            "=" * 70
        )


        for machine in machines:

            master_machine_id = (
                machine.get(
                    "master_machine_id"
                )
            )

            machine_file_id = (
                normalize_machine_id(
                    master_machine_id
                )
            )


            if not machine_file_id:
                error_count += 1

                print(
                    "[スキップ] "
                    "master_machine_idが空です。"
                )

                continue


            try:
                machine_lookup_key = (
                    normalize_machine_lookup_key(
                        master_machine_id
                    )
                )


                # ==================================
                # 商品
                # ==================================

                products = (
                    products_by_machine.get(
                        machine_lookup_key,
                        [],
                    )
                )


                # ==================================
                # 価格履歴
                # ==================================

                price_history = (
                    history_by_machine.get(
                        machine_lookup_key,
                        [],
                    )
                )


                # ==================================
                # 全期間価格
                # ==================================

                all_time_price_range = (
                    all_time_price_range_by_machine.get(
                        machine_lookup_key,
                        {
                            "all_time_min_price": None,
                            "all_time_max_price": None,
                        },
                    )
                )


                # ==================================
                # 同シリーズ関連機種
                # ==================================

                series_related_machines = (
                    get_series_related_machines(
                        machine=machine,
                        series_machine_index=(
                            series_machine_index
                        ),
                        limit=(
                            RELATED_SERIES_LIMIT
                        ),
                    )
                )


                # ==================================
                # 価格が近い機種
                # ==================================

                near_price_machines = (
                    get_near_price_machines(
                        machine=machine,
                        machines=machines,
                        limit=(
                            NEAR_PRICE_MACHINE_LIMIT
                        ),
                    )
                )


                # ==================================
                # 同タイプ関連機種
                # ==================================

                type_related_machines = (
                    get_type_related_machines(
                        machine=machine,
                        type_machine_index=(
                            type_machine_index
                        ),
                        limit=(
                            RELATED_TYPE_LIMIT
                        ),
                    )
                )


                # ==================================
                # 同メーカー関連機種
                # ==================================

                related_machines = (
                    get_related_machines(
                        machine=machine,
                        related_machine_index=(
                            related_machine_index
                        ),
                        limit=(
                            RELATED_MACHINE_LIMIT
                        ),
                    )
                )


                # ==================================
                # テンプレートcontext
                # ==================================

                context = (
                    build_machine_page_context(
                        machine=(
                            machine
                        ),
                        products=(
                            products
                        ),
                        price_history=(
                            price_history
                        ),

                        related_machines=(
                            related_machines
                        ),

                        series_related_machines=(
                            series_related_machines
                        ),

                        near_price_machines=(
                            near_price_machines
                        ),

                        type_related_machines=(
                            type_related_machines
                        ),

                        all_time_price_range=(
                            all_time_price_range
                        ),

                        generated_at=(
                            generated_at
                        ),
                    )
                )


                html = template.render(
                    **context
                )


                output_file_path = (
                    OUTPUT_MACHINE_DIR
                    / (
                        f"{machine_file_id}"
                        ".html"
                    )
                )


                output_file_path.write_text(
                    html,
                    encoding="utf-8",
                    newline="",
                )


                generated_count += 1

                product_total_count += (
                    len(
                        products
                    )
                )


                machine_image_file_path = (
                    Path(PROJECT_ROOT)
                    / "static"
                    / "img"
                    / "machines"
                    / (
                        f"{machine_file_id}"
                        ".webp"
                    )
                )


                image_status = (
                    "画像あり"
                    if (
                        machine_image_file_path.is_file()
                    )
                    else "画像なし"
                )


                print(
                    "[生成] "
                    f"{machine_file_id}.html"
                    " - "
                    f"{machine['master_machine_name']}"
                    " "
                    f"({len(products):,}商品 / "
                    f"履歴{len(price_history):,}日 / "
                    f"シリーズ{len(series_related_machines):,} / "
                    f"近似価格{len(near_price_machines):,} / "
                    f"同タイプ{len(type_related_machines):,} / "
                    f"同メーカー{len(related_machines):,} / "
                    f"{image_status})"
                )


            except Exception as error:
                error_count += 1

                print(
                    "[エラー] "
                    f"機種ID: "
                    f"{master_machine_id} "
                    f"{type(error).__name__}: "
                    f"{error}"
                )


        print(
            "=" * 70
        )


        print(
            "生成成功: "
            f"{generated_count:,}ページ"
        )


        print(
            "生成失敗・スキップ: "
            f"{error_count:,}ページ"
        )


        print(
            "取得商品合計: "
            f"{product_total_count:,}件"
        )


        print(
            "HTML出力先: "
            f"{OUTPUT_MACHINE_DIR}"
        )


        print(
            "詳細CSS出力先: "
            f"{Path(OUTPUT_DIR) / 'css' / 'machine_detail.css'}"
        )


        print(
            "詳細JS出力先: "
            f"{Path(OUTPUT_DIR) / 'js' / 'machine_detail.js'}"
        )


# ==================================================
# 実行
# ==================================================

def main() -> None:
    """
    機種詳細ページ生成処理を実行する。
    """
    try:
        generate_machine_pages()

        elapsed_time = (
            time.time()
            - START_TIME
        )

        print(
            "-" * 70
        )

        print(
            "全機種の詳細ページ生成が完了しました。"
        )

        print(
            "処理時間: "
            f"{elapsed_time:.2f}秒"
        )

        print(
            "-" * 70
        )


    except sqlite3.Error as error:
        print(
            "-" * 70
        )

        print(
            "SQLite処理でエラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


    except Exception as error:
        print(
            "-" * 70
        )

        print(
            "機種詳細ページ生成処理で"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


if __name__ == "__main__":
    main()