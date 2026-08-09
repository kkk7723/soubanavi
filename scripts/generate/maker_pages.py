import os
import sqlite3
import sys
import time
import re

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

from utils.breadcrumb_utils import (
    create_maker_detail_breadcrumbs,
    create_maker_list_breadcrumbs,
)

from utils.db_utils import (
    SUMMARY_TABLE_NAME,
    check_table_exists,
    connect_database,
    row_to_dict,
    validate_identifier,
)

from utils.maker_utils import (
    ensure_unique_maker_slugs,
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
# テンプレート設定
# ==================================================

MAKER_LIST_TEMPLATE_NAME = (
    "makers/maker_index.html"
)

MAKER_DETAIL_TEMPLATE_NAME = (
    "makers/maker_detail.html"
)


# ==================================================
# 出力先設定
# ==================================================

OUTPUT_MAKERS_DIR = (
    Path(OUTPUT_DIR)
    / "makers"
)

MAKER_LIST_OUTPUT_PATH = (
    OUTPUT_MAKERS_DIR
    / "index.html"
)


# ==================================================
# DBデータ取得
# ==================================================

def get_makers(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """
    メーカー一覧と
    メーカー別集計情報を取得する。
    """
    safe_summary_table = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    sql = f"""
        SELECT
            TRIM(
                master_machine_maker
            ) AS name,

            COUNT(*) AS machine_count,

            COALESCE(
                SUM(price_count),
                0
            ) AS product_count,

            COALESCE(
                SUM(shop_count),
                0
            ) AS shop_count,

            MIN(
                CASE
                    WHEN min_price > 0
                        THEN min_price
                    ELSE NULL
                END
            ) AS min_price,

            MAX(
                CASE
                    WHEN max_price > 0
                        THEN max_price
                    ELSE NULL
                END
            ) AS max_price,

            AVG(
                CASE
                    WHEN avg_price > 0
                        THEN avg_price
                    ELSE NULL
                END
            ) AS avg_price,

            MAX(
                COALESCE(
                    latest_scraped_at,
                    last_seen,
                    updated_at
                )
            ) AS updated_at

        FROM {safe_summary_table}

        WHERE master_machine_id IS NOT NULL
          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''
          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''
          AND master_machine_maker IS NOT NULL
          AND TRIM(master_machine_maker) != ''

        GROUP BY
            TRIM(master_machine_maker)

        ORDER BY
            TRIM(master_machine_maker)
            COLLATE NOCASE ASC
    """

    rows = connection.execute(
        sql
    ).fetchall()

    makers = [
        row_to_dict(row)
        for row in rows
    ]

    ensure_unique_maker_slugs(
        makers
    )

    return makers


def get_machines_by_maker(
    connection: sqlite3.Connection,
    maker_name: str,
) -> list[dict[str, Any]]:
    """
    指定メーカーの機種一覧を取得する。
    """
    safe_summary_table = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    sql = f"""
        SELECT
            id,
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
            first_seen,
            last_seen,
            latest_scraped_at,
            created_at,
            updated_at

        FROM {safe_summary_table}

        WHERE master_machine_id IS NOT NULL
          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''
          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''
          AND master_machine_maker IS NOT NULL
          AND TRIM(master_machine_maker) = TRIM(?)

        ORDER BY
            CAST(
                master_machine_id AS INTEGER
            ) ASC,
            master_machine_id ASC
    """

    rows = connection.execute(
        sql,
        (
            maker_name,
        ),
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]


# ==================================================
# SEO用テキスト作成
# ==================================================

def build_maker_list_meta_description(
    maker_count: int,
    machine_count: int,
    product_count: int,
) -> str:
    """
    メーカー一覧ページ用の
    meta descriptionを作成する。
    """
    return (
        f"パチンコ・パチスロ実機を扱う"
        f"{maker_count:,}メーカーを一覧で掲載しています。"
        f"全{machine_count:,}機種、"
        f"{product_count:,}件の中古実機出品情報から、"
        "メーカー別の価格相場や機種情報を確認できます。"
    )


def build_maker_detail_meta_description(
    maker_name: str,
    machine_count: int,
    product_count: int,
) -> str:
    """
    メーカー詳細ページ用の
    meta descriptionを作成する。
    """
    if product_count > 0:
        return (
            f"{maker_name}のパチンコ・パチスロ実機"
            f"{machine_count:,}機種、"
            f"{product_count:,}件の中古出品情報を掲載しています。"
            "最安値、平均価格、価格相場、"
            "機種ごとの販売情報を比較できます。"
        )

    return (
        f"{maker_name}のパチンコ・パチスロ実機"
        f"{machine_count:,}機種を掲載しています。"
        "各機種の中古価格、最安値、平均価格、"
        "価格相場を確認できます。"
    )


# ==================================================
# コンテキスト作成
# ==================================================

def build_maker_list_context(
    makers: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """
    maker_list.htmlへ渡すデータを作成する。
    """
    maker_count = len(
        makers
    )

    total_machine_count = sum(
        int(
            maker.get("machine_count")
            or 0
        )
        for maker in makers
    )

    total_product_count = sum(
        int(
            maker.get("product_count")
            or 0
        )
        for maker in makers
    )

    meta_description = (
        build_maker_list_meta_description(
            maker_count=maker_count,
            machine_count=total_machine_count,
            product_count=total_product_count,
        )
    )

    seo = build_seo_data(
        title="パチンコ・パチスロメーカー一覧",
        description=meta_description,
        canonical_path="/makers/",
        robots="index,follow",
        og_type="website",
    )

    return {
        # SEO情報
        **seo,

        # header.html・footer.html用
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # パンくずリスト
        "breadcrumbs": (
            create_maker_list_breadcrumbs()
        ),

        # output/makers/index.htmlから見た相対パス
        "root_prefix": "../",
        "asset_prefix": "../",

        # メーカー一覧ページ用
        "makers": makers,
        "maker_count": maker_count,
        "machine_count": total_machine_count,
        "product_count": total_product_count,

        # 更新日時
        "generated_at": generated_at,
        "updated_at": generated_at,
    }


def build_maker_detail_context(
    maker: dict[str, Any],
    machines: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """
    maker_detail.htmlへ渡すデータを作成する。
    """
    page_updated_at = (
        maker.get("updated_at")
        or generated_at
    )

    maker_name = str(
        maker.get("name")
        or ""
    ).strip()

    maker_slug = str(
        maker.get("slug")
        or ""
    ).strip()

    machine_count = len(
        machines
    )

    product_count = int(
        maker.get("product_count")
        or 0
    )

    meta_description = (
        build_maker_detail_meta_description(
            maker_name=maker_name,
            machine_count=machine_count,
            product_count=product_count,
        )
    )

    seo = build_seo_data(
        title=(
            f"{maker_name}のパチンコ・パチスロ実機一覧"
        ),
        description=meta_description,
        canonical_path=(
            f"/makers/{maker_slug}/"
        ),
        robots="index,follow",
        og_type="website",
    )

    return {
        # SEO情報
        **seo,

        # header.html・footer.html用
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # パンくずリスト
        "breadcrumbs": (
            create_maker_detail_breadcrumbs(
                maker_name
            )
        ),

        # output/makers/<slug>/index.htmlから見た相対パス
        "root_prefix": "../../",
        "asset_prefix": "../../",

        # メーカー詳細ページ用
        "maker": maker,
        "machines": machines,
        "machine_count": machine_count,
        "product_count": product_count,

        # 更新日時
        "generated_at": generated_at,
        "updated_at": page_updated_at,
    }


# ==================================================
# staticファイルコピー
# ==================================================

def copy_maker_static_files() -> None:
    """
    共通staticファイルと
    メーカーページで使用するファイルをコピーする。
    """
    copy_common_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
    )

    copy_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
        relative_paths=(
            "css/machine_index.css",
        ),
    )


# ==================================================
# HTML生成
# ==================================================

def generate_maker_pages() -> None:
    """
    メーカー一覧ページと
    メーカー詳細ページを生成する。

    出力例:
        output/makers/index.html
        output/makers/sammy/index.html
        output/makers/sankyo/index.html
    """
    start_time = time.time()
    generated_at = datetime.now()

    OUTPUT_MAKERS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy_maker_static_files()

    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
        root_prefix=ROOT_PREFIX,
        asset_prefix=ASSET_PREFIX,
    )

    try:
        maker_list_template = (
            environment.get_template(
                MAKER_LIST_TEMPLATE_NAME
            )
        )

        maker_detail_template = (
            environment.get_template(
                MAKER_DETAIL_TEMPLATE_NAME
            )
        )

    except TemplateNotFound as error:
        raise FileNotFoundError(
            "Jinja2テンプレートが見つかりません: "
            f"{error.name}"
        ) from error

    detail_generated_count = 0
    error_count = 0
    total_machine_count = 0

    with connect_database(
        DB_PATH
    ) as connection:
        check_table_exists(
            connection,
            SUMMARY_TABLE_NAME,
        )

        makers = get_makers(
            connection
        )

        print("=" * 70)

        print(
            "メーカー一覧テンプレート: "
            f"{Path(TEMPLATE_DIR) / MAKER_LIST_TEMPLATE_NAME}"
        )

        print(
            "メーカー詳細テンプレート: "
            f"{Path(TEMPLATE_DIR) / MAKER_DETAIL_TEMPLATE_NAME}"
        )

        print(
            "生成対象メーカー数: "
            f"{len(makers):,}件"
        )

        print("=" * 70)

        # ------------------------------------------
        # メーカー一覧ページ生成
        # ------------------------------------------

        maker_list_context = (
            build_maker_list_context(
                makers=makers,
                generated_at=generated_at,
            )
        )

        maker_list_html = (
            maker_list_template.render(
                **maker_list_context
            )
        )

        MAKER_LIST_OUTPUT_PATH.write_text(
            maker_list_html,
            encoding="utf-8",
            newline="",
        )

        print(
            "[生成] makers/index.html"
            f" - {len(makers):,}メーカー"
        )

        print(
            "  title: "
            f"{maker_list_context['page_title']}"
        )

        print(
            "  canonical: "
            f"{maker_list_context['canonical_url']}"
        )

        # ------------------------------------------
        # メーカー詳細ページ生成
        # ------------------------------------------

        for maker in makers:
            maker_name = str(
                maker.get("name")
                or ""
            ).strip()

            maker_slug = str(
                maker.get("slug")
                or ""
            ).strip()

            if not maker_name:
                error_count += 1

                print(
                    "[スキップ] "
                    "メーカー名が空です。"
                )

                continue

            if not maker_slug:
                error_count += 1

                print(
                    "[スキップ] "
                    f"{maker_name}: slugが空です。"
                )

                continue

            try:
                machines = get_machines_by_maker(
                    connection=connection,
                    maker_name=maker_name,
                )

                maker_output_dir = (
                    OUTPUT_MAKERS_DIR
                    / maker_slug
                )

                maker_output_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                maker_output_path = (
                    maker_output_dir
                    / "index.html"
                )

                context = build_maker_detail_context(
                    maker=maker,
                    machines=machines,
                    generated_at=generated_at,
                )

                html = maker_detail_template.render(
                    **context
                )

                maker_output_path.write_text(
                    html,
                    encoding="utf-8",
                    newline="",
                )

                detail_generated_count += 1
                total_machine_count += len(
                    machines
                )

                print(
                    "[生成] "
                    f"makers/{maker_slug}/index.html"
                    " - "
                    f"{maker_name}"
                    " "
                    f"({len(machines):,}機種)"
                )

            except Exception as error:
                error_count += 1

                print(
                    "[エラー] "
                    f"{maker_name}: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

    elapsed_time = (
        time.time()
        - start_time
    )

    print("=" * 70)

    print(
        "メーカー一覧生成: "
        f"{MAKER_LIST_OUTPUT_PATH}"
    )

    print(
        "メーカー詳細生成成功: "
        f"{detail_generated_count:,}ページ"
    )

    print(
        "生成失敗・スキップ: "
        f"{error_count:,}ページ"
    )

    print(
        "メーカー詳細掲載機種合計: "
        f"{total_machine_count:,}機種"
    )

    print(
        "HTML出力先: "
        f"{OUTPUT_MAKERS_DIR}"
    )

    print(
        "処理時間: "
        f"{elapsed_time:.2f}秒"
    )

    print("=" * 70)


# ==================================================
# 実行
# ==================================================

def main() -> None:
    """
    メーカー一覧・メーカー詳細ページの
    生成処理を実行する。
    """
    try:
        generate_maker_pages()

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

    except Exception as error:
        print("-" * 70)

        print(
            "メーカーページ生成処理で"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


if __name__ == "__main__":
    main()