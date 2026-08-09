#!/usr/bin/env python
# coding: utf-8

# In[3]:


import os
import sys
import time
import sqlite3
import statistics

from collections import defaultdict
from datetime import datetime


# ==================
# 初期設定
# ==================

start_time = time.time()
now = datetime.now()


# ==================
# importパス設定
# ==================

# Jupyter・通常のPythonスクリプトの両方に対応
try:
    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )
except NameError:
    base_dir = os.getcwd()


# 現在位置:
# soubanavi/scripts/database/
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


from utils.config import (
    DB_PATH,
)


# ==================
# DB設定
# ==================

# 集計元テーブル
TABLE_NAME = "result_table"

# 集計先テーブル
SUMMARY_TABLE_NAME = "product_summary"


# ==================
# 補助関数
# ==================

def normalize_text(value):
    """
    Noneを空文字へ変換し、
    前後の空白を削除する。
    """
    if value is None:
        return ""

    return str(value).strip()


def normalize_category(value):
    """
    categoryを正規化する。

    戻り値:
        pachi
        slot
        None

    想定外の値はNoneを返す。
    """
    text = normalize_text(
        value
    ).lower()

    if not text:
        return None

    category_mapping = {
        "pachi": "pachi",
        "pachinko": "pachi",
        "パチンコ": "pachi",
        "ぱちんこ": "pachi",

        "slot": "slot",
        "pachislot": "slot",
        "pachislo": "slot",
        "パチスロ": "slot",
        "ぱちすろ": "slot",
        "スロット": "slot",
    }

    return category_mapping.get(
        text
    )


def normalize_price(value):
    """
    DBの価格を整数へ変換する。

    0以下、空文字、変換できない値は
    Noneを返す。
    """
    if value is None:
        return None

    try:
        # "198,000" のような値にも対応
        text = str(value).replace(
            ",",
            "",
        ).strip()

        if not text:
            return None

        price = int(
            float(text)
        )

        if price <= 0:
            return None

        return price

    except (TypeError, ValueError):
        return None


def parse_datetime(value):
    """
    SQLite内の日付文字列を
    datetimeへ変換する。

    対応例:
    2026-07-21
    2026-07-21 10:30:00
    2026-07-21T10:30:00
    2026-07-21T10:30:00+09:00
    """
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    # ISO形式を優先
    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(
                text,
                date_format,
            )
        except ValueError:
            continue

    return None


def format_datetime(value):
    """
    datetimeをSQLite用の文字列へ
    変換する。
    """
    if value is None:
        return None

    return value.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_table_columns(
    cursor,
    target_table,
):
    """
    テーブルに存在するカラム名を
    取得する。
    """
    cursor.execute(
        f"PRAGMA table_info({target_table})"
    )

    return {
        row[1]
        for row in cursor.fetchall()
    }


def ensure_summary_category_column(
    cursor,
):
    """
    product_summaryにcategory列がなければ
   追加する。
    """
    summary_columns = get_table_columns(
        cursor,
        SUMMARY_TABLE_NAME,
    )

    if "category" in summary_columns:
        return

    cursor.execute(
        f"""
        ALTER TABLE {SUMMARY_TABLE_NAME}
        ADD COLUMN category TEXT
        """
    )

    print(
        "[カラム追加] "
        f"{SUMMARY_TABLE_NAME}.category"
    )


def get_record_datetime(row):
    """
    行の確認日時を取得する。

    scraped_dateを優先し、
    空の場合はupdated_at、
    created_atの順で使用する。
    """
    for key in (
        "scraped_date",
        "updated_at",
        "created_at",
    ):
        value = row.get(key)

        parsed = parse_datetime(
            value
        )

        if parsed is not None:
            return parsed

    return None


def get_latest_non_empty(
    rows,
    column_name,
):
    """
    最新行から最初に見つかった
    空でない値を返す。
    """
    if not column_name:
        return None

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            get_record_datetime(row)
            or datetime.min,

            row.get("id") or 0,
        ),
        reverse=True,
    )

    for row in sorted_rows:
        value = normalize_text(
            row.get(column_name)
        )

        if value:
            return value

    return None


def get_latest_category(
    rows,
):
    """
    最新行から、最初に見つかった
    有効なcategoryを返す。

    戻り値:
        pachi
        slot
        None
    """
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            get_record_datetime(row)
            or datetime.min,

            row.get("id") or 0,
        ),
        reverse=True,
    )

    for row in sorted_rows:
        category = normalize_category(
            row.get("category")
        )

        if category:
            return category

    return None


# ==================
# 集計処理
# ==================

def aggregate_product_summary():
    """
    result_tableを
    master_machine_id単位で集計し、
    product_summaryへUPSERTする。

    categoryについては、
    各機種の最新の有効な値を
    product_summaryへ保存する。

    categoryの保存値:
        pachi
        slot
    """
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            "データベースが見つかりません: "
            f"{DB_PATH}"
        )

    conn = sqlite3.connect(
        DB_PATH
    )

    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (?, ?)
            """,
            (
                TABLE_NAME,
                SUMMARY_TABLE_NAME,
            ),
        )

        existing_tables = {
            row["name"]
            for row in cursor.fetchall()
        }

        if TABLE_NAME not in existing_tables:
            raise RuntimeError(
                f"{TABLE_NAME}が存在しません。"
            )

        if SUMMARY_TABLE_NAME not in existing_tables:
            raise RuntimeError(
                f"{SUMMARY_TABLE_NAME}"
                "が存在しません。"
            )

        # product_summaryにcategory列がなければ追加
        ensure_summary_category_column(
            cursor
        )

        source_columns = get_table_columns(
            cursor,
            TABLE_NAME,
        )

        summary_columns = get_table_columns(
            cursor,
            SUMMARY_TABLE_NAME,
        )

        # ==================
        # 必須カラム確認
        # ==================

        required_source_columns = {
            "id",
            "category",
            "master_machine_id",
            "master_machine_name",
            "master_machine_maker",
            "master_machine_model",
            "master_machine_type",
            "master_machine_gouki",
            "master_machine_memo",
            "master_machine_introduced_date",            
            "master_machine_game_system",
            "master_machine_pworld_url",
            "master_machine_pworld_image_url",
            "price",
            "shop_name",
            "product_url",
        }

        missing_source_columns = (
            required_source_columns
            - source_columns
        )

        if missing_source_columns:
            raise RuntimeError(
                "result_tableに必要な"
                "カラムがありません: "
                + ", ".join(
                    sorted(
                        missing_source_columns
                    )
                )
            )

        required_summary_columns = {
            "category",
            "master_machine_id",
            "master_machine_name",
            "master_machine_maker",
            "master_machine_model",
            "master_machine_type",
            "master_machine_gouki",
            "master_machine_memo",
            "master_machine_introduced_date",            
            "master_machine_game_system",            
            "master_machine_pworld_url",
            "master_machine_pworld_image_url",
            "latest_price",
            "min_price",
            "max_price",
            "avg_price",
            "median_price",
            "price_count",
            "shop_count",
            "lowest_shop_name",
            "lowest_product_url",
            "first_seen",
            "last_seen",
            "latest_scraped_at",
            "created_at",
            "updated_at",
        }

        missing_summary_columns = (
            required_summary_columns
            - summary_columns
        )

        if missing_summary_columns:
            raise RuntimeError(
                "product_summaryに必要な"
                "カラムがありません: "
                + ", ".join(
                    sorted(
                        missing_summary_columns
                    )
                )
            )

        # ==================
        # 日付カラム確認
        # ==================

        scraped_date_column = (
            "scraped_date"
            if "scraped_date" in source_columns
            else None
        )

        created_at_column = (
            "created_at"
            if "created_at" in source_columns
            else None
        )

        updated_at_column = (
            "updated_at"
            if "updated_at" in source_columns
            else None
        )

        # ==================
        # インデックス作成
        # ==================

        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS
            idx_{TABLE_NAME}_master_machine_id
            ON {TABLE_NAME}(master_machine_id)
            """
        )

        cursor.execute(
            f"""
            CREATE INDEX IF NOT EXISTS
            idx_{SUMMARY_TABLE_NAME}_category
            ON {SUMMARY_TABLE_NAME}(category)
            """
        )

        # ==================
        # 集計元データ取得
        # ==================

        select_columns = [
            "id",
            "category",
            "master_machine_id",
            "master_machine_name",
            "master_machine_maker",
            "master_machine_model",
            "master_machine_type",
            "master_machine_gouki",
            "master_machine_memo",
            "master_machine_introduced_date",
            "master_machine_game_system",
            "master_machine_pworld_url",
            "master_machine_pworld_image_url",
            "price",
            "shop_name",
            "product_url",
        ]

        if scraped_date_column:
            select_columns.append(
                f"{scraped_date_column} "
                "AS scraped_date"
            )
        else:
            select_columns.append(
                "NULL AS scraped_date"
            )

        if created_at_column:
            select_columns.append(
                f"{created_at_column} "
                "AS created_at"
            )
        else:
            select_columns.append(
                "NULL AS created_at"
            )

        if updated_at_column:
            select_columns.append(
                f"{updated_at_column} "
                "AS updated_at"
            )
        else:
            select_columns.append(
                "NULL AS updated_at"
            )

        select_sql = f"""
            SELECT
                {", ".join(select_columns)}

            FROM {TABLE_NAME}

            WHERE master_machine_id IS NOT NULL
              AND TRIM(
                    CAST(
                        master_machine_id
                        AS TEXT
                    )
                  ) != ''
        """

        cursor.execute(
            select_sql
        )

        source_rows = [
            dict(row)
            for row in cursor.fetchall()
        ]

        print(
            "集計対象データ: "
            f"{len(source_rows):,}件"
        )

        # ==================
        # category元データ確認
        # ==================

        source_category_counts = defaultdict(
            int
        )

        for row in source_rows:
            original_category = normalize_text(
                row.get("category")
            )

            display_category = (
                original_category
                if original_category
                else "(空)"
            )

            source_category_counts[
                display_category
            ] += 1

        print(
            "result_table category内訳:"
        )

        for (
            category_name,
            category_count,
        ) in sorted(
            source_category_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(
                f"  {category_name}: "
                f"{category_count:,}件"
            )

        # ==================
        # 機種IDごとに分類
        # ==================

        grouped_rows = defaultdict(
            list
        )

        for row in source_rows:
            master_machine_id = row.get(
                "master_machine_id"
            )

            grouped_rows[
                master_machine_id
            ].append(row)

        print(
            "集計対象機種: "
            f"{len(grouped_rows):,}機種"
        )

        # ==================
        # UPSERT文
        # ==================

        upsert_sql = f"""
            INSERT INTO {SUMMARY_TABLE_NAME} (
                master_machine_id,
                category,
                master_machine_name,
                master_machine_maker,
                master_machine_model,
                master_machine_type,
                master_machine_gouki,
                master_machine_memo,
                master_machine_introduced_date,
                master_machine_game_system,
                master_machine_pworld_url,
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
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?
            )

            ON CONFLICT(master_machine_id)
            DO UPDATE SET
                category =
                    CASE
                        WHEN
                            excluded.category IS NOT NULL
                            AND TRIM(
                                excluded.category
                            ) != ''
                        THEN
                            excluded.category

                        ELSE
                            {SUMMARY_TABLE_NAME}
                            .category
                    END,

                master_machine_name =
                    excluded.master_machine_name,

                master_machine_maker =
                    excluded.master_machine_maker,

                master_machine_model =
                    excluded.master_machine_model,

                master_machine_type =
                    excluded.master_machine_type,

                master_machine_gouki =
                    excluded.master_machine_gouki,

                master_machine_memo =
                    excluded.master_machine_memo,

                master_machine_introduced_date =
                    excluded.master_machine_introduced_date,

                master_machine_game_system =
                    excluded.master_machine_game_system,

                master_machine_pworld_url =
                    excluded.master_machine_pworld_url,

                master_machine_pworld_image_url =
                    excluded.master_machine_pworld_image_url,

                latest_price =
                    excluded.latest_price,

                min_price =
                    excluded.min_price,

                max_price =
                    excluded.max_price,

                avg_price =
                    excluded.avg_price,

                median_price =
                    excluded.median_price,

                price_count =
                    excluded.price_count,

                shop_count =
                    excluded.shop_count,

                lowest_shop_name =
                    excluded.lowest_shop_name,

                lowest_product_url =
                    excluded.lowest_product_url,

                first_seen =
                    CASE
                        WHEN
                            {SUMMARY_TABLE_NAME}
                            .first_seen IS NULL
                        THEN
                            excluded.first_seen

                        WHEN
                            excluded.first_seen
                            IS NULL
                        THEN
                            {SUMMARY_TABLE_NAME}
                            .first_seen

                        WHEN
                            excluded.first_seen
                            <
                            {SUMMARY_TABLE_NAME}
                            .first_seen
                        THEN
                            excluded.first_seen

                        ELSE
                            {SUMMARY_TABLE_NAME}
                            .first_seen
                    END,

                last_seen =
                    excluded.last_seen,

                latest_scraped_at =
                    excluded.latest_scraped_at,

                updated_at =
                    excluded.updated_at
        """

        current_time_text = now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        summary_values = []

        skipped_count = 0
        category_empty_count = 0

        summary_category_counts = defaultdict(
            int
        )

        # ==================
        # 機種単位の集計
        # ==================

        for (
            master_machine_id,
            rows,
        ) in grouped_rows.items():

            # 有効価格がある行だけ抽出
            price_rows = []

            for row in rows:
                price = normalize_price(
                    row.get("price")
                )

                if price is None:
                    continue

                copied_row = row.copy()

                copied_row[
                    "_normalized_price"
                ] = price

                price_rows.append(
                    copied_row
                )

            # 価格が1件もない機種は登録しない
            if not price_rows:
                skipped_count += 1
                continue

            prices = [
                row["_normalized_price"]
                for row in price_rows
            ]

            min_price = min(
                prices
            )

            max_price = max(
                prices
            )

            avg_price = (
                sum(prices)
                / len(prices)
            )

            # product_summary側が
            # INTEGERの場合に対応して整数化
            median_price = int(
                statistics.median(
                    prices
                )
            )

            price_count = len(
                prices
            )

            # 空文字を除外して店舗数を取得
            shop_names = {
                normalize_text(
                    row.get("shop_name")
                )
                for row in price_rows
                if normalize_text(
                    row.get("shop_name")
                )
            }

            shop_count = len(
                shop_names
            )

            # 日付とIDで並べ替え
            sorted_price_rows = sorted(
                price_rows,
                key=lambda row: (
                    get_record_datetime(row)
                    or datetime.min,

                    row.get("id") or 0,
                ),
                reverse=True,
            )

            latest_row = (
                sorted_price_rows[0]
            )

            latest_price = latest_row[
                "_normalized_price"
            ]

            # 最安値が同額の場合は
            # 最新行を採用
            lowest_candidates = [
                row
                for row in price_rows
                if row["_normalized_price"]
                == min_price
            ]

            lowest_row = max(
                lowest_candidates,
                key=lambda row: (
                    get_record_datetime(row)
                    or datetime.min,

                    row.get("id") or 0,
                ),
            )

            lowest_shop_name = (
                normalize_text(
                    lowest_row.get(
                        "shop_name"
                    )
                )
                or None
            )

            lowest_product_url = (
                normalize_text(
                    lowest_row.get(
                        "product_url"
                    )
                )
                or None
            )

            # ==================
            # 日時情報
            # ==================

            record_datetimes = [
                get_record_datetime(row)
                for row in rows
            ]

            record_datetimes = [
                value
                for value in record_datetimes
                if value is not None
            ]

            if record_datetimes:
                first_seen = min(
                    record_datetimes
                )

                last_seen = max(
                    record_datetimes
                )
            else:
                first_seen = now
                last_seen = now

            scraped_datetimes = [
                parse_datetime(
                    row.get("scraped_date")
                )
                for row in rows
            ]

            scraped_datetimes = [
                value
                for value in scraped_datetimes
                if value is not None
            ]

            if scraped_datetimes:
                latest_scraped_at = max(
                    scraped_datetimes
                )
            else:
                latest_scraped_at = (
                    last_seen
                )

            # ==================
            # category
            # ==================

            category = get_latest_category(
                rows
            )

            if category:
                summary_category_counts[
                    category
                ] += 1
            else:
                category_empty_count += 1
                summary_category_counts[
                    "(空)"
                ] += 1

            # ==================
            # 機種マスタ情報
            # ==================

            master_machine_name = (
                get_latest_non_empty(
                    rows,
                    "master_machine_name",
                )
            )

            master_machine_maker = (
                get_latest_non_empty(
                    rows,
                    "master_machine_maker",
                )
            )

            master_machine_model = (
                get_latest_non_empty(
                    rows,
                    "master_machine_model",
                )
            )

            master_machine_type = (
                get_latest_non_empty(
                    rows,
                    "master_machine_type",
                )
            )

            master_machine_gouki = (
                get_latest_non_empty(
                    rows,
                    "master_machine_gouki",
                )
            )

            master_machine_memo = (
                get_latest_non_empty(
                    rows,
                    "master_machine_memo",
                )
            )


            master_machine_game_system = (
                get_latest_non_empty(
                    rows,
                    "master_machine_game_system",
                )
            )
    
            master_machine_introduced_date = (
                get_latest_non_empty(
                    rows,
                    "master_machine_introduced_date",
                )
            )

            master_machine_pworld_url = (
                get_latest_non_empty(
                    rows,
                    "master_machine_pworld_url",
                )
            )

            master_machine_pworld_image_url = (
                get_latest_non_empty(
                    rows,
                    "master_machine_pworld_image_url",
                )
            )

            summary_values.append(
                (
                    master_machine_id,
                    category,
                    master_machine_name,
                    master_machine_maker,
                    master_machine_model,
                    master_machine_type,
                    master_machine_gouki,
                    master_machine_memo,
                    master_machine_introduced_date,
                    master_machine_game_system,
                    master_machine_pworld_url,
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
                    format_datetime(
                        first_seen
                    ),
                    format_datetime(
                        last_seen
                    ),
                    format_datetime(
                        latest_scraped_at
                    ),
                    current_time_text,
                    current_time_text,
                )
            )

        # ==================
        # DB登録
        # ==================

        if summary_values:
            cursor.executemany(
                upsert_sql,
                summary_values,
            )

        conn.commit()

        print(
            "product_summary更新: "
            f"{len(summary_values):,}機種"
        )

        if skipped_count:
            print(
                "価格なしのため除外: "
                f"{skipped_count:,}機種"
            )

        if category_empty_count:
            print(
                "categoryを取得できなかった機種: "
                f"{category_empty_count:,}機種"
            )

        print(
            "集計後category内訳:"
        )

        for (
            category_name,
            category_count,
        ) in sorted(
            summary_category_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):
            print(
                f"  {category_name}: "
                f"{category_count:,}機種"
            )

        # ==================
        # 更新結果確認
        # ==================

        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM {SUMMARY_TABLE_NAME}
            """
        )

        total_summary_count = (
            cursor.fetchone()[0]
        )

        print(
            "product_summary総件数: "
            f"{total_summary_count:,}件"
        )

        cursor.execute(
            f"""
            SELECT
                COALESCE(
                    NULLIF(
                        TRIM(category),
                        ''
                    ),
                    '(空)'
                ) AS category_name,

                COUNT(*) AS machine_count

            FROM {SUMMARY_TABLE_NAME}

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM(category),
                        ''
                    ),
                    '(空)'
                )

            ORDER BY
                machine_count DESC
            """
        )

        print(
            "product_summary category確認:"
        )

        for row in cursor.fetchall():
            print(
                f"  {row['category_name']}: "
                f"{int(row['machine_count'] or 0):,}機種"
            )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ==================
# 実行
# ==================

if __name__ == "__main__":
    try:
        aggregate_product_summary()

        elapsed_time = (
            time.time()
            - start_time
        )

        print("-" * 50)

        print(
            "集計処理が完了しました。"
        )

        print(
            "処理時間: "
            f"{elapsed_time:.2f}秒"
        )

        print(
            f"DB: {DB_PATH}"
        )

    except Exception as error:
        print("-" * 50)

        print(
            "集計処理で"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


# In[ ]:




