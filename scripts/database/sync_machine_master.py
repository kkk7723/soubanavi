#!/usr/bin/env python
# coding: utf-8

# In[7]:


import os
import re
import sys
import time
import sqlite3

from datetime import datetime
from typing import Any

import gspread

from google.oauth2.service_account import (
    Credentials,
)


# ==================================================
# 初期設定
# ==================================================

START_TIME = time.time()

TABLE_NAME = "machine_master"

SHEET_NAMES = (
    "slot",
    "pachi",
)

# 3行目:
# DBカラム名
#
# 4行目以降:
# データ
HEADER_ROW = 3
DATA_START_ROW = 4

# 取得する最終列
SHEET_LAST_COLUMN = "AZ"

# 取得する最終行
SHEET_LAST_ROW = 20000

# スプレッドシート側で必須のカラム
REQUIRED_COLUMNS = {
    "master_machine_id",
    "master_machine_name",
}

# DB側で自動設定するカラム
DB_MANAGED_COLUMNS = {
    "id",
    "master_machine_category",
    "source_sheet_row",
    "created_at",
    "updated_at",
}


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


# ==================================================
# config読み込み
# ==================================================

from utils.config import (
    DB_PATH,
    GSPREAD_CREDENTIALS_PATH,
    GSHEET_NAME,
)


# ==================================================
# 共通ユーティリティ
# ==================================================

def clean_value(
    value: Any,
) -> str | None:
    """
    スプレッドシートの値を
    DB登録用に整形する。

    空文字はNoneへ変換する。
    """
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    return text


def get_row_value(
    row: list[Any],
    index: int,
) -> str | None:
    """
    行データから安全に値を取得する。
    """
    if index < 0:
        return None

    if index >= len(row):
        return None

    return clean_value(
        row[index]
    )


def validate_identifier(
    identifier: str,
) -> str:
    """
    SQLiteのテーブル名・カラム名として
    安全な形式か確認する。

    使用可能:
    ・英字
    ・数字
    ・アンダースコア

    先頭:
    ・英字
    ・アンダースコア
    """
    normalized = str(
        identifier
    ).strip()

    if not normalized:
        raise ValueError(
            "空の識別子があります。"
        )

    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*",
        normalized,
    ):
        raise ValueError(
            "DBのテーブル名・カラム名には"
            "英数字とアンダースコアのみ"
            "使用してください: "
            f"{normalized}"
        )

    return normalized


def quote_identifier(
    identifier: str,
) -> str:
    """
    SQLite識別子を
    ダブルクォートで囲む。
    """
    validated = validate_identifier(
        identifier
    )

    return f'"{validated}"'


# ==================================================
# Google Sheets接続
# ==================================================

def connect_google_sheets() -> gspread.Client:
    """
    utils.configの
    GSPREAD_CREDENTIALS_PATHを使用して
    Google Sheetsへ接続する。
    """
    scopes = [
        (
            "https://www.googleapis.com/auth/"
            "spreadsheets.readonly"
        ),
        (
            "https://www.googleapis.com/auth/"
            "drive.readonly"
        ),
    ]

    credentials = (
        Credentials.from_service_account_file(
            str(
                GSPREAD_CREDENTIALS_PATH
            ),
            scopes=scopes,
        )
    )

    return gspread.authorize(
        credentials
    )


# ==================================================
# DBテーブル情報
# ==================================================

def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    """
    指定テーブルが存在するか確認する。
    """
    row = connection.execute(
        """
        SELECT
            1

        FROM sqlite_master

        WHERE type = 'table'
          AND name = ?

        LIMIT 1
        """,
        (
            table_name,
        ),
    ).fetchone()

    return row is not None


def get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> list[str]:
    """
    SQLiteテーブルのカラム名一覧を取得する。
    """
    safe_table_name = quote_identifier(
        table_name
    )

    rows = connection.execute(
        f"""
        PRAGMA table_info(
            {safe_table_name}
        )
        """
    ).fetchall()

    return [
        str(
            row[1]
        ).strip()
        for row in rows
    ]


# ==================================================
# シート見出し取得
# ==================================================

def parse_sheet_headers(
    raw_headers: list[Any],
    sheet_name: str,
) -> tuple[
    list[str],
    list[int],
]:
    """
    スプレッドシート3行目から、
    同期対象のDBカラム名と列番号を取得する。

    3行目が空欄の列は同期対象外とする。

    日本語などDBカラム名として使えない
    見出しは警告を出して無視する。
    """
    headers: list[str] = []

    header_indexes: list[int] = []

    seen_headers: set[str] = set()

    for index, raw_header in enumerate(
        raw_headers
    ):
        header_text = str(
            raw_header
            or ""
        ).strip()

        # 3行目が空欄の列は同期しない。
        if not header_text:
            continue

        # 日本語見出しなど、
        # DBカラム名として使用できない列は無視する。
        try:
            column_name = validate_identifier(
                header_text
            )

        except ValueError:
            print(
                "[WARN] 同期対象外: "
                f"{sheet_name}シート "
                f"{HEADER_ROW}行目 "
                f"{index + 1}列目 "
                f"見出し={header_text}"
            )

            continue

        if column_name in seen_headers:
            raise ValueError(
                f"{sheet_name}シートの"
                f"{HEADER_ROW}行目に"
                "重複カラム名があります: "
                f"{column_name}"
            )

        seen_headers.add(
            column_name
        )

        headers.append(
            column_name
        )

        header_indexes.append(
            index
        )

    if not headers:
        raise RuntimeError(
            f"{sheet_name}シートの"
            f"{HEADER_ROW}行目から"
            "有効なDBカラム名を"
            "取得できませんでした。"
        )

    missing_required_columns = (
        REQUIRED_COLUMNS
        - set(
            headers
        )
    )

    if missing_required_columns:
        raise ValueError(
            f"{sheet_name}シートに"
            "必須カラムがありません: "
            + ", ".join(
                sorted(
                    missing_required_columns
                )
            )
        )

    return (
        headers,
        header_indexes,
    )


# ==================================================
# 1シート分のデータ取得
# ==================================================

def get_sheet_records(
    worksheet: gspread.Worksheet,
    sheet_name: str,
) -> tuple[
    list[str],
    list[dict[str, Any]],
]:
    """
    1つのワークシートから
    機種マスターデータを取得する。

    3行目:
    DBカラム名

    4行目以降:
    機種データ

    master_machine_categoryには
    シート名のslotまたはpachiを自動設定する。
    """
    sheet_range = (
        f"A{HEADER_ROW}:"
        f"{SHEET_LAST_COLUMN}"
        f"{SHEET_LAST_ROW}"
    )

    values = worksheet.get(
        sheet_range
    )

    if not values:
        raise RuntimeError(
            f"{sheet_name}シートから"
            "データを取得できませんでした。"
        )

    raw_headers = values[0]

    headers, header_indexes = (
        parse_sheet_headers(
            raw_headers=raw_headers,
            sheet_name=sheet_name,
        )
    )

    records: list[
        dict[str, Any]
    ] = []

    data_rows = values[1:]

    for offset, row in enumerate(
        data_rows
    ):
        sheet_row_number = (
            DATA_START_ROW
            + offset
        )

        record: dict[
            str,
            Any
        ] = {}

        for column_name, column_index in zip(
            headers,
            header_indexes,
        ):
            record[
                column_name
            ] = get_row_value(
                row=row,
                index=column_index,
            )

        # 完全な空行は除外する。
        if not any(
            value is not None
            for value in record.values()
        ):
            continue

        machine_id = clean_value(
            record.get(
                "master_machine_id"
            )
        )

        machine_name = clean_value(
            record.get(
                "master_machine_name"
            )
        )

        if not machine_id:
            print(
                "[WARN] スキップ: "
                f"{sheet_name}シート "
                f"{sheet_row_number}行目 "
                "master_machine_idが空です。"
            )

            continue

        if not machine_name:
            print(
                "[WARN] スキップ: "
                f"{sheet_name}シート "
                f"{sheet_row_number}行目 "
                "master_machine_nameが空です。"
            )

            continue

        record[
            "master_machine_id"
        ] = machine_id

        record[
            "master_machine_name"
        ] = machine_name

        # シート名からカテゴリを自動設定
        record[
            "master_machine_category"
        ] = sheet_name

        # DBへ自動登録するシート行番号
        record[
            "source_sheet_row"
        ] = sheet_row_number

        # 重複エラーなどの表示用。
        # DBには登録しない。
        record[
            "__source_sheet_name"
        ] = sheet_name

        records.append(
            record
        )

    print(
        "[INFO] シート取得完了: "
        f"{sheet_name} "
        f"{len(records):,}件"
    )

    return (
        headers,
        records,
    )


# ==================================================
# slot・pachi両シート取得
# ==================================================

def get_all_sheet_records() -> tuple[
    list[str],
    list[dict[str, Any]],
]:
    """
    slotシートとpachiシートを取得し、
    1つの機種マスターリストへ結合する。
    """
    client = connect_google_sheets()

    spreadsheet = client.open(
        GSHEET_NAME
    )

    all_columns: list[str] = []

    seen_columns: set[str] = set()

    all_records: list[
        dict[str, Any]
    ] = []

    for sheet_name in SHEET_NAMES:
        worksheet = spreadsheet.worksheet(
            sheet_name
        )

        sheet_columns, sheet_records = (
            get_sheet_records(
                worksheet=worksheet,
                sheet_name=sheet_name,
            )
        )

        for column_name in sheet_columns:
            if column_name in seen_columns:
                continue

            seen_columns.add(
                column_name
            )

            all_columns.append(
                column_name
            )

        all_records.extend(
            sheet_records
        )

    if not all_records:
        raise RuntimeError(
            "slot・pachiシートから"
            "同期対象データを"
            "取得できませんでした。"
        )

    validate_duplicate_machine_ids(
        all_records
    )

    return (
        all_columns,
        all_records,
    )


# ==================================================
# 機種ID重複確認
# ==================================================

def validate_duplicate_machine_ids(
    records: list[dict[str, Any]],
) -> None:
    """
    slot・pachiを含む全レコードで、
    master_machine_idの重複を確認する。

    重複時はDB同期を中止する。
    """
    seen_machine_ids: dict[
        str,
        dict[str, Any]
    ] = {}

    duplicate_messages: list[str] = []

    for record in records:
        machine_id = str(
            record.get(
                "master_machine_id"
            )
            or ""
        ).strip()

        if not machine_id:
            continue

        if machine_id not in seen_machine_ids:
            seen_machine_ids[
                machine_id
            ] = record

            continue

        first_record = seen_machine_ids[
            machine_id
        ]

        first_sheet = first_record.get(
            "__source_sheet_name"
        )

        first_row = first_record.get(
            "source_sheet_row"
        )

        first_name = first_record.get(
            "master_machine_name"
        )

        duplicate_sheet = record.get(
            "__source_sheet_name"
        )

        duplicate_row = record.get(
            "source_sheet_row"
        )

        duplicate_name = record.get(
            "master_machine_name"
        )

        duplicate_messages.append(
            f"ID={machine_id} / "
            f"最初={first_sheet}!"
            f"{first_row} "
            f"{first_name} / "
            f"重複={duplicate_sheet}!"
            f"{duplicate_row} "
            f"{duplicate_name}"
        )

    if duplicate_messages:
        details = "\n".join(
            f"- {message}"
            for message in duplicate_messages[
                :50
            ]
        )

        omitted_count = (
            len(
                duplicate_messages
            )
            - 50
        )

        if omitted_count > 0:
            details += (
                "\n"
                f"- ほか{omitted_count:,}件"
            )

        raise ValueError(
            "master_machine_idの"
            "重複があります。\n"
            f"{details}"
        )


# ==================================================
# DB登録カラム決定
# ==================================================

def resolve_insert_columns(
    sheet_columns: list[str],
    db_columns: list[str],
) -> list[str]:
    """
    スプレッドシートとDBの両方に存在する
    カラムだけをINSERT対象にする。

    自動設定するカラムは除外する。
    """
    db_column_set = set(
        db_columns
    )

    insert_columns = [
        column_name
        for column_name in sheet_columns
        if column_name in db_column_set
        and column_name
        not in DB_MANAGED_COLUMNS
    ]

    missing_required_columns = (
        REQUIRED_COLUMNS
        - set(
            insert_columns
        )
    )

    if missing_required_columns:
        raise ValueError(
            "スプレッドシートまたはDBに"
            "必須カラムがありません: "
            + ", ".join(
                sorted(
                    missing_required_columns
                )
            )
        )

    ignored_sheet_columns = [
        column_name
        for column_name in sheet_columns
        if column_name not in db_column_set
    ]

    if ignored_sheet_columns:
        print(
            "[WARN] DBに存在しないため"
            "同期しないカラム:"
        )

        for column_name in (
            ignored_sheet_columns
        ):
            print(
                f"  - {column_name}"
            )

    return insert_columns


# ==================================================
# INSERTデータ作成
# ==================================================

def build_insert_values(
    records: list[dict[str, Any]],
    insert_columns: list[str],
    automatic_columns: list[str],
    current_time: str,
) -> list[tuple[Any, ...]]:
    """
    executemany用の登録値を作成する。
    """
    insert_values: list[
        tuple[Any, ...]
    ] = []

    for record in records:
        row_values: list[Any] = []

        # スプレッドシートから取得した値
        for column_name in insert_columns:
            row_values.append(
                record.get(
                    column_name
                )
            )

        # コード側で自動設定する値
        for column_name in automatic_columns:
            if (
                column_name
                == "master_machine_category"
            ):
                row_values.append(
                    record.get(
                        "master_machine_category"
                    )
                )

            elif column_name == "source_sheet_row":
                row_values.append(
                    record.get(
                        "source_sheet_row"
                    )
                )

            elif column_name in {
                "created_at",
                "updated_at",
            }:
                row_values.append(
                    current_time
                )

            else:
                row_values.append(
                    None
                )

        insert_values.append(
            tuple(
                row_values
            )
        )

    return insert_values


# ==================================================
# machine_master同期
# ==================================================

def sync_machine_master() -> None:
    """
    slot・pachiシートの機種マスターを、
    machine_masterテーブルへ全件同期する。

    処理:
    1. slotシート取得
    2. pachiシート取得
    3. master_machine_category設定
    4. 機種ID重複確認
    5. DBカラム確認
    6. トランザクション開始
    7. 既存machine_master全件削除
    8. 全件INSERT
    9. 登録件数確認
    10. COMMIT

    途中でエラーが発生した場合は
    ROLLBACKする。
    """
    sheet_columns, records = (
        get_all_sheet_records()
    )

    slot_count = sum(
        1
        for record in records
        if record.get(
            "master_machine_category"
        ) == "slot"
    )

    pachi_count = sum(
        1
        for record in records
        if record.get(
            "master_machine_category"
        ) == "pachi"
    )

    print("=" * 80)

    print(
        "[INFO] スプレッドシート: "
        f"{GSHEET_NAME}"
    )

    print(
        "[INFO] slot件数: "
        f"{slot_count:,}件"
    )

    print(
        "[INFO] pachi件数: "
        f"{pachi_count:,}件"
    )

    print(
        "[INFO] 合計件数: "
        f"{len(records):,}件"
    )

    print(
        "[INFO] DB: "
        f"{DB_PATH}"
    )

    print(
        "[INFO] TABLE: "
        f"{TABLE_NAME}"
    )

    print("=" * 80)

    connection = sqlite3.connect(
        str(
            DB_PATH
        )
    )

    try:
        if not table_exists(
            connection=connection,
            table_name=TABLE_NAME,
        ):
            raise RuntimeError(
                f"{TABLE_NAME}テーブルが"
                "存在しません。"
                "先にcreate_machine_master.ipynbを"
                "実行してください。"
            )

        db_columns = get_table_columns(
            connection=connection,
            table_name=TABLE_NAME,
        )

        # master_machine_categoryが
        # DBに存在することを必須にする。
        if (
            "master_machine_category"
            not in db_columns
        ):
            raise RuntimeError(
                "machine_masterテーブルに"
                "master_machine_categoryカラムが"
                "ありません。"
                "columns_machine_master.txtへ"
                "'master_machine_category "
                "TEXT NOT NULL'を追加して、"
                "create_machine_master.ipynbを"
                "再実行してください。"
            )

        insert_columns = (
            resolve_insert_columns(
                sheet_columns=sheet_columns,
                db_columns=db_columns,
            )
        )

        automatic_columns: list[str] = []

        if (
            "master_machine_category"
            in db_columns
            and "master_machine_category"
            not in insert_columns
        ):
            automatic_columns.append(
                "master_machine_category"
            )

        if (
            "source_sheet_row" in db_columns
            and "source_sheet_row"
            not in insert_columns
        ):
            automatic_columns.append(
                "source_sheet_row"
            )

        if (
            "created_at" in db_columns
            and "created_at"
            not in insert_columns
        ):
            automatic_columns.append(
                "created_at"
            )

        if (
            "updated_at" in db_columns
            and "updated_at"
            not in insert_columns
        ):
            automatic_columns.append(
                "updated_at"
            )

        final_insert_columns = (
            insert_columns
            + automatic_columns
        )

        quoted_columns = ",\n                ".join(
            quote_identifier(
                column_name
            )
            for column_name
            in final_insert_columns
        )

        placeholders = ", ".join(
            "?"
            for _ in final_insert_columns
        )

        insert_sql = f"""
            INSERT INTO {quote_identifier(TABLE_NAME)} (
                {quoted_columns}
            )
            VALUES (
                {placeholders}
            )
        """

        current_time = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

        insert_values = build_insert_values(
            records=records,
            insert_columns=insert_columns,
            automatic_columns=(
                automatic_columns
            ),
            current_time=current_time,
        )

        connection.execute(
            "BEGIN"
        )

        connection.execute(
            f"""
            DELETE FROM
                {quote_identifier(TABLE_NAME)}
            """
        )

        connection.executemany(
            insert_sql,
            insert_values,
        )

        inserted_count = (
            connection.execute(
                f"""
                SELECT
                    COUNT(*)

                FROM
                    {quote_identifier(TABLE_NAME)}
                """
            ).fetchone()[0]
        )

        if inserted_count != len(
            records
        ):
            raise RuntimeError(
                "登録件数が一致しません。"
                f" シート={len(records):,}件"
                f" DB={inserted_count:,}件"
            )

        category_counts = (
            connection.execute(
                f"""
                SELECT
                    master_machine_category,
                    COUNT(*)

                FROM
                    {quote_identifier(TABLE_NAME)}

                GROUP BY
                    master_machine_category

                ORDER BY
                    master_machine_category
                """
            ).fetchall()
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    print("=" * 80)

    print(
        "[INFO] ✅ machine_master同期完了"
    )

    print(
        "[INFO] slot同期件数: "
        f"{slot_count:,}件"
    )

    print(
        "[INFO] pachi同期件数: "
        f"{pachi_count:,}件"
    )

    print(
        "[INFO] 合計同期件数: "
        f"{len(records):,}件"
    )

    print(
        "[INFO] DBカテゴリ別件数:"
    )

    for category, count in category_counts:
        print(
            f"  - {category}: "
            f"{count:,}件"
        )

    print(
        "[INFO] 同期カラム:"
    )

    for column_name in final_insert_columns:
        print(
            f"  - {column_name}"
        )

    print("=" * 80)


# ==================================================
# 実行
# ==================================================

def main() -> None:
    """
    machine_master同期処理を実行する。
    """
    try:
        sync_machine_master()

        elapsed_time = (
            time.time()
            - START_TIME
        )

        print(
            "[INFO] 処理時間: "
            f"{elapsed_time:.2f}秒"
        )

    except gspread.exceptions.WorksheetNotFound as error:
        print("=" * 80)

        print(
            "[ERROR] slotまたはpachiシートが"
            "見つかりません。"
        )

        print(
            f"[ERROR] {type(error).__name__}: "
            f"{error}"
        )

        print("=" * 80)

        raise

    except gspread.exceptions.GSpreadException as error:
        print("=" * 80)

        print(
            "[ERROR] Google Sheets処理で"
            "エラーが発生しました。"
        )

        print(
            f"[ERROR] {type(error).__name__}: "
            f"{error}"
        )

        print("=" * 80)

        raise

    except sqlite3.Error as error:
        print("=" * 80)

        print(
            "[ERROR] SQLite処理で"
            "エラーが発生しました。"
        )

        print(
            f"[ERROR] {type(error).__name__}: "
            f"{error}"
        )

        print("=" * 80)

        raise

    except Exception as error:
        print("=" * 80)

        print(
            "[ERROR] machine_master同期処理で"
            "エラーが発生しました。"
        )

        print(
            f"[ERROR] {type(error).__name__}: "
            f"{error}"
        )

        print("=" * 80)

        raise


if __name__ == "__main__":
    main()


# In[ ]:




