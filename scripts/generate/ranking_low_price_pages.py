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

from utils.breadcrumb_utils import (
    create_ranking_detail_breadcrumbs,
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

LOW_PRICE_OUTPUT_DIR = os.path.join(
    OUTPUT_DIR,
    "rankings",
    "low-price",
)

LOW_PRICE_ALL_OUTPUT_FILE_PATH = os.path.join(
    LOW_PRICE_OUTPUT_DIR,
    "index.html",
)

LOW_PRICE_PACHINKO_OUTPUT_FILE_PATH = os.path.join(
    LOW_PRICE_OUTPUT_DIR,
    "pachinko",
    "index.html",
)

LOW_PRICE_SLOT_OUTPUT_FILE_PATH = os.path.join(
    LOW_PRICE_OUTPUT_DIR,
    "slot",
    "index.html",
)


# ==================================================
# テンプレート設定
# ==================================================

RANKING_DETAIL_TEMPLATE_NAME = (
    "rankings/ranking_low_price_index.html"
)


# ==================================================
# 最安価格ランキング基本設定
# ==================================================

LOW_PRICE_RANKING_LIMIT = 100

LOW_PRICE_RANKING_UNIT = "円"


# ==================================================
# category設定
# ==================================================

# product_summaryの種別列
CATEGORY_COLUMN_NAME = "category"

# product_summary.categoryに保存されている値
PACHINKO_CATEGORY_VALUE = "pachi"
SLOT_CATEGORY_VALUE = "slot"


# ==================================================
# ランキングページ設定
# ==================================================

RANKING_PAGE_CONFIGS = {
    "all": {
        "ranking_key": "low-price",
        "ranking_title": (
            "中古実機の最安価格ランキング"
        ),
        "ranking_description": (
            "パチンコ・パチスロ中古実機を、"
            "現在の最安価格が安い順に"
            "掲載しています。"
        ),
        "page_title": (
            "パチンコ・パチスロ中古実機の"
            "最安価格ランキング"
        ),
        "canonical_path": (
            "/rankings/low-price/"
        ),
        "output_file_path": (
            LOW_PRICE_ALL_OUTPUT_FILE_PATH
        ),
        "root_prefix": "../../",

        # DB検索用category
        "category": None,

        # テンプレート表示用キー
        "display_category": "all",

        "print_path": (
            "rankings/low-price/index.html"
        ),
    },

    "pachinko": {
        "ranking_key": "low-price-pachinko",
        "ranking_title": (
            "中古パチンコ実機の最安価格ランキング"
        ),
        "ranking_description": (
            "中古パチンコ実機を、"
            "現在の最安価格が安い順に"
            "掲載しています。"
        ),
        "page_title": (
            "中古パチンコ実機の"
            "最安価格ランキング"
        ),
        "canonical_path": (
            "/rankings/low-price/pachinko/"
        ),
        "output_file_path": (
            LOW_PRICE_PACHINKO_OUTPUT_FILE_PATH
        ),
        "root_prefix": "../../../",

        # DB検索用category
        "category": PACHINKO_CATEGORY_VALUE,

        # テンプレート表示用キー
        "display_category": "pachinko",

        "print_path": (
            "rankings/low-price/"
            "pachinko/index.html"
        ),
    },

    "slot": {
        "ranking_key": "low-price-slot",
        "ranking_title": (
            "中古パチスロ実機の最安価格ランキング"
        ),
        "ranking_description": (
            "中古パチスロ・スロット実機を、"
            "現在の最安価格が安い順に"
            "掲載しています。"
        ),
        "page_title": (
            "中古パチスロ実機の"
            "最安価格ランキング"
        ),
        "canonical_path": (
            "/rankings/low-price/slot/"
        ),
        "output_file_path": (
            LOW_PRICE_SLOT_OUTPUT_FILE_PATH
        ),
        "root_prefix": "../../../",

        # DB検索用category
        "category": SLOT_CATEGORY_VALUE,

        # テンプレート表示用キー
        "display_category": "slot",

        "print_path": (
            "rankings/low-price/"
            "slot/index.html"
        ),
    },
}


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
# テーブル列取得・確認
# ==================================================

def get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """
    SQLiteテーブルの列名一覧を取得する。
    """
    safe_table_name = validate_identifier(
        table_name
    )

    rows = connection.execute(
        f"PRAGMA table_info({safe_table_name})"
    ).fetchall()

    columns: set[str] = set()

    for row in rows:
        try:
            column_name = row["name"]
        except (TypeError, KeyError):
            column_name = row[1]

        if column_name:
            columns.add(
                str(column_name)
            )

    return columns


def check_category_column(
    connection: sqlite3.Connection,
) -> None:
    """
    product_summaryにcategory列が
    存在することを確認する。
    """
    table_columns = get_table_columns(
        connection=connection,
        table_name=SUMMARY_TABLE_NAME,
    )

    if CATEGORY_COLUMN_NAME not in table_columns:
        raise RuntimeError(
            f"{SUMMARY_TABLE_NAME}に"
            f"{CATEGORY_COLUMN_NAME}カラムがありません。"
            "\n先にproduct_summary集計処理を実行し、"
            "categoryカラムを作成してください。"
        )


def print_category_counts(
    connection: sqlite3.Connection,
) -> None:
    """
    product_summary.categoryの
    登録状況を表示する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    category_column = validate_identifier(
        CATEGORY_COLUMN_NAME
    )

    sql = f"""
        SELECT
            COALESCE(
                NULLIF(
                    LOWER(
                        TRIM(
                            CAST(
                                {category_column}
                                AS TEXT
                            )
                        )
                    ),
                    ''
                ),
                '(空)'
            ) AS category_value,

            COUNT(*) AS machine_count

        FROM {table_name}

        GROUP BY
            COALESCE(
                NULLIF(
                    LOWER(
                        TRIM(
                            CAST(
                                {category_column}
                                AS TEXT
                            )
                        )
                    ),
                    ''
                ),
                '(空)'
            )

        ORDER BY
            machine_count DESC,
            category_value ASC
    """

    rows = connection.execute(
        sql
    ).fetchall()

    print(
        f"{SUMMARY_TABLE_NAME} category内訳:"
    )

    if not rows:
        print(
            "  データなし"
        )
        return

    for row in rows:
        print(
            "  "
            f"{row['category_value']}: "
            f"{int(row['machine_count'] or 0):,}機種"
        )


# ==================================================
# ランキング表示件数
# ==================================================

def normalize_ranking_limit(
    limit: Any,
) -> int:
    """
    ランキング表示件数を
    正の整数へ変換する。
    """
    try:
        limit_value = int(
            limit
        )
    except (TypeError, ValueError):
        return LOW_PRICE_RANKING_LIMIT

    if limit_value <= 0:
        return LOW_PRICE_RANKING_LIMIT

    return limit_value


# ==================================================
# 最安価格ランキング対象条件
# ==================================================

def build_low_price_where_sql(
    category: str | None = None,
) -> tuple[str, list[Any]]:
    """
    最安価格ランキングの対象条件SQLと
    バインドパラメータを返す。

    category:
        None
            パチンコ・スロット総合

        pachi
            パチンコのみ

        slot
            パチスロのみ
    """
    category_column = validate_identifier(
        CATEGORY_COLUMN_NAME
    )

    where_parts = [
        """
        master_machine_id IS NOT NULL
        """,
        """
        TRIM(
            CAST(
                master_machine_id AS TEXT
            )
        ) != ''
        """,
        """
        master_machine_name IS NOT NULL
        """,
        """
        TRIM(master_machine_name) != ''
        """,
        """
        min_price IS NOT NULL
        """,
        """
        min_price > 0
        """,
    ]

    parameters: list[Any] = []

    if category is not None:
        normalized_category = (
            str(category)
            .strip()
            .lower()
        )

        if normalized_category not in {
            PACHINKO_CATEGORY_VALUE,
            SLOT_CATEGORY_VALUE,
        }:
            raise ValueError(
                "未対応のランキングカテゴリです: "
                f"{category}"
            )

        where_parts.append(
            f"""
            LOWER(
                TRIM(
                    CAST(
                        {category_column}
                        AS TEXT
                    )
                )
            ) = ?
            """
        )

        parameters.append(
            normalized_category
        )

    where_sql = "\nAND\n".join(
        part.strip()
        for part in where_parts
    )

    return (
        where_sql,
        parameters,
    )


# ==================================================
# DBデータ取得
# ==================================================

def get_low_price_ranking(
    connection: sqlite3.Connection,
    category: str | None = None,
    limit: int = LOW_PRICE_RANKING_LIMIT,
) -> list[dict[str, Any]]:
    """
    最安価格が安い順に機種を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    limit_value = normalize_ranking_limit(
        limit
    )

    where_sql, where_parameters = (
        build_low_price_where_sql(
            category=category,
        )
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

    query_parameters = [
        *where_parameters,
        limit_value,
    ]

    rows = connection.execute(
        sql,
        query_parameters,
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]


def get_low_price_machine_count(
    connection: sqlite3.Connection,
    category: str | None = None,
) -> int:
    """
    最安価格ランキングの
    対象機種数を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    where_sql, where_parameters = (
        build_low_price_where_sql(
            category=category,
        )
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
        where_parameters,
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["machine_count"]
        or 0
    )


def get_low_price_ranking_updated_at(
    connection: sqlite3.Connection,
    category: str | None = None,
) -> Any:
    """
    最安価格ランキング対象データの
    最終更新日時を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    where_sql, where_parameters = (
        build_low_price_where_sql(
            category=category,
        )
    )

    sql = f"""
        SELECT
            COALESCE(
                MAX(latest_scraped_at),
                MAX(updated_at)
            ) AS ranking_updated_at

        FROM {table_name}

        WHERE
            {where_sql}
    """

    row = connection.execute(
        sql,
        where_parameters,
    ).fetchone()

    if row is None:
        return None

    return row["ranking_updated_at"]


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_low_price_meta_description(
    machine_count: int,
    ranking_limit: int,
    category: str | None = None,
) -> str:
    """
    最安価格ランキング用の
    meta descriptionを作成する。
    """
    display_count = min(
        machine_count,
        ranking_limit,
    )

    if category == PACHINKO_CATEGORY_VALUE:
        category_text = (
            "中古パチンコ実機"
        )

    elif category == SLOT_CATEGORY_VALUE:
        category_text = (
            "中古パチスロ・スロット実機"
        )

    else:
        category_text = (
            "パチンコ・パチスロ中古実機"
        )

    return (
        f"{category_text}を、"
        "現在の最安価格が安い順に"
        "ランキングで掲載しています。"
        f"価格情報のある{machine_count:,}機種のうち、"
        f"上位{display_count:,}機種について、"
        "最安値、平均価格、出品件数、"
        "販売店情報を比較できます。"
    )


# ==================================================
# カテゴリリンク作成
# ==================================================

def build_ranking_category_links(
    root_prefix: str,
) -> dict[str, dict[str, str]]:
    """
    総合・パチンコ・スロットの
    切り替えリンクを作成する。
    """
    return {
        "all": {
            "label": "総合",
            "url": (
                root_prefix
                + "rankings/low-price/"
            ),
        },
        "pachinko": {
            "label": "パチンコ",
            "url": (
                root_prefix
                + "rankings/low-price/"
                + "pachinko/"
            ),
        },
        "slot": {
            "label": "スロット",
            "url": (
                root_prefix
                + "rankings/low-price/"
                + "slot/"
            ),
        },
    }


# ==================================================
# 最安価格ランキングページ生成
# ==================================================

def generate_low_price_ranking_page(
    environment: Environment,
    connection: sqlite3.Connection,
    generated_at: datetime,
    page_config: dict[str, Any],
) -> int:
    """
    指定された設定に基づいて
    最安価格ランキングページを生成する。
    """
    template = environment.get_template(
        RANKING_DETAIL_TEMPLATE_NAME
    )

    category = page_config["category"]

    machines = get_low_price_ranking(
        connection=connection,
        category=category,
        limit=LOW_PRICE_RANKING_LIMIT,
    )

    total_machine_count = (
        get_low_price_machine_count(
            connection=connection,
            category=category,
        )
    )

    ranking_updated_at = (
        get_low_price_ranking_updated_at(
            connection=connection,
            category=category,
        )
    )

    meta_description = (
        build_low_price_meta_description(
            machine_count=(
                total_machine_count
            ),
            ranking_limit=(
                LOW_PRICE_RANKING_LIMIT
            ),
            category=category,
        )
    )

    seo = build_seo_data(
        title=page_config["page_title"],
        description=meta_description,
        canonical_path=(
            page_config["canonical_path"]
        ),
        robots="index,follow",
        og_type="website",
    )

    root_prefix = page_config[
        "root_prefix"
    ]

    context = {
        # SEO情報
        **seo,

        # header.html・footer.html用
        "site_description": (
            SITE_DESCRIPTION
        ),
        "current_year": (
            generated_at.year
        ),
        "is_top_page": False,

        # パンくずリスト
        "breadcrumbs": (
            create_ranking_detail_breadcrumbs(
                page_config[
                    "ranking_title"
                ]
            )
        ),

        # ランキング詳細ページ用
        "ranking_title": (
            page_config[
                "ranking_title"
            ]
        ),
        "ranking_description": (
            page_config[
                "ranking_description"
            ]
        ),
        "ranking_key": (
            page_config[
                "ranking_key"
            ]
        ),
        "ranking_unit": (
            LOW_PRICE_RANKING_UNIT
        ),

        # 現在のカテゴリ
        #
        # DB上はpachiだが、
        # テンプレートではpachinkoを使用する。
        "ranking_category": (
            page_config[
                "display_category"
            ]
        ),

        # カテゴリページリンク
        "ranking_category_links": (
            build_ranking_category_links(
                root_prefix=root_prefix,
            )
        ),

        # ランキングデータ
        "machines": machines,
        "machine_count": len(
            machines
        ),
        "total_machine_count": (
            total_machine_count
        ),

        # 更新日時
        "generated_at": generated_at,
        "updated_at": (
            ranking_updated_at
            or generated_at
        ),

        # 出力ページから見た相対パス
        "root_prefix": root_prefix,
        "asset_prefix": root_prefix,
    }

    html = template.render(
        **context
    )

    write_html(
        output_file_path=(
            page_config[
                "output_file_path"
            ]
        ),
        html=html,
    )

    print(
        "[生成] "
        f"{page_config['print_path']}"
        f" - {len(machines):,}機種"
    )

    print(
        "  DB category: "
        f"{category or '総合'}"
    )

    print(
        "  対象機種総数: "
        f"{total_machine_count:,}機種"
    )

    print(
        "  title: "
        f"{context['page_title']}"
    )

    print(
        "  canonical: "
        f"{context['canonical_url']}"
    )

    return len(
        machines
    )


# ==================================================
# 最安価格ランキング生成処理
# ==================================================

def generate_low_price_ranking() -> None:
    """
    以下の最安価格ランキングページを生成する。

    output/rankings/low-price/index.html

    output/rankings/low-price/
        pachinko/index.html

    output/rankings/low-price/
        slot/index.html
    """
    start_time = time.perf_counter()

    generated_at = datetime.now()

    os.makedirs(
        LOW_PRICE_OUTPUT_DIR,
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
            "css/ranking_low_price_index.css",
        ),
    )

    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
    )

    generated_counts: dict[str, int] = {}

    with connect_database(
        DB_PATH
    ) as connection:
        check_table_exists(
            connection,
            SUMMARY_TABLE_NAME,
        )

        check_category_column(
            connection
        )

        print(
            "ランキング取得元テーブル: "
            f"{SUMMARY_TABLE_NAME}"
        )

        print(
            "カテゴリ列: "
            f"{CATEGORY_COLUMN_NAME}"
        )

        print_category_counts(
            connection
        )

        for page_key, page_config in (
            RANKING_PAGE_CONFIGS.items()
        ):
            generated_counts[page_key] = (
                generate_low_price_ranking_page(
                    environment=environment,
                    connection=connection,
                    generated_at=generated_at,
                    page_config=page_config,
                )
            )

    elapsed_time = (
        time.perf_counter()
        - start_time
    )

    print("=" * 60)

    print(
        "最安価格ランキングページを"
        "生成しました。"
    )

    print(
        "総合ランキング: "
        f"{generated_counts.get('all', 0):,}件"
    )

    print(
        "パチンコランキング: "
        f"{generated_counts.get('pachinko', 0):,}件"
    )

    print(
        "スロットランキング: "
        f"{generated_counts.get('slot', 0):,}件"
    )

    print(
        "ランキング表示上限: "
        f"各{LOW_PRICE_RANKING_LIMIT:,}件"
    )

    print(
        "出力先:"
    )

    print(
        "  "
        f"{LOW_PRICE_ALL_OUTPUT_FILE_PATH}"
    )

    print(
        "  "
        f"{LOW_PRICE_PACHINKO_OUTPUT_FILE_PATH}"
    )

    print(
        "  "
        f"{LOW_PRICE_SLOT_OUTPUT_FILE_PATH}"
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
        generate_low_price_ranking()

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

        raise

    except Exception as error:
        print("-" * 60)

        print(
            "最安価格ランキングページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise