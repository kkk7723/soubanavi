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
    create_machine_list_breadcrumbs,
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

TEMPLATE_FILE_NAME = (
    "machines/machine_index.html"
)

OUTPUT_MACHINE_DIR = (
    Path(OUTPUT_DIR)
    / "machines"
)

OUTPUT_FILE_PATH = (
    OUTPUT_MACHINE_DIR
    / "index.html"
)


# ==================================================
# DBデータ取得
# ==================================================

def get_machines(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """
    machine_masterを起点に、
    product_summaryの価格・出品情報を結合して、
    全機種を取得する。
    """
    machine_master_table = validate_identifier(
        "machine_master"
    )

    summary_table = validate_identifier(
        SUMMARY_TABLE_NAME
    )

    sql = f"""
        SELECT
            m.master_machine_id,
            m.master_machine_category,
            m.master_machine_name,
            m.master_machine_maker,
            m.master_machine_type,
            m.master_machine_gouki,
            m.master_machine_memo,
            m.master_machine_pworld_url,

            s.latest_price,
            s.min_price,
            s.max_price,
            s.avg_price,
            s.median_price,

            COALESCE(
                s.price_count,
                0
            ) AS price_count,

            COALESCE(
                s.shop_count,
                0
            ) AS shop_count,

            s.lowest_shop_name,
            s.lowest_product_url,
            s.first_seen,
            s.last_seen,
            s.latest_scraped_at,

            COALESCE(
                s.created_at,
                m.created_at
            ) AS created_at,

            COALESCE(
                s.updated_at,
                m.updated_at
            ) AS updated_at

        FROM {machine_master_table} AS m

        LEFT JOIN {summary_table} AS s
          ON CAST(
                m.master_machine_id AS TEXT
             )
           = CAST(
                s.master_machine_id AS TEXT
             )

        WHERE m.master_machine_id IS NOT NULL
          AND TRIM(
                CAST(
                    m.master_machine_id AS TEXT
                )
              ) != ''
          AND m.master_machine_name IS NOT NULL
          AND TRIM(
                m.master_machine_name
              ) != ''

        ORDER BY
            m.master_machine_name COLLATE NOCASE ASC,
            CAST(
                m.master_machine_id AS INTEGER
            ) ASC,
            m.master_machine_id ASC
    """

    rows = connection.execute(
        sql
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]
    rows = connection.execute(
        sql
    ).fetchall()

    return [
        row_to_dict(row)
        for row in rows
    ]


# ==================================================
# 選択肢作成
# ==================================================

def get_unique_options(
    machines: list[dict[str, Any]],
    key: str,
) -> list[str]:
    """
    指定したカラムから選択肢を作成する。

    重複、None、空文字を除外し、
    大文字・小文字を区別せず並べ替える。
    """
    option_set: set[str] = set()

    for machine in machines:
        value = machine.get(
            key
        )

        if value is None:
            continue

        option_name = str(
            value
        ).strip()

        if not option_name:
            continue

        option_set.add(
            option_name
        )

    return sorted(
        option_set,
        key=lambda option: option.casefold(),
    )


def get_makers(
    machines: list[dict[str, Any]],
) -> list[str]:
    """
    機種一覧からメーカー一覧を作成する。
    """
    return get_unique_options(
        machines=machines,
        key="master_machine_maker",
    )


def get_machine_type_options(
    machines: list[dict[str, Any]],
) -> list[str]:
    """
    機種一覧から機種タイプの選択肢を作成する。
    """
    return get_unique_options(
        machines=machines,
        key="master_machine_type",
    )

def get_machine_gouki_options(
    machines: list[dict[str, Any]],
) -> list[str]:
    """
    機種一覧から号機の選択肢を作成する。
    """
    return get_unique_options(
        machines=machines,
        key="master_machine_gouki",
    )


# ==================================================
# 更新日時取得
# ==================================================

def parse_datetime_value(
    value: Any,
) -> datetime | None:
    """
    DBから取得した日時を
    比較可能なdatetimeへ変換する。
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.replace(
            tzinfo=None
        )

    value_text = str(
        value
    ).strip()

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
    機種一覧に含まれるデータから
    最も新しい更新日時を取得する。

    テンプレートへはDB内の元の値を返す。
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
                or parsed_datetime > latest_datetime
            ):
                latest_datetime = parsed_datetime
                latest_original_value = original_value

    if latest_original_value is None:
        return default_value

    return latest_original_value


# ==================================================
# テンプレート用データ作成
# ==================================================

def build_machine_list_context(
    machines: list[dict[str, Any]],
    generated_at: datetime,
) -> dict[str, Any]:
    """
    machine_list.htmlへ渡す
    テンプレート変数を作成する。
    """
    makers = get_makers(
        machines
    )

    machine_types = get_machine_type_options(
        machines
    )

    machine_goukis = get_machine_gouki_options(
        machines
    )

    updated_at = get_latest_updated_at(
        machines=machines,
        default_value=generated_at,
    )

    breadcrumbs = (
        create_machine_list_breadcrumbs()
    )

    machine_count = len(
        machines
    )

    maker_count = len(
        makers
    )

    seo = build_seo_data(
        title="パチンコ・パチスロ実機一覧",
        description=(
            f"パチンコ・パチスロ実機{machine_count:,}機種の"
            "中古価格、最安値、平均価格、出品情報を確認できる"
            "機種一覧ページです。"
        ),
        canonical_path="/machines/",
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
        "breadcrumbs": breadcrumbs,

        # output/machines/index.htmlから見た相対パス
        "root_prefix": "../",
        "asset_prefix": "../",

        # 機種一覧ページ用
        "machines": machines,
        "makers": makers,
        "machine_types": machine_types,
        "machine_goukis": machine_goukis,
        "machine_count": machine_count,
        "maker_count": maker_count,

        # 更新日時
        "generated_at": generated_at,
        "updated_at": updated_at,
    }


# ==================================================
# 静的ファイルコピー
# ==================================================

def copy_machine_list_static_files() -> None:
    """
    共通ファイルと機種一覧ページ専用ファイルを
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
            "css/machine_index.css",
            "js/machine_index.js",
        ),
    )


# ==================================================
# HTML生成
# ==================================================

def generate_machine_list_page() -> None:
    """
    templates/machines/machine_list.htmlを使用して、
    output/machines/index.htmlを生成する。

    output/machines内にある
    各機種の詳細ページは変更しない。
    """
    start_time = time.time()
    generated_at = datetime.now()

    OUTPUT_MACHINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy_machine_list_static_files()

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
            "Jinja2テンプレートが見つかりません: "
            f"{error.name}"
        ) from error

    with connect_database(
        DB_PATH
    ) as connection:
        check_table_exists(
            connection,
            "machine_master",
        )
    
        check_table_exists(
            connection,
            SUMMARY_TABLE_NAME,
        )
    
        machines = get_machines(
            connection
        )

    context = build_machine_list_context(
        machines=machines,
        generated_at=generated_at,
    )

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

    print("=" * 70)

    print(
        "機種一覧ページを生成しました。"
    )

    print(
        "使用テンプレート: "
        f"{Path(TEMPLATE_DIR) / TEMPLATE_FILE_NAME}"
    )

    print(
        "HTML出力先: "
        f"{OUTPUT_FILE_PATH}"
    )

    print(
        "共通CSS出力先: "
        f"{Path(OUTPUT_DIR) / 'css' / 'common.css'}"
    )

    print(
        "共通JS出力先: "
        f"{Path(OUTPUT_DIR) / 'js' / 'common.js'}"
    )

    print(
        "一覧CSS出力先: "
        f"{Path(OUTPUT_DIR) / 'css' / 'machine_index.css'}"
    )

    print(
        "掲載機種数: "
        f"{len(machines):,}件"
    )

    print(
        "メーカー数: "
        f"{context['maker_count']:,}件"
    )

    print(
        "機種タイプ数: "
        f"{len(context['machine_types']):,}件"
    )

    print(
        "号機区分数: "
        f"{len(context['machine_goukis']):,}件"
    )

    print(
        "ページタイトル: "
        f"{context['page_title']}"
    )

    print(
        "canonical URL: "
        f"{context['canonical_url']}"
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
    機種一覧ページ生成処理を実行する。
    """
    try:
        generate_machine_list_page()

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
            "機種一覧ページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


if __name__ == "__main__":
    main()