#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sys
import time
import sqlite3

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


# ==================================================
# 初期設定
# ==================================================

start_time = time.time()


# ==================================================
# importパス設定
# ==================================================

# Jupyter・通常スクリプトの両方に対応
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


# ==================================================
# テーブル設定
# ==================================================

SOURCE_TABLE = "product_summary"
HISTORY_TABLE = "price_history"


# 日本時間
JAPAN_TIMEZONE = ZoneInfo(
    "Asia/Tokyo"
)


# ==================================================
# 必要カラム
# ==================================================

SOURCE_REQUIRED_COLUMNS = {
    "master_machine_id",
    "master_machine_name",
    "master_machine_maker",

    "min_price",
    "avg_price",
    "median_price",
    "max_price",
    "latest_price",

    "price_count",
    "shop_count",

    "lowest_shop_name",
    "lowest_product_url",
}


HISTORY_REQUIRED_COLUMNS = {
    "id",
    "master_machine_id",
    "record_date",

    "master_machine_name",
    "master_machine_maker",

    "min_price",
    "avg_price",
    "median_price",
    "max_price",
    "latest_price",

    "price_count",
    "shop_count",

    "lowest_shop_name",
    "lowest_product_url",

    "created_at",
    "updated_at",
}


# ==================================================
# DB確認関数
# ==================================================

def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    """
    指定したテーブルが存在するか確認する。
    """
    row = connection.execute(
        """
        SELECT
            name

        FROM sqlite_master

        WHERE type = 'table'
          AND name = ?
        """,
        (
            table_name,
        ),
    ).fetchone()

    return row is not None


def get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """
    指定したテーブルのカラム名を取得する。
    """
    rows = connection.execute(
        f"""
        PRAGMA table_info("{table_name}")
        """
    ).fetchall()

    return {
        str(row["name"])
        for row in rows
    }


def validate_database(
    connection: sqlite3.Connection,
) -> None:
    """
    必要なテーブルとカラムを確認する。
    """
    if not table_exists(
        connection,
        SOURCE_TABLE,
    ):
        raise RuntimeError(
            f"{SOURCE_TABLE}テーブルが"
            "存在しません。"
        )

    if not table_exists(
        connection,
        HISTORY_TABLE,
    ):
        raise RuntimeError(
            f"{HISTORY_TABLE}テーブルが"
            "存在しません。"
        )

    source_columns = get_table_columns(
        connection,
        SOURCE_TABLE,
    )

    missing_source_columns = (
        SOURCE_REQUIRED_COLUMNS
        - source_columns
    )

    if missing_source_columns:
        raise RuntimeError(
            f"{SOURCE_TABLE}に必要な"
            "カラムがありません: "
            + ", ".join(
                sorted(
                    missing_source_columns
                )
            )
        )

    history_columns = get_table_columns(
        connection,
        HISTORY_TABLE,
    )

    missing_history_columns = (
        HISTORY_REQUIRED_COLUMNS
        - history_columns
    )

    if missing_history_columns:
        raise RuntimeError(
            f"{HISTORY_TABLE}に必要な"
            "カラムがありません: "
            + ", ".join(
                sorted(
                    missing_history_columns
                )
            )
        )


# ==================================================
# UNIQUE制約確認
# ==================================================

def has_machine_date_unique_index(
    connection: sqlite3.Connection,
) -> bool:
    """
    price_historyに次のUNIQUE制約が
    存在するか確認する。

    master_machine_id
    record_date
    """
    index_rows = connection.execute(
        f"""
        PRAGMA index_list("{HISTORY_TABLE}")
        """
    ).fetchall()

    for index_row in index_rows:
        is_unique = int(
            index_row["unique"]
        )

        if is_unique != 1:
            continue

        index_name = str(
            index_row["name"]
        )

        column_rows = connection.execute(
            f"""
            PRAGMA index_info("{index_name}")
            """
        ).fetchall()

        index_columns = [
            str(row["name"])
            for row in column_rows
        ]

        if index_columns == [
            "master_machine_id",
            "record_date",
        ]:
            return True

    return False


def validate_unique_constraint(
    connection: sqlite3.Connection,
) -> None:
    """
    ON CONFLICTに必要なUNIQUE制約を確認する。
    """
    if has_machine_date_unique_index(
        connection
    ):
        return

    raise RuntimeError(
        "price_historyに次のUNIQUE制約が"
        "設定されていません:\n"
        "UNIQUE("
        "master_machine_id, "
        "record_date"
        ")"
    )


# ==================================================
# データ件数取得
# ==================================================

def get_source_machine_count(
    connection: sqlite3.Connection,
) -> int:
    """
    price_historyへの保存対象件数を取得する。
    """
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS machine_count

        FROM "{SOURCE_TABLE}"

        WHERE master_machine_id IS NOT NULL

          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''

          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''

          AND price_count IS NOT NULL
          AND price_count > 0

          AND (
                min_price IS NOT NULL
                OR avg_price IS NOT NULL
                OR median_price IS NOT NULL
                OR max_price IS NOT NULL
                OR latest_price IS NOT NULL
              )
        """
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["machine_count"]
        or 0
    )


def get_existing_history_count(
    connection: sqlite3.Connection,
    record_date: str,
) -> int:
    """
    指定日の保存済み履歴件数を取得する。
    """
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS history_count

        FROM "{HISTORY_TABLE}"

        WHERE record_date = ?
        """,
        (
            record_date,
        ),
    ).fetchone()

    if row is None:
        return 0

    return int(
        row["history_count"]
        or 0
    )


# ==================================================
# 価格履歴保存
# ==================================================

def save_daily_price_history(
    connection: sqlite3.Connection,
    record_date: str,
    current_datetime: str,
) -> int:
    """
    product_summaryの集計値を
    price_historyへ保存する。

    同じ機種・同じ日付が存在する場合は
   現在の集計値で更新する。
    """
    changes_before = (
        connection.total_changes
    )

    connection.execute(
        f"""
        INSERT INTO "{HISTORY_TABLE}" (
            master_machine_id,
            record_date,

            master_machine_name,
            master_machine_maker,

            min_price,
            avg_price,
            median_price,
            max_price,
            latest_price,

            price_count,
            shop_count,

            lowest_shop_name,
            lowest_product_url,

            created_at,
            updated_at
        )

        SELECT
            CAST(
                master_machine_id AS TEXT
            ) AS master_machine_id,

            ? AS record_date,

            master_machine_name,
            master_machine_maker,

            CASE
                WHEN min_price > 0
                THEN CAST(min_price AS INTEGER)
                ELSE NULL
            END AS min_price,

            CASE
                WHEN avg_price > 0
                THEN CAST(avg_price AS REAL)
                ELSE NULL
            END AS avg_price,

            CASE
                WHEN median_price > 0
                THEN CAST(median_price AS REAL)
                ELSE NULL
            END AS median_price,

            CASE
                WHEN max_price > 0
                THEN CAST(max_price AS INTEGER)
                ELSE NULL
            END AS max_price,

            CASE
                WHEN latest_price > 0
                THEN CAST(latest_price AS INTEGER)
                ELSE NULL
            END AS latest_price,

            COALESCE(
                CAST(price_count AS INTEGER),
                0
            ) AS price_count,

            COALESCE(
                CAST(shop_count AS INTEGER),
                0
            ) AS shop_count,

            lowest_shop_name,
            lowest_product_url,

            ? AS created_at,
            ? AS updated_at

        FROM "{SOURCE_TABLE}"

        WHERE master_machine_id IS NOT NULL

          AND TRIM(
                CAST(
                    master_machine_id AS TEXT
                )
              ) != ''

          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''

          AND price_count IS NOT NULL
          AND price_count > 0

          AND (
                min_price IS NOT NULL
                OR avg_price IS NOT NULL
                OR median_price IS NOT NULL
                OR max_price IS NOT NULL
                OR latest_price IS NOT NULL
              )

        ON CONFLICT (
            master_machine_id,
            record_date
        )

        DO UPDATE SET
            master_machine_name =
                excluded.master_machine_name,

            master_machine_maker =
                excluded.master_machine_maker,

            min_price =
                excluded.min_price,

            avg_price =
                excluded.avg_price,

            median_price =
                excluded.median_price,

            max_price =
                excluded.max_price,

            latest_price =
                excluded.latest_price,

            price_count =
                excluded.price_count,

            shop_count =
                excluded.shop_count,

            lowest_shop_name =
                excluded.lowest_shop_name,

            lowest_product_url =
                excluded.lowest_product_url,

            updated_at =
                excluded.updated_at
        """,
        (
            record_date,
            current_datetime,
            current_datetime,
        ),
    )

    return (
        connection.total_changes
        - changes_before
    )


# ==================================================
# 保存結果確認
# ==================================================

def get_saved_price_summary(
    connection: sqlite3.Connection,
    record_date: str,
) -> dict[str, Any]:
    """
    指定日の価格履歴集計結果を取得する。
    """
    row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS machine_count,

            COUNT(min_price)
                AS min_price_count,

            COUNT(avg_price)
                AS avg_price_count,

            COUNT(median_price)
                AS median_price_count,

            COUNT(max_price)
                AS max_price_count,

            COALESCE(
                MIN(min_price),
                0
            ) AS lowest_price,

            COALESCE(
                MAX(max_price),
                0
            ) AS highest_price

        FROM "{HISTORY_TABLE}"

        WHERE record_date = ?
        """,
        (
            record_date,
        ),
    ).fetchone()

    if row is None:
        return {
            "machine_count": 0,
            "min_price_count": 0,
            "avg_price_count": 0,
            "median_price_count": 0,
            "max_price_count": 0,
            "lowest_price": 0,
            "highest_price": 0,
        }

    return dict(row)


# ==================================================
# メイン処理
# ==================================================

def update_price_history() -> None:
    """
    当日の価格履歴を保存する。
    """
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            "データベースが"
            "見つかりません: "
            f"{DB_PATH}"
        )

    now = datetime.now(
        JAPAN_TIMEZONE
    )

    record_date = now.strftime(
        "%Y-%m-%d"
    )

    current_datetime = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    connection = sqlite3.connect(
        DB_PATH,
        timeout=60,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    try:
        # 外部キー制約を有効化
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        # DBの書き込み待機時間
        connection.execute(
            "PRAGMA busy_timeout = 60000"
        )

        validate_database(
            connection
        )

        validate_unique_constraint(
            connection
        )

        source_machine_count = (
            get_source_machine_count(
                connection
            )
        )

        existing_count_before = (
            get_existing_history_count(
                connection,
                record_date,
            )
        )

        if source_machine_count == 0:
            print(
                "price_historyへ保存できる"
                "価格データがありません。"
            )
            return

        connection.execute(
            "BEGIN IMMEDIATE"
        )

        changed_count = (
            save_daily_price_history(
                connection,
                record_date,
                current_datetime,
            )
        )

        connection.commit()

        existing_count_after = (
            get_existing_history_count(
                connection,
                record_date,
            )
        )

        inserted_count = max(
            existing_count_after
            - existing_count_before,
            0,
        )

        updated_count = max(
            changed_count
            - inserted_count,
            0,
        )

        summary = (
            get_saved_price_summary(
                connection,
                record_date,
            )
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    elapsed_time = (
        time.time()
        - start_time
    )

    print("=" * 60)
    print(
        "price_historyへの"
        "日次集計が完了しました。"
    )
    print("-" * 60)

    print(
        "DB: "
        f"{DB_PATH}"
    )

    print(
        "集計日: "
        f"{record_date}"
    )

    print(
        "実行日時: "
        f"{current_datetime}"
    )

    print(
        "保存対象機種数: "
        f"{source_machine_count:,}件"
    )

    print(
        "当日保存済み件数（実行前）: "
        f"{existing_count_before:,}件"
    )

    print(
        "新規保存件数: "
        f"{inserted_count:,}件"
    )

    print(
        "更新件数: "
        f"{updated_count:,}件"
    )

    print(
        "当日の履歴件数: "
        f"{summary['machine_count']:,}件"
    )

    print(
        "最安価格あり: "
        f"{summary['min_price_count']:,}件"
    )

    print(
        "平均価格あり: "
        f"{summary['avg_price_count']:,}件"
    )

    print(
        "中央値あり: "
        f"{summary['median_price_count']:,}件"
    )

    print(
        "最高価格あり: "
        f"{summary['max_price_count']:,}件"
    )

    print(
        "当日の最低価格: "
        f"{int(summary['lowest_price'] or 0):,}円"
    )

    print(
        "当日の最高価格: "
        f"{int(summary['highest_price'] or 0):,}円"
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
        update_price_history()

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
            "価格履歴の集計中に"
            "エラーが発生しました。"
        )
        print(
            f"{type(error).__name__}: "
            f"{error}"
        )
        raise


# In[ ]:




