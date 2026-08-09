#!/usr/bin/env python
# coding: utf-8

# In[4]:


import os
import sys
import time
import sqlite3
import re
import unicodedata

from datetime import datetime


# ==================
# 初期設定
# ==================

start_time = time.time()
now = datetime.now()

# Jupyter・通常のPythonスクリプトの両方に対応
try:
    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )
except NameError:
    base_dir = os.getcwd()

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

from utils.config import DB_PATH
from utils.maker_utils import MAKER_SLUG_MAP


# ==================
# DB設定
# ==================

TABLE_NAME = "result_table"


# ==================
# 設定値
# ==================

SOURCE_COLUMN = "machine_name"
NORMALIZED_COLUMN = "normalized_machine_name"

# executemanyで一度に処理する件数
BATCH_SIZE = 1000


# ==================
# ローマ数字変換
# ==================

ROMAN_NUMBER_MAP = {
    "XII": "12",
    "XI": "11",
    "X": "10",
    "IX": "9",
    "VIII": "8",
    "VII": "7",
    "VI": "6",
    "V": "5",
    "IV": "4",
    "III": "3",
    "II": "2",
    "I": "1",
}

# 前後が英数字ではない場合だけ変換する
ROMAN_PATTERN = re.compile(
    r"(^|[^A-Za-z0-9])"
    r"(XII|XI|IX|VIII|VII|VI|IV|III|II|X|V|I)"
    r"(?=$|[^A-Za-z0-9])",
    flags=re.IGNORECASE,
)


def convert_roman_numerals_to_numbers(
    text: str,
) -> str:
    """
    単独のローマ数字を算用数字へ変換する。

    例:
        Ⅰ                -> 1
        Ⅲ                -> 3
        IV               -> 4
        VII              -> 7
        XII              -> 12
        シンフォギアIII  -> シンフォギア3
        北斗の拳VII      -> 北斗の拳7

    英単語中のIやVなどは変換しない。
    """

    def replace_roman(
        match: re.Match,
    ) -> str:
        prefix = match.group(1)
        roman = match.group(2).upper()

        return (
            prefix
            + ROMAN_NUMBER_MAP[roman]
        )

    return ROMAN_PATTERN.sub(
        replace_roman,
        text,
    )


# ==================
# メーカー名取得
# ==================

def get_maker_words() -> set[str]:
    """
    maker_utils.py の MAKER_SLUG_MAP から
    メーカー名一覧を取得する。

    MAKER_SLUG_MAPのキーをNFKC正規化し、
    前後の空白を除去してsetとして返す。

    setを使用することで重複を除外し、
    メーカー名の存在確認を高速化する。
    """
    maker_words: set[str] = set()

    for maker_name in MAKER_SLUG_MAP:
        normalized_name = unicodedata.normalize(
            "NFKC",
            str(maker_name),
        ).strip()

        if normalized_name:
            maker_words.add(
                normalized_name
            )

    return maker_words


# ==================
# 正規化処理
# ==================

def normalize_washoi_machine_name(
    value,
    maker_set: set[str],
) -> str:
    """
    パチンコ機種名を正規化する。

    主な処理:
    ・NFKC正規化
    ・ローマ数字を算用数字へ変換
    ・不要な括弧書きを削除
    ・固定文字列を削除
    ・メーカー名を完全一致で削除
    ・不要記号とスペースを削除
    """

    if value is None or value == "":
        return ""

    # ----------------------------------
    # NFKC正規化
    # ----------------------------------

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    # ----------------------------------
    # ローマ数字を算用数字へ変換
    # ----------------------------------

    text = convert_roman_numerals_to_numbers(
        text
    )

    # ----------------------------------
    # 各種括弧書きの処理
    # ----------------------------------

    # 半角角括弧 [...]
    #
    # 「スマパチ」または「数字+号機」で始まる場合は残す。
    # それ以外は括弧ごとスペースへ置換する。
    text = re.sub(
        r"\[(?!(?:スマパチ|\d+号機)[^\]]*\])[^\]]*\]",
        " ",
        text,
    )

    # 隅付き括弧 【...】
    #
    # 「スマパチ」または「数字+号機」で始まる場合は残す。
    text = re.sub(
        r"【(?!(?:スマパチ|\d+号機)[^】]*】)[^】]*】",
        " ",
        text,
    )

    # 丸括弧 (...)
    #
    # 括弧内のどこかに「スマパチ」または「数字+号機」が
    # 含まれていれば残す。
    text = re.sub(
        r"\((?![^)]*(?:スマパチ|\d+号機))[^)]*\)",
        " ",
        text,
    )

    # ----------------------------------
    # 残した括弧の前後に一時スペースを追加
    # ----------------------------------

    # 例:
    # 【スマパチ】機種名 -> 【スマパチ】 機種名
    text = re.sub(
        r"([\]】)])(?=\S)",
        r"\1 ",
        text,
    )

    # 例:
    # 機種名【スマパチ】 -> 機種名 【スマパチ】
    text = re.sub(
        r"(\S)(?=[\[【(])",
        r"\1 ",
        text,
    )

    # ----------------------------------
    # 固定文字列の削除
    # ----------------------------------

    text = re.sub(
        r"中古パチンコ実機",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"パチンコ実機",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # No.ps0710、No.58283などを削除
    text = re.sub(
        r"No\.[A-Za-z0-9]+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ----------------------------------
    # スペースを一度整理
    # ----------------------------------

    text = re.sub(
        r"[ 　]+",
        " ",
        text,
    ).strip()

    # ----------------------------------
    # スペース区切りでメーカー名を完全一致削除
    # ----------------------------------

    parts = re.split(
        r"\s+",
        text,
    )

    text = " ".join(
        part
        for part in parts
        if part and part not in maker_set
    )

    # ----------------------------------
    # 記号削除
    # ----------------------------------

    # ～ 〜 ~
    # ・ ･
    # ■
    # : ：
    # , ，
    # ; ；
    # ☆
    text = re.sub(
        r"[☆～〜~・･■:：,，;；]",
        "",
        text,
    )

    # 山括弧類
    text = re.sub(
        r"[〈〉《》＜＞<>]",
        "",
        text,
    )

    # ! と ！
    text = re.sub(
        r"[!！]+",
        "",
        text,
    )

    # ハイフン類
    text = re.sub(
        r"[‐\-‒–—―−－]",
        "",
        text,
    )

    # アポストロフィ類
    text = re.sub(
        r"[’'＇]",
        "",
        text,
    )

    # ----------------------------------
    # 最後にすべての半角・全角スペースを削除
    # ----------------------------------

    text = re.sub(
        r"[ 　]+",
        "",
        text,
    )

    return text.strip()


# ==================
# SQLite関連
# ==================

def quote_identifier(
    identifier: str,
) -> str:
    """
    SQLiteの識別子を安全にダブルクォートで囲む。
    """
    return (
        '"'
        + identifier.replace(
            '"',
            '""',
        )
        + '"'
    )


def validate_table_name(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> None:
    """
    指定テーブルが存在するか確認する。
    """
    cursor = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (target_table_name,),
    )

    if cursor.fetchone() is None:
        raise RuntimeError(
            f'テーブル「{target_table_name}」が'
            f"データベース内に見つかりません。"
        )


def get_table_columns(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> set[str]:
    """
    テーブルのカラム名一覧を取得する。
    """
    quoted_table = quote_identifier(
        target_table_name
    )

    rows = connection.execute(
        f"PRAGMA table_info({quoted_table})"
    ).fetchall()

    return {
        row[1]
        for row in rows
    }


def ensure_normalized_column(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> None:
    """
    normalized_machine_nameが存在しない場合は追加する。
    """
    columns = get_table_columns(
        connection,
        target_table_name,
    )

    if SOURCE_COLUMN not in columns:
        raise RuntimeError(
            f'元カラム「{SOURCE_COLUMN}」が'
            f'テーブル「{target_table_name}」にありません。'
        )

    if "category" not in columns:
        raise RuntimeError(
            f'条件カラム「category」が'
            f'テーブル「{target_table_name}」にありません。'
        )

    if NORMALIZED_COLUMN in columns:
        return

    quoted_table = quote_identifier(
        target_table_name
    )
    quoted_column = quote_identifier(
        NORMALIZED_COLUMN
    )

    connection.execute(
        f"""
        ALTER TABLE {quoted_table}
        ADD COLUMN {quoted_column} TEXT
        """
    )

    print(
        f"✅ カラム「{NORMALIZED_COLUMN}」を追加しました"
    )


def update_normalized_machine_names(
    connection: sqlite3.Connection,
    target_table_name: str,
    maker_set: set[str],
) -> tuple[int, int]:
    """
    categoryがpachiのレコードだけを正規化して保存する。

    戻り値:
        total_count:
            更新した件数

        empty_count:
            正規化後に空文字になった件数
    """
    quoted_table = quote_identifier(
        target_table_name
    )
    quoted_source = quote_identifier(
        SOURCE_COLUMN
    )
    quoted_normalized = quote_identifier(
        NORMALIZED_COLUMN
    )
    quoted_category = quote_identifier(
        "category"
    )

    select_sql = f"""
        SELECT rowid, {quoted_source}
        FROM {quoted_table}
        WHERE {quoted_category} = ?
    """

    update_sql = f"""
        UPDATE {quoted_table}
        SET {quoted_normalized} = ?
        WHERE rowid = ?
    """

    read_cursor = connection.execute(
        select_sql,
        ("pachi",),
    )

    total_count = 0
    empty_count = 0

    while True:
        rows = read_cursor.fetchmany(
            BATCH_SIZE
        )

        if not rows:
            break

        update_values: list[tuple[str, int]] = []

        for rowid, machine_name in rows:
            normalized_name = (
                normalize_washoi_machine_name(
                    machine_name,
                    maker_set,
                )
            )

            if normalized_name == "":
                empty_count += 1

            update_values.append(
                (
                    normalized_name,
                    rowid,
                )
            )

        connection.executemany(
            update_sql,
            update_values,
        )

        total_count += len(
            update_values
        )

        print(
            f"\r処理中: {total_count:,}件",
            end="",
            flush=True,
        )

    if total_count:
        print()

    return total_count, empty_count


# ==================
# メイン処理
# ==================

def main() -> None:
    # ----------------------------------
    # DBファイル確認
    # ----------------------------------

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            "[ERROR] データベースが見つかりません: "
            f"{DB_PATH}"
        )

    # ----------------------------------
    # maker_utils.pyからメーカー名取得
    # ----------------------------------

    maker_set = get_maker_words()

    print(
        f"✅ maker_utils.pyからメーカー名を"
        f"{len(maker_set):,}件取得しました"
    )

    # ----------------------------------
    # SQLite更新
    # ----------------------------------

    connection = sqlite3.connect(
        DB_PATH
    )

    total_count = 0
    empty_count = 0

    try:
        validate_table_name(
            connection,
            TABLE_NAME,
        )

        ensure_normalized_column(
            connection,
            TABLE_NAME,
        )

        # エラー時に全更新を取り消せるよう明示的に開始
        connection.execute(
            "BEGIN"
        )

        total_count, empty_count = (
            update_normalized_machine_names(
                connection,
                TABLE_NAME,
                maker_set,
            )
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    elapsed_time = (
        time.time()
        - start_time
    )

    print(
        f"✅ 正規化完了: {total_count:,}件"
    )

    print(
        f"空文字になった件数: {empty_count:,}件"
    )

    print(
        f"データベース: {DB_PATH}"
    )

    print(
        f"処理時間: {elapsed_time:.2f}秒"
    )


if __name__ == "__main__":
    main()


# In[ ]:




