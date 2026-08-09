import os
import sqlite3
import sys
import time

from datetime import datetime

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
    create_ranking_list_breadcrumbs,
)

from utils.db_utils import (
    SUMMARY_TABLE_NAME,
    check_table_exists,
    connect_database,
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
# 出力先設定
# ==================================================

RANKING_OUTPUT_DIR = os.path.join(
    OUTPUT_DIR,
    "rankings",
)

RANKING_LIST_OUTPUT_FILE_PATH = os.path.join(
    RANKING_OUTPUT_DIR,
    "index.html",
)


# ==================================================
# テンプレート設定
# ==================================================

RANKING_LIST_TEMPLATE_NAME = (
    "rankings/ranking_index.html"
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
# DBデータ取得
# ==================================================

def get_ranking_machine_count(
    connection: sqlite3.Connection,
) -> int:
    """
    価格ランキングの対象となる
    機種数を取得する。
    """
    table_name = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    sql = f"""
        SELECT
            COUNT(*) AS machine_count

        FROM {table_name}

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
    """

    row = connection.execute(
        sql
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["machine_count"]
        or 0
    )


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_ranking_list_meta_description(
    ranking_count: int,
    machine_count: int,
) -> str:
    """
    ランキング一覧ページ用の
    meta descriptionを作成する。
    """
    return (
        "パチンコ・パチスロ中古実機の"
        f"価格ランキングを{ranking_count:,}種類掲載しています。"
        f"現在{machine_count:,}機種を対象に、"
        "最安値や中古価格相場をランキング形式で"
        "確認できます。"
    )


# ==================================================
# ランキング一覧ページ生成
# ==================================================

def generate_ranking_list_page(
    environment: Environment,
    connection: sqlite3.Connection,
    generated_at: datetime,
) -> int:
    """
    ランキング一覧ページを生成する。

    出力先:
        output/rankings/index.html
    """
    template = environment.get_template(
        RANKING_LIST_TEMPLATE_NAME
    )

    machine_count = get_ranking_machine_count(
        connection
    )

    rankings = [
        {
            "title": (
                "中古実機の総合最安価格ランキング"
            ),
            "label": (
                "総合ランキング"
            ),
            "description": (
                "パチンコ・パチスロ中古実機を合わせて、"
                "現在の最安価格が安い順に掲載しています。"
            ),
            "url": "low-price/",
            "machine_count": machine_count,
        },
        {
            "title": (
                "パチンコ中古実機の最安価格ランキング"
            ),
            "label": (
                "パチンコランキング"
            ),
            "description": (
                "パチンコ中古実機を、"
                "現在の最安価格が安い順に掲載しています。"
            ),
            "url": "low-price/pachinko/",
            "machine_count": None,
        },
        {
            "title": (
                "パチスロ中古実機の最安価格ランキング"
            ),
            "label": (
                "スロットランキング"
            ),
            "description": (
                "パチスロ中古実機を、"
                "現在の最安価格が安い順に掲載しています。"
            ),
            "url": "low-price/slot/",
            "machine_count": None,
        },
    ]

    ranking_count = len(
        rankings
    )

    meta_description = (
        build_ranking_list_meta_description(
            ranking_count=ranking_count,
            machine_count=machine_count,
        )
    )

    seo = build_seo_data(
        title=(
            "パチンコ・パチスロ中古実機ランキング"
        ),
        description=meta_description,
        canonical_path="/rankings/",
        robots="index,follow",
        og_type="website",
    )

    context = {
        # SEO情報
        **seo,

        # header.html・footer.html用
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # パンくずリスト
        "breadcrumbs": (
            create_ranking_list_breadcrumbs()
        ),

        # ランキング一覧ページ用
        "rankings": rankings,
        "ranking_count": ranking_count,

        # 更新日時
        "generated_at": generated_at,
        "updated_at": generated_at,

        # output/rankings/index.htmlから見た相対パス
        "root_prefix": "../",
        "asset_prefix": "../",
    }

    html = template.render(
        **context
    )

    write_html(
        RANKING_LIST_OUTPUT_FILE_PATH,
        html,
    )

    print(
        "[生成] rankings/index.html"
        f" - {ranking_count:,}ランキング"
    )

    print(
        "  title: "
        f"{context['page_title']}"
    )

    print(
        "  canonical: "
        f"{context['canonical_url']}"
    )

    return ranking_count


# ==================================================
# ランキング一覧ページ生成
# ==================================================

def generate_ranking_list_pages() -> None:
    """
    ランキング一覧ページのみ生成する。
    """
    generated_at = datetime.now()

    os.makedirs(
        RANKING_OUTPUT_DIR,
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
            "css/ranking_index.css",
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
            SUMMARY_TABLE_NAME,
        )

        ranking_count = (
            generate_ranking_list_page(
                environment=environment,
                connection=connection,
                generated_at=generated_at,
            )
        )

    elapsed_time = (
        time.time()
        - START_TIME
    )

    print("=" * 60)

    print(
        "ランキング一覧ページを生成しました。"
    )

    print(
        "出力先: "
        f"{RANKING_LIST_OUTPUT_FILE_PATH}"
    )

    print(
        "掲載ランキング数: "
        f"{ranking_count:,}件"
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
        generate_ranking_list_pages()

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
            "ランキング一覧ページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise