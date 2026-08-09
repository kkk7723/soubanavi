import os
from collections import defaultdict
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

# 同一メーカーの関連機種表示数
RELATED_MACHINE_LIMIT = 6

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


def related_machine_sort_key(
    machine: dict[str, Any],
) -> tuple[int, int, str]:
    """
    関連機種の並び順を作成する。

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
            related_machine_index[maker_name] = []
            seen_machine_ids[maker_name] = set()

        # 同じメーカー内の機種ID重複を除外
        if machine_id in seen_machine_ids[maker_name]:
            continue

        seen_machine_ids[maker_name].add(
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

    if not maker_name or not current_machine_id:
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

        if len(related_machines) >= limit_value:
            break

    return related_machines

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

    return str(value).strip()


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
        product = row_to_dict(row)

        machine_key = normalize_machine_lookup_key(
            product.get("master_machine_id")
        )

        if not machine_key:
            continue

        products_by_machine[machine_key].append(
            product
        )

    return dict(products_by_machine)


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
        limit_value = int(days)
    except (TypeError, ValueError):
        limit_value = PRICE_HISTORY_DAYS

    if limit_value <= 0:
        limit_value = PRICE_HISTORY_DAYS

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
        history = row_to_dict(row)

        machine_key = normalize_machine_lookup_key(
            history.get("master_machine_id")
        )

        if not machine_key:
            continue

        # テンプレート側では不要なので削除する。
        history.pop(
            "master_machine_id",
            None,
        )

        history_by_machine[machine_key].append(
            history
        )

    return dict(history_by_machine)


# ==================================================
# SEO用テキスト作成
# ==================================================

def format_price_for_seo(
    value: Any,
) -> str:
    """
    SEO文面で使用する価格を整形する。

    数値として扱えない場合や0以下の場合は
    空文字を返す。
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

    return f"{price:,}円"


def build_machine_meta_description(
    machine: dict[str, Any],
    product_count: int,
) -> str:
    """
    機種詳細ページ用のmeta descriptionを作成する。
    """
    machine_name = str(
        machine.get("master_machine_name")
        or ""
    ).strip()

    maker_name = str(
        machine.get("master_machine_maker")
        or ""
    ).strip()

    min_price = format_price_for_seo(
        machine.get("min_price")
    )

    avg_price = format_price_for_seo(
        machine.get("avg_price")
    )

    description_parts: list[str] = []

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

    if len(description_parts) == 1:
        description_parts.append(
            "中古価格、相場、出品情報、価格推移を確認できます"
        )
    else:
        description_parts.append(
            "価格推移や販売店ごとの出品情報を比較できます"
        )

    return "。".join(
        description_parts
    ) + "。"


# ==================================================
# テンプレート用データ作成
# ==================================================

def build_machine_page_context(
    machine: dict[str, Any],
    products: list[dict[str, Any]],
    price_history: list[dict[str, Any]],
    related_machines: list[dict[str, Any]],
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
        machine.get("latest_scraped_at")
        or machine.get("last_seen")
        or machine.get("updated_at")
        or generated_at
    )

    machine_name = str(
        machine.get("master_machine_name")
        or ""
    ).strip()

    machine_file_id = normalize_machine_id(
        machine.get("master_machine_id")
    )

    product_count = len(
        products
    )

    meta_description = (
        build_machine_meta_description(
            machine=machine,
            product_count=product_count,
        )
    )

    static_machine_image_path = (
        Path(PROJECT_ROOT)
        / "static"
        / "img"
        / "machines"
        / f"{machine_file_id}.webp"
    )

    if static_machine_image_path.is_file():
        machine_image_path = (
            f"../img/machines/{machine_file_id}.webp"
        )

        machine_image_og_path = (
            f"/img/machines/{machine_file_id}.webp"
        )
    else:
        machine_image_path = (
            "../img/no_image.webp"
        )

        machine_image_og_path = (
            "/img/no_image.webp"
        )

    canonical_path = (
        f"/machines/{machine_file_id}.html"
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
        description=meta_description,
        canonical_path=canonical_path,
        robots="index,follow",
        og_image=machine_image_og_path,
        og_type="article",
        og_image_alt=(
            f"{machine_name}の実機画像"
        ),
    )

    return {
        # SEO情報
        **seo,

        # SNSシェア用
        "share_url": canonical_url,
        "share_title": share_title,
        "share_text": share_text,

        # 共通テンプレート用
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # パンくずリスト
        "breadcrumbs": (
            create_machine_detail_breadcrumbs(
                machine_name
            )
        ),

        # output/machines/*.htmlから見た相対パス
        "root_prefix": "../",
        "asset_prefix": "../",

        # 機種詳細ページ用
        "machine": machine,
        "machine_image_path": machine_image_path,
        "products": products,
        "lowest_product": lowest_product,
        "product_count": product_count,

        # 関連機種
        "related_machines": related_machines,
        "related_machine_count": len(
            related_machines
        ),

        # 価格推移グラフ用
        "price_history": price_history,

        # 更新日時
        "generated_at": generated_at,
        "updated_at": page_updated_at,
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
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
    )

    copy_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
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
    generated_at = datetime.now()

    OUTPUT_MACHINE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy_machine_detail_static_files()

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

        related_machine_index = (
            build_related_machine_index(
                machines
            )
        )

        # 商品と価格履歴は機種ループの前に一括取得する。
        # これにより、機種ごとのSQL実行をなくす。
        products_by_machine = (
            get_all_products_by_machine(
                connection
            )
        )

        history_by_machine = (
            get_all_price_history_by_machine(
                connection=connection,
                days=PRICE_HISTORY_DAYS,
            )
        )

        print("=" * 70)

        print(
            "使用テンプレート: "
            f"{Path(TEMPLATE_DIR) / TEMPLATE_FILE_NAME}"
        )

        print(
            "ページ生成対象: "
            f"{len(machines):,}機種"
        )

        print("=" * 70)

        for machine in machines:
            master_machine_id = machine.get(
                "master_machine_id"
            )

            machine_file_id = normalize_machine_id(
                master_machine_id
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

                products = products_by_machine.get(
                    machine_lookup_key,
                    [],
                )

                price_history = history_by_machine.get(
                    machine_lookup_key,
                    [],
                )

                related_machines = (
                    get_related_machines(
                        machine=machine,
                        related_machine_index=(
                            related_machine_index
                        ),
                        limit=RELATED_MACHINE_LIMIT,
                    )
                )

                context = build_machine_page_context(
                    machine=machine,
                    products=products,
                    price_history=price_history,
                    related_machines=(
                        related_machines
                    ),
                    generated_at=generated_at,
                )

                html = template.render(
                    **context
                )

                output_file_path = (
                    OUTPUT_MACHINE_DIR
                    / f"{machine_file_id}.html"
                )

                output_file_path.write_text(
                    html,
                    encoding="utf-8",
                    newline="",
                )

                generated_count += 1
                product_total_count += len(
                    products
                )

                machine_image_file_path = (
                    Path(PROJECT_ROOT)
                    / "static"
                    / "img"
                    / "machines"
                    / f"{machine_file_id}.webp"
                )
                
                image_status = (
                    "画像あり"
                    if machine_image_file_path.is_file()
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
                    f"関連{len(related_machines):,}機種 / "
                    f"{image_status})"
                )

            except Exception as error:
                error_count += 1

                print(
                    "[エラー] "
                    f"機種ID: {master_machine_id} "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

        print("=" * 70)

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

        print("-" * 70)

        print(
            "全機種の詳細ページ生成が完了しました。"
        )

        print(
            "処理時間: "
            f"{elapsed_time:.2f}秒"
        )

        print("-" * 70)

    except sqlite3.Error as error:
        print("-" * 70)

        print(
            "SQLite処理でエラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    except Exception as error:
        print("-" * 70)

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