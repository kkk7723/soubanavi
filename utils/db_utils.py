import re
import sqlite3

from pathlib import Path
from typing import Any


# ==================================================
# テーブル名
# ==================================================

PRODUCT_TABLE_NAME = "result_table"
SUMMARY_TABLE_NAME = "product_summary"
PRICE_HISTORY_TABLE_NAME = "price_history"


# ==================================================
# SQLite接続
# ==================================================

def connect_database(
    db_path: str | Path,
) -> sqlite3.Connection:
    """
    SQLiteデータベースへ接続する。

    sqlite3.Rowを設定するため、
    取得結果をカラム名で参照できる。
    """
    database_path = Path(
        db_path
    ).expanduser().resolve()

    if not database_path.is_file():
        raise FileNotFoundError(
            "SQLiteデータベースが見つかりません: "
            f"{database_path}"
        )

    connection = sqlite3.connect(
        str(database_path)
    )

    connection.row_factory = sqlite3.Row

    return connection


# ==================================================
# SQLite行データ変換
# ==================================================

def row_to_dict(
    row: sqlite3.Row,
) -> dict[str, Any]:
    """
    sqlite3.Rowを通常のdictへ変換する。
    """
    return dict(row)


def rows_to_dicts(
    rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    """
    sqlite3.Rowの一覧を
    通常のdictの一覧へ変換する。
    """
    return [
        dict(row)
        for row in rows
    ]


# ==================================================
# SQL識別子
# ==================================================

def validate_identifier(
    identifier: str,
) -> str:
    """
    SQLで使用するテーブル名などが、
    英数字とアンダースコアだけで
    構成されていることを確認する。

    SQLiteではテーブル名を
    プレースホルダーに渡せないため、
    動的なテーブル名を使用する場合に使う。
    """
    if not isinstance(
        identifier,
        str,
    ):
        raise TypeError(
            "SQL識別子は文字列で指定してください。"
        )

    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*",
        identifier,
    ):
        raise ValueError(
            "不正なSQL識別子です: "
            f"{identifier}"
        )

    return identifier


# ==================================================
# テーブル存在確認
# ==================================================

def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    """
    指定したテーブルが存在する場合はTrue、
    存在しない場合はFalseを返す。
    """
    row = connection.execute(
        """
        SELECT 1
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


def check_table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> None:
    """
    指定したテーブルが存在するか確認する。

    存在しない場合はRuntimeErrorを発生させる。
    """
    if not table_exists(
        connection,
        table_name,
    ):
        raise RuntimeError(
            "テーブルが存在しません: "
            f"{table_name}"
        )


def check_tables_exist(
    connection: sqlite3.Connection,
    table_names: list[str] | tuple[str, ...],
) -> None:
    """
    複数のテーブルが存在するかまとめて確認する。

    存在しないテーブルがある場合は、
    RuntimeErrorを発生させる。
    """
    missing_tables = [
        table_name
        for table_name in table_names
        if not table_exists(
            connection,
            table_name,
        )
    ]

    if missing_tables:
        raise RuntimeError(
            "必要なテーブルが存在しません:\n"
            + "\n".join(
                missing_tables
            )
        )