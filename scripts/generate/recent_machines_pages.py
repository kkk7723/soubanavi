import os
import re
import sqlite3
import sys
import time
import calendar

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
# テーブル設定
# ==================================================

MACHINE_MASTER_TABLE_NAME = (
    "machine_master"
)

PRODUCT_SUMMARY_TABLE_NAME = (
    SUMMARY_TABLE_NAME
)


# ==================================================
# 出力先設定
# ==================================================

RECENT_MACHINES_OUTPUT_DIR = os.path.join(
    OUTPUT_DIR,
    "recent-machines",
)


RECENT_MACHINES_OUTPUT_FILE_PATH = os.path.join(
    RECENT_MACHINES_OUTPUT_DIR,
    "index.html",
)


RECENT_MACHINES_PACHINKO_OUTPUT_FILE_PATH = (
    os.path.join(
        RECENT_MACHINES_OUTPUT_DIR,
        "pachinko",
        "index.html",
    )
)


RECENT_MACHINES_SLOT_OUTPUT_FILE_PATH = (
    os.path.join(
        RECENT_MACHINES_OUTPUT_DIR,
        "slot",
        "index.html",
    )
)


# ==================================================
# テンプレート・CSS設定
# ==================================================

RECENT_MACHINES_TEMPLATE_NAME = (
    "recent_machines/"
    "recent_machines_index.html"
)


RECENT_MACHINES_CSS_PATH = (
    "css/recent_machines_index.css"
)


# ==================================================
# ページ設定
# ==================================================

# 今日から何か月前までを対象にするか
RECENT_MONTHS = 6


RECENT_MACHINES_HEADING = (
    "最近導入された機種"
)


RECENT_MACHINES_PAGE_TITLE = (
    "最近導入された"
    "パチンコ・パチスロ実機"
)


RECENT_MACHINES_CANONICAL_PATH = (
    "/recent-machines/"
)


RECENT_MACHINES_PACHINKO_HEADING = (
    "最近導入されたパチンコ"
)


RECENT_MACHINES_PACHINKO_PAGE_TITLE = (
    "最近導入されたパチンコ実機"
)


RECENT_MACHINES_PACHINKO_CANONICAL_PATH = (
    "/recent-machines/pachinko/"
)


RECENT_MACHINES_SLOT_HEADING = (
    "最近導入されたパチスロ"
)


RECENT_MACHINES_SLOT_PAGE_TITLE = (
    "最近導入されたパチスロ実機"
)


RECENT_MACHINES_SLOT_CANONICAL_PATH = (
    "/recent-machines/slot/"
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

def clean_text(
    value: Any,
) -> str:
    """
    値を文字列へ変換し、
    前後の空白を除去する。

    Noneは空文字へ変換する。
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
    """
    master_machine_idを
    HTMLファイル名として使用できる
    文字列へ変換する。
    """
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
    """
    datetimeから指定した月数を引く。

    外部ライブラリを使用せず、
    暦上の月数で計算する。
    """
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

    target_month_last_day = calendar.monthrange(
        target_year,
        target_month,
    )[1]

    target_day = min(
        value.day,
        target_month_last_day,
    )

    return value.replace(
        year=target_year,
        month=target_month,
        day=target_day,
    )


# ==================================================
# カテゴリ判定
# ==================================================

def normalize_category_key(
    value: Any,
) -> str:
    """
    master_machine_categoryを
    カテゴリ判定用の文字列へ変換する。

    戻り値:
        pachinko
        slot
        other
    """
    category = clean_text(
        value
    ).casefold()

    category = re.sub(
        r"[\s　_-]+",
        "",
        category,
    )

    pachinko_values = {
        "pachi",
        "パチンコ",
        "ぱちんこ",
        "pachinko",
        "p",
    }

    slot_values = {
        "パチスロ",
        "ぱちすろ",
        "スロット",
        "すろっと",
        "slot",
        "slots",
        "s",
    }

    if category in pachinko_values:
        return "pachinko"

    if category in slot_values:
        return "slot"

    # 完全一致しない場合も、
    # 文字列中の語句から判定する
    if (
        "パチンコ" in category
        or "ぱちんこ" in category
        or "pachinko" in category
        or "pachi" in category
    ):
        return "pachinko"

    if (
        "パチスロ" in category
        or "ぱちすろ" in category
        or "スロット" in category
        or "すろっと" in category
        or "slot" in category
    ):
        return "slot"

    return "other"


def split_machines_by_category(
    machines: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    機種一覧を次の3種類へ分割する。

    ・パチンコ
    ・パチスロ
    ・カテゴリ判定不能
    """
    pachinko_machines: list[
        dict[str, Any]
    ] = []

    slot_machines: list[
        dict[str, Any]
    ] = []

    other_machines: list[
        dict[str, Any]
    ] = []

    for machine in machines:
        category_key = normalize_category_key(
            machine.get(
                "master_machine_category"
            )
        )

        machine_data = dict(
            machine
        )

        machine_data[
            "normalized_category_key"
        ] = category_key

        if category_key == "pachinko":
            pachinko_machines.append(
                machine_data
            )

        elif category_key == "slot":
            slot_machines.append(
                machine_data
            )

        else:
            other_machines.append(
                machine_data
            )

    return (
        pachinko_machines,
        slot_machines,
        other_machines,
    )


# ==================================================
# 導入日変換
# ==================================================

def parse_introduced_date(
    value: Any,
) -> datetime | None:
    """
    machine_masterの導入日を
    比較可能なdatetimeへ変換する。

    対応例:

    2026年06月08日(月)
    2026年06月08日（月）
    2026年06月08日
    2026年06月
    2026/06/08
    2026/06
    2026-06-08
    2026-06
    """
    text = clean_text(
        value
    )

    if not text:
        return None

    # 曜日表記を削除
    text = re.sub(
        r"[（(]\s*[月火水木金土日]\s*[）)]",
        "",
        text,
    ).strip()

    # 日付部分だけを抽出
    date_patterns = (
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}年\d{1,2}月",
        r"\d{4}/\d{1,2}/\d{1,2}",
        r"\d{4}/\d{1,2}",
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\d{4}-\d{1,2}",
    )

    extracted_text = None

    for pattern in date_patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            extracted_text = match.group(
                0
            )

            break

    if extracted_text:
        text = extracted_text

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
    """
    テンプレート表示用の導入日を作成する。

    元データに日まで存在する場合:
        YYYY年MM月DD日

    元データが年月だけの場合:
        YYYY年MM月
    """
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


def format_period_date(
    value: datetime,
) -> str:
    """
    対象期間表示用の日付を作成する。
    """
    return (
        f"{value.year}年"
        f"{value.month}月"
        f"{value.day}日"
    )


# ==================================================
# インデックス作成
# ==================================================

def create_recent_machines_indexes(
    connection: sqlite3.Connection,
) -> None:
    """
    最近導入された機種ページ生成で使用する
    インデックスを作成する。

    既に存在する場合は何もしない。
    """
    master_table_name = validate_identifier(
        MACHINE_MASTER_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{master_table_name}_introduced_date

        ON {master_table_name} (
            master_machine_introduced_date
        )
        """
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{master_table_name}_category

        ON {master_table_name} (
            master_machine_category
        )
        """
    )

    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS
            idx_{summary_table_name}_master_machine_id

        ON {summary_table_name} (
            master_machine_id
        )
        """
    )

    connection.commit()


# ==================================================
# DBデータ取得
# ==================================================

def get_all_machine_rows(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """
    machine_masterを起点にして、
    product_summaryの価格・出品情報を
    LEFT JOINで取得する。

    product_summaryに存在しない機種も
    取得対象になる。
    """
    master_table_name = validate_identifier(
        MACHINE_MASTER_TABLE_NAME
    )

    summary_table_name = validate_identifier(
        PRODUCT_SUMMARY_TABLE_NAME
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
            machine_master.master_machine_memo,
            machine_master.master_machine_introduced_date,
            machine_master.master_machine_game_system,
            machine_master.master_machine_pworld_url,
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
            product_summary.first_seen,
            product_summary.last_seen,
            product_summary.latest_scraped_at,

            COALESCE(
                product_summary.created_at,
                machine_master.created_at
            ) AS created_at,

            COALESCE(
                product_summary.updated_at,
                machine_master.updated_at
            ) AS updated_at

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
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
]:
    """
    machine_masterの機種から、
    導入日が指定月数以内の機種を取得する。

    将来導入予定の機種は除外する。
    """
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

    parsed_count = 0
    unparsed_count = 0
    future_count = 0
    old_count = 0
    invalid_machine_id_count = 0

    for machine in all_machines:
        original_introduced_date = machine.get(
            "master_machine_introduced_date"
        )

        introduced_date = parse_introduced_date(
            original_introduced_date
        )

        if introduced_date is None:
            unparsed_count += 1

            continue

        introduced_date = introduced_date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        parsed_count += 1

        # 将来導入予定は除外
        if introduced_date > today:
            future_count += 1

            continue

        # 指定月数より前は除外
        if introduced_date < period_start:
            old_count += 1

            continue

        machine_file_id = normalize_machine_id(
            machine.get(
                "master_machine_id"
            )
        )

        if not machine_file_id:
            invalid_machine_id_count += 1

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

        category_key = normalize_category_key(
            machine.get(
                "master_machine_category"
            )
        )

        machine_data = dict(
            machine
        )

        machine_data.update(
            {
                # 詳細ページ用ID
                "machine_file_id": (
                    machine_file_id
                ),

                # カテゴリ
                "normalized_category_key": (
                    category_key
                ),

                # 導入日
                "introduced_date_value": (
                    introduced_date
                ),

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

                # 件数
                "price_count": (
                    price_count
                ),

                "shop_count": (
                    shop_count
                ),

                # 在庫判定
                "has_products": (
                    price_count > 0
                ),
            }
        )

        recent_machines.append(
            machine_data
        )

    # 導入日が新しい順
    #
    # 同じ導入日の場合:
    # 1. 商品数が多い順
    # 2. ショップ数が多い順
    # 3. 機種IDが大きい順
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

    counts = {
        "all_count": len(
            all_machines
        ),

        "parsed_count": (
            parsed_count
        ),

        "unparsed_count": (
            unparsed_count
        ),

        "future_count": (
            future_count
        ),

        "old_count": (
            old_count
        ),

        "invalid_machine_id_count": (
            invalid_machine_id_count
        ),

        "recent_count": len(
            recent_machines
        ),
    }

    return (
        recent_machines,
        counts,
    )


# ==================================================
# ページ別機種データ作成
# ==================================================

def prepare_machines_for_page(
    machines: list[dict[str, Any]],
    root_prefix: str,
) -> list[dict[str, Any]]:
    """
    ページ階層に応じたURLを機種データへ追加する。

    総合ページ:
        root_prefix = "../"

    pachinko・slotページ:
        root_prefix = "../../"
    """
    page_machines: list[
        dict[str, Any]
    ] = []

    for machine in machines:
        machine_data = dict(
            machine
        )

        machine_file_id = clean_text(
            machine_data.get(
                "machine_file_id"
            )
        )

        machine_data[
            "detail_url"
        ] = (
            f"{root_prefix}"
            "machines/"
            f"{machine_file_id}.html"
        )

        page_machines.append(
            machine_data
        )

    return page_machines


# ==================================================
# 選択肢作成
# ==================================================

def get_unique_options(
    machines: list[dict[str, Any]],
    key: str,
) -> list[str]:
    """
    指定したキーから、
    重複のない選択肢一覧を作成する。
    """
    option_values: set[str] = set()

    for machine in machines:
        value = clean_text(
            machine.get(
                key
            )
        )

        if not value:
            continue

        option_values.add(
            value
        )

    return sorted(
        option_values,
        key=lambda value: (
            value.casefold()
        ),
    )


# ==================================================
# 更新日時取得
# ==================================================

def parse_datetime_value(
    value: Any,
) -> datetime | None:
    """
    DBの日時文字列をdatetimeへ変換する。
    """
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value.replace(
            tzinfo=None
        )

    value_text = clean_text(
        value
    )

    if not value_text:
        return None

    try:
        parsed_datetime = datetime.fromisoformat(
            value_text.replace(
                "Z",
                "+00:00",
            )
        )

        return parsed_datetime.replace(
            tzinfo=None
        )

    except ValueError:
        pass

    datetime_formats = (
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

    for datetime_format in datetime_formats:
        try:
            return datetime.strptime(
                value_text,
                datetime_format,
            )

        except ValueError:
            continue

    return None


def get_latest_updated_at(
    machines: list[dict[str, Any]],
    default_value: datetime,
) -> Any:
    """
    機種データ内で最も新しい更新日時を取得する。

    テンプレートにはDB内の元の値を返す。
    """
    latest_datetime: datetime | None = None
    latest_original_value: Any = None

    datetime_keys = (
        "latest_scraped_at",
        "last_seen",
        "updated_at",
    )

    for machine in machines:
        for key in datetime_keys:
            original_value = machine.get(
                key
            )

            parsed_datetime = parse_datetime_value(
                original_value
            )

            if parsed_datetime is None:
                continue

            if (
                latest_datetime is None
                or parsed_datetime
                > latest_datetime
            ):
                latest_datetime = parsed_datetime
                latest_original_value = (
                    original_value
                )

    if latest_original_value is None:
        return default_value

    return latest_original_value


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_recent_machines_meta_description(
    machine_count: int,
    in_stock_count: int,
    category_label: str = "",
) -> str:
    """
    最近導入された機種ページの
    meta descriptionを作成する。
    """
    if category_label:
        target_label = (
            f"{category_label}実機"
        )

    else:
        target_label = (
            "パチンコ・パチスロ実機"
        )

    if machine_count <= 0:
        return (
            f"過去{RECENT_MONTHS}か月以内に"
            f"導入された{target_label}を掲載する"
            "新機種情報ページです。"
        )

    return (
        f"過去{RECENT_MONTHS}か月以内に"
        f"導入された{target_label}を"
        f"{machine_count:,}機種掲載しています。"
        f"現在出品中は{in_stock_count:,}機種です。"
        "導入日、メーカー、機種タイプ、"
        "中古最安価格、商品数、ショップ数を"
        "確認できます。"
    )


def build_recent_machines_description(
    period_start: datetime,
    period_end: datetime,
    machine_count: int,
    category_label: str = "",
) -> str:
    """
    ページ内に表示する説明文を作成する。
    """
    period_start_display = format_period_date(
        period_start
    )

    period_end_display = format_period_date(
        period_end
    )

    if category_label:
        target_label = (
            f"{category_label}実機"
        )

    else:
        target_label = (
            "パチンコ・パチスロ実機"
        )

    if machine_count <= 0:
        return (
            f"{period_start_display}から"
            f"{period_end_display}までに"
            f"導入された{target_label}は"
            "登録されていません。"
        )

    return (
        f"{period_start_display}から"
        f"{period_end_display}までに導入された"
        f"{target_label}を"
        f"{machine_count:,}機種掲載しています。"
        "導入日の新しい順に表示しています。"
    )


# ==================================================
# パンくずリスト作成
# ==================================================

def create_recent_machines_breadcrumbs(
    page_type: str,
) -> list[dict[str, Any]]:
    """
    最近導入された機種ページ用の
    パンくずリストを作成する。

    page_type:
        all
        pachinko
        slot
    """
    if page_type == "pachinko":
        return [
            {
                "title": "トップ",
                "url": "../../",
            },
            {
                "title": (
                    RECENT_MACHINES_HEADING
                ),
                "url": "../",
            },
            {
                "title": "パチンコ",
                "url": None,
            },
        ]

    if page_type == "slot":
        return [
            {
                "title": "トップ",
                "url": "../../",
            },
            {
                "title": (
                    RECENT_MACHINES_HEADING
                ),
                "url": "../",
            },
            {
                "title": "パチスロ",
                "url": None,
            },
        ]

    return [
        {
            "title": "トップ",
            "url": "../",
        },
        {
            "title": (
                RECENT_MACHINES_HEADING
            ),
            "url": None,
        },
    ]


# ==================================================
# ページ切り替えリンク作成
# ==================================================

def create_recent_machines_category_links(
    page_type: str,
) -> list[dict[str, Any]]:
    """
    総合・パチンコ・パチスロページ間の
    切り替えリンクを作成する。
    """
    if page_type == "pachinko":
        return [
            {
                "key": "all",
                "label": "すべて",
                "url": "../",
                "is_current": False,
            },
            {
                "key": "pachinko",
                "label": "パチンコ",
                "url": None,
                "is_current": True,
            },
            {
                "key": "slot",
                "label": "パチスロ",
                "url": "../slot/",
                "is_current": False,
            },
        ]

    if page_type == "slot":
        return [
            {
                "key": "all",
                "label": "すべて",
                "url": "../",
                "is_current": False,
            },
            {
                "key": "pachinko",
                "label": "パチンコ",
                "url": "../pachinko/",
                "is_current": False,
            },
            {
                "key": "slot",
                "label": "パチスロ",
                "url": None,
                "is_current": True,
            },
        ]

    return [
        {
            "key": "all",
            "label": "すべて",
            "url": None,
            "is_current": True,
        },
        {
            "key": "pachinko",
            "label": "パチンコ",
            "url": "pachinko/",
            "is_current": False,
        },
        {
            "key": "slot",
            "label": "パチスロ",
            "url": "slot/",
            "is_current": False,
        },
    ]


# ==================================================
# 1ページ生成
# ==================================================

def generate_recent_machines_page(
    environment: Environment,
    machines: list[dict[str, Any]],
    generated_at: datetime,
    page_type: str,
    page_title: str,
    page_heading: str,
    canonical_path: str,
    output_file_path: str,
    root_prefix: str,
    category_label: str = "",
) -> int:
    """
    最近導入された機種ページを1ページ生成する。

    page_type:
        all
        pachinko
        slot
    """
    page_machines = prepare_machines_for_page(
        machines=machines,
        root_prefix=root_prefix,
    )

    period_end = generated_at.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    period_start = subtract_months(
        period_end,
        RECENT_MONTHS,
    )

    machine_count = len(
        page_machines
    )

    in_stock_count = sum(
        1
        for machine in page_machines
        if machine.get(
            "has_products"
        )
    )

    out_of_stock_count = (
        machine_count
        - in_stock_count
    )

    # 総合ページではカテゴリ選択肢を渡す。
    # カテゴリ別ページでは空配列にする。
    if page_type == "all":
        categories = get_unique_options(
            machines=page_machines,
            key="master_machine_category",
        )

    else:
        categories = []

    makers = get_unique_options(
        machines=page_machines,
        key="master_machine_maker",
    )

    machine_types = get_unique_options(
        machines=page_machines,
        key="master_machine_type",
    )

    updated_at = get_latest_updated_at(
        machines=page_machines,
        default_value=generated_at,
    )

    meta_description = (
        build_recent_machines_meta_description(
            machine_count=machine_count,
            in_stock_count=in_stock_count,
            category_label=category_label,
        )
    )

    page_description = (
        build_recent_machines_description(
            period_start=period_start,
            period_end=period_end,
            machine_count=machine_count,
            category_label=category_label,
        )
    )

    robots = (
        "index,follow"
        if machine_count > 0
        else "noindex,follow"
    )

    seo = build_seo_data(
        title=page_title,
        description=meta_description,
        canonical_path=canonical_path,
        robots=robots,
        og_type="website",
    )

    category_links = (
        create_recent_machines_category_links(
            page_type=page_type
        )
    )

    context = {
        **seo,

        # ==================================================
        # サイト共通
        # ==================================================

        "site_name": (
            SITE_NAME
        ),

        "site_description": (
            SITE_DESCRIPTION
        ),

        "current_year": (
            generated_at.year
        ),

        "is_top_page": False,

        # ==================================================
        # テンプレートが直接参照する値
        # ==================================================

        "page_title": (
            page_title
        ),

        "page_description": (
            page_description
        ),

        "breadcrumbs": (
            create_recent_machines_breadcrumbs(
                page_type=page_type
            )
        ),

        # ==================================================
        # 最近導入された機種ページ情報
        # ==================================================

        "recent_machines_title": (
            page_heading
        ),

        "recent_machines_description": (
            page_description
        ),

        "recent_months": (
            RECENT_MONTHS
        ),

        "period_start": (
            period_start
        ),

        "period_end": (
            period_end
        ),

        "period_start_display": (
            format_period_date(
                period_start
            )
        ),

        "period_end_display": (
            format_period_date(
                period_end
            )
        ),

        # ==================================================
        # ページ種別
        # ==================================================

        "page_type": (
            page_type
        ),

        "category_label": (
            category_label
        ),

        "is_all_page": (
            page_type == "all"
        ),

        "is_pachinko_page": (
            page_type == "pachinko"
        ),

        "is_slot_page": (
            page_type == "slot"
        ),

        "category_links": (
            category_links
        ),

        # ==================================================
        # 機種一覧
        # ==================================================

        "machines": (
            page_machines
        ),

        "machine_count": (
            machine_count
        ),

        "in_stock_count": (
            in_stock_count
        ),

        "out_of_stock_count": (
            out_of_stock_count
        ),

        # ==================================================
        # 絞り込み
        # ==================================================

        "categories": (
            categories
        ),

        "makers": (
            makers
        ),

        "machine_types": (
            machine_types
        ),

        "show_category_filter": (
            page_type == "all"
        ),

        # ==================================================
        # 更新日時
        # ==================================================

        "generated_at": (
            generated_at
        ),

        "updated_at": (
            updated_at
        ),

        # ==================================================
        # 相対パス
        # ==================================================

        "root_prefix": (
            root_prefix
        ),

        "asset_prefix": (
            root_prefix
        ),
    }

    template = environment.get_template(
        RECENT_MACHINES_TEMPLATE_NAME
    )

    html = template.render(
        **context
    )

    write_html(
        output_file_path=output_file_path,
        html=html,
    )

    relative_output_path = os.path.relpath(
        output_file_path,
        OUTPUT_DIR,
    ).replace(
        os.sep,
        "/",
    )

    print(
        "[生成] "
        f"{relative_output_path}"
        f" - {machine_count:,}機種"
    )

    print(
        "  ページ種別: "
        f"{page_type}"
    )

    print(
        "  対象期間: "
        f"{period_start.strftime('%Y-%m-%d')}"
        " ～ "
        f"{period_end.strftime('%Y-%m-%d')}"
    )

    print(
        "  在庫あり: "
        f"{in_stock_count:,}機種"
    )

    print(
        "  現在出品なし: "
        f"{out_of_stock_count:,}機種"
    )

    print(
        "  カテゴリ数: "
        f"{len(categories):,}件"
    )

    print(
        "  メーカー数: "
        f"{len(makers):,}件"
    )

    print(
        "  機種タイプ数: "
        f"{len(machine_types):,}件"
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

    return machine_count


# ==================================================
# 最近導入された機種ページ生成
# ==================================================

def generate_recent_machines() -> None:
    """
    次の3ページを生成する。

    output/recent-machines/index.html
    output/recent-machines/pachinko/index.html
    output/recent-machines/slot/index.html
    """
    start_time = time.perf_counter()

    generated_at = datetime.now()

    os.makedirs(
        RECENT_MACHINES_OUTPUT_DIR,
        exist_ok=True,
    )

    os.makedirs(
        os.path.dirname(
            RECENT_MACHINES_PACHINKO_OUTPUT_FILE_PATH
        ),
        exist_ok=True,
    )

    os.makedirs(
        os.path.dirname(
            RECENT_MACHINES_SLOT_OUTPUT_FILE_PATH
        ),
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
            RECENT_MACHINES_CSS_PATH,
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
            MACHINE_MASTER_TABLE_NAME,
        )

        check_table_exists(
            connection,
            PRODUCT_SUMMARY_TABLE_NAME,
        )

        print(
            "[確認] インデックスを確認します。",
            flush=True,
        )

        create_recent_machines_indexes(
            connection
        )

        print(
            "[確認] 最近導入された機種を取得します。",
            flush=True,
        )

        all_recent_machines, counts = (
            get_recent_machines(
                connection=connection,
                generated_at=generated_at,
                recent_months=RECENT_MONTHS,
            )
        )

        print(
            "[確認] 最近導入された機種取得完了: "
            f"{len(all_recent_machines):,}件",
            flush=True,
        )

        (
            pachinko_machines,
            slot_machines,
            other_machines,
        ) = split_machines_by_category(
            all_recent_machines
        )

        print(
            "[確認] カテゴリ分割結果"
        )

        print(
            "  パチンコ: "
            f"{len(pachinko_machines):,}件"
        )

        print(
            "  パチスロ: "
            f"{len(slot_machines):,}件"
        )

        print(
            "  カテゴリ判定不能: "
            f"{len(other_machines):,}件"
        )

        if other_machines:
            print(
                "  カテゴリ判定不能の値:"
            )

            unknown_categories = (
                get_unique_options(
                    machines=other_machines,
                    key=(
                        "master_machine_category"
                    ),
                )
            )

            for category in unknown_categories:
                print(
                    f"    - {category}"
                )

        print("-" * 70)

        # --------------------------------------------------
        # 総合ページ
        # --------------------------------------------------

        all_page_count = (
            generate_recent_machines_page(
                environment=environment,
                machines=all_recent_machines,
                generated_at=generated_at,
                page_type="all",
                page_title=(
                    RECENT_MACHINES_PAGE_TITLE
                ),
                page_heading=(
                    RECENT_MACHINES_HEADING
                ),
                canonical_path=(
                    RECENT_MACHINES_CANONICAL_PATH
                ),
                output_file_path=(
                    RECENT_MACHINES_OUTPUT_FILE_PATH
                ),
                root_prefix="../",
                category_label="",
            )
        )

        print("-" * 70)

        # --------------------------------------------------
        # パチンコページ
        # --------------------------------------------------

        pachinko_page_count = (
            generate_recent_machines_page(
                environment=environment,
                machines=pachinko_machines,
                generated_at=generated_at,
                page_type="pachinko",
                page_title=(
                    RECENT_MACHINES_PACHINKO_PAGE_TITLE
                ),
                page_heading=(
                    RECENT_MACHINES_PACHINKO_HEADING
                ),
                canonical_path=(
                    RECENT_MACHINES_PACHINKO_CANONICAL_PATH
                ),
                output_file_path=(
                    RECENT_MACHINES_PACHINKO_OUTPUT_FILE_PATH
                ),
                root_prefix="../../",
                category_label="パチンコ",
            )
        )

        print("-" * 70)

        # --------------------------------------------------
        # パチスロページ
        # --------------------------------------------------

        slot_page_count = (
            generate_recent_machines_page(
                environment=environment,
                machines=slot_machines,
                generated_at=generated_at,
                page_type="slot",
                page_title=(
                    RECENT_MACHINES_SLOT_PAGE_TITLE
                ),
                page_heading=(
                    RECENT_MACHINES_SLOT_HEADING
                ),
                canonical_path=(
                    RECENT_MACHINES_SLOT_CANONICAL_PATH
                ),
                output_file_path=(
                    RECENT_MACHINES_SLOT_OUTPUT_FILE_PATH
                ),
                root_prefix="../../",
                category_label="パチスロ",
            )
        )

    elapsed_time = (
        time.perf_counter()
        - start_time
    )

    print("=" * 70)

    print(
        "最近導入された機種ページを"
        "生成しました。"
    )

    print(
        "出力ファイル:"
    )

    print(
        "  "
        f"{RECENT_MACHINES_OUTPUT_FILE_PATH}"
    )

    print(
        "  "
        f"{RECENT_MACHINES_PACHINKO_OUTPUT_FILE_PATH}"
    )

    print(
        "  "
        f"{RECENT_MACHINES_SLOT_OUTPUT_FILE_PATH}"
    )

    print(
        "使用テンプレート: "
        f"{os.path.join(TEMPLATE_DIR, RECENT_MACHINES_TEMPLATE_NAME)}"
    )

    print(
        "使用CSS: "
        f"{os.path.join(PROJECT_ROOT, 'static', RECENT_MACHINES_CSS_PATH)}"
    )

    print(
        "掲載機種数:"
    )

    print(
        "  総合ページ: "
        f"{all_page_count:,}件"
    )

    print(
        "  パチンコページ: "
        f"{pachinko_page_count:,}件"
    )

    print(
        "  パチスロページ: "
        f"{slot_page_count:,}件"
    )

    print(
        "  カテゴリ判定不能: "
        f"{len(other_machines):,}件"
    )

    print(
        "DB取得・除外状況:"
    )

    print(
        "  machine_master取得件数: "
        f"{counts['all_count']:,}件"
    )

    print(
        "  導入日解析成功: "
        f"{counts['parsed_count']:,}件"
    )

    print(
        "  導入日解析失敗: "
        f"{counts['unparsed_count']:,}件"
    )

    print(
        "  将来導入予定のため除外: "
        f"{counts['future_count']:,}件"
    )

    print(
        "  対象期間より前のため除外: "
        f"{counts['old_count']:,}件"
    )

    print(
        "  機種ID不正のため除外: "
        f"{counts['invalid_machine_id_count']:,}件"
    )

    print(
        "対象期間: "
        f"過去{RECENT_MONTHS}か月"
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
        generate_recent_machines()

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
            "テンプレート名: "
            f"{RECENT_MACHINES_TEMPLATE_NAME}"
        )

        raise

    except FileNotFoundError as error:
        print("-" * 70)

        print(
            "最近導入された機種ページ用の"
            "静的ファイルが見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            "確認するCSS: "
            f"{os.path.join(PROJECT_ROOT, 'static', RECENT_MACHINES_CSS_PATH)}"
        )

        raise

    except (
        TypeError,
        ValueError,
    ) as error:
        print("-" * 70)

        print(
            "最近導入された機種ページ設定に"
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
            "最近導入された機種ページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise