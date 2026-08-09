#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sys
import time
import sqlite3

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ==================================================
# 初期設定
# ==================================================

START_TIME = time.time()


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
)


# ==================================================
# DB設定
# ==================================================

# 商品データ
TARGET_TABLE_NAME = "result_table"

# 機種マスター
MASTER_TABLE_NAME = "machine_master"


# ==================================================
# 照合設定
# ==================================================

# result_table側の照合元カラム
SOURCE_COLUMN = "normalized_machine_name"

# result_table側のカテゴリカラム
TARGET_CATEGORY_COLUMN = "category"

# result_tableで照合対象とするカテゴリ
TARGET_CATEGORY_VALUE = "pachi"

# machine_master側のカテゴリカラム
MASTER_CATEGORY_COLUMN = (
    "master_machine_category"
)

# machine_masterから取得するカテゴリ
MASTER_CATEGORY_VALUE = "pachi"


# ==================================================
# 検索カラム
# ==================================================

# 通常検索に使用するmachine_master側のカラム
NORMAL_SEARCH_COLUMNS = (
    "master_machine_pworld_normalized_model_search",
    "master_machine_pworld_normalized_name_search",
    "master_machine_ptown_normalized_model_search",
    "master_machine_ptown_normalized_name_search",
    "master_machine_special_search_1",
    "master_machine_special_search_2",
    "master_machine_special_search_3",
    "master_machine_special_search_4",
)


# ==================================================
# result_tableへ書き込むカラム
# ==================================================

# DBカラム名: SQLite型
#
# この順番はcreate_update_values()の
# 戻り値の順番と一致させる。
OUTPUT_COLUMNS = {
    "master_machine_name": "TEXT",
    "master_machine_id": "TEXT",
    "master_machine_pworld_url": "TEXT",
    "master_machine_pworld_image_url": "TEXT",
    "master_machine_model": "TEXT",
    "master_machine_maker": "TEXT",
    "master_machine_introduced_date": "TEXT",
    "master_machine_type": "TEXT",
    "master_machine_gouki": "TEXT",
    "master_machine_game_system": "TEXT",
    "master_machine_memo": "TEXT",
}

# サンプル表示用
OUTPUT_COLUMN = "master_machine_name"

# 一度に処理する件数
BATCH_SIZE = 1000


# ==================================================
# pachi検索マスタ
# ==================================================

@dataclass(frozen=True)
class MasterItem:
    """
    machine_masterテーブルから作成する
    pachi用検索マスタ。
    """

    master_machine_id: str

    pworld_url: str
    pworld_image_url: str

    model: str
    master_name: str
    maker: str
    introduced_date: str

    machine_type: str
    generation: str
    game_system: str
    memo: str

    search_word: str


# ==================================================
# 値整形
# ==================================================

def clean_text(
    value: Any,
) -> str:
    """
    DBの値を文字列へ変換し、
    前後の空白を除去する。

    Noneは空文字へ変換する。
    """
    if value is None:
        return ""

    return str(
        value
    ).strip()


# ==================================================
# SQLite識別子
# ==================================================

def quote_identifier(
    identifier: str,
) -> str:
    """
    SQLiteのテーブル名・カラム名を
    ダブルクォートで安全に囲む。
    """
    return (
        '"'
        + identifier.replace(
            '"',
            '""',
        )
        + '"'
    )


# ==================================================
# SQLite確認処理
# ==================================================

def validate_table_name(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> None:
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
            target_table_name,
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"テーブル「{target_table_name}」が"
            "データベース内に見つかりません。"
        )


def get_table_columns(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> set[str]:
    """
    指定テーブルのカラム名一覧を取得する。
    """
    quoted_table = quote_identifier(
        target_table_name
    )

    rows = connection.execute(
        f"""
        PRAGMA table_info(
            {quoted_table}
        )
        """
    ).fetchall()

    return {
        str(
            row[1]
        )
        for row in rows
    }


def validate_master_table_columns(
    connection: sqlite3.Connection,
) -> None:
    """
    machine_masterテーブルに、
    pachi照合で必要なカラムが
    存在するか確認する。
    """
    master_columns = get_table_columns(
        connection,
        MASTER_TABLE_NAME,
    )

    required_master_columns = {
        "master_machine_id",
        "master_machine_category",
        "master_machine_name",
        "master_machine_pworld_url",
        "master_machine_pworld_image_url",
        "master_machine_model",
        "master_machine_maker",
        "master_machine_introduced_date",
        "master_machine_type",
        "master_machine_gouki",
        "master_machine_game_system",
        "master_machine_memo",
        *NORMAL_SEARCH_COLUMNS,
    }

    missing_columns = (
        required_master_columns
        - master_columns
    )

    if missing_columns:
        raise RuntimeError(
            "machine_masterテーブルに"
            "必要なカラムがありません:\n"
            + "\n".join(
                f"- {column_name}"
                for column_name in sorted(
                    missing_columns
                )
            )
        )


def ensure_output_columns(
    connection: sqlite3.Connection,
    target_table_name: str,
) -> None:
    """
    result_tableの必須カラムを確認し、
    出力先カラムがなければ追加する。
    """
    columns = get_table_columns(
        connection,
        target_table_name,
    )

    if SOURCE_COLUMN not in columns:
        raise RuntimeError(
            f"照合元カラム「{SOURCE_COLUMN}」が"
            f"テーブル「{target_table_name}」に"
            "ありません。"
        )

    if TARGET_CATEGORY_COLUMN not in columns:
        raise RuntimeError(
            f"対象判定カラム"
            f"「{TARGET_CATEGORY_COLUMN}」が"
            f"テーブル「{target_table_name}」に"
            "ありません。"
        )

    quoted_table = quote_identifier(
        target_table_name
    )

    for (
        column_name,
        column_type,
    ) in OUTPUT_COLUMNS.items():
        if column_name in columns:
            continue

        quoted_column = quote_identifier(
            column_name
        )

        connection.execute(
            f"""
            ALTER TABLE {quoted_table}
            ADD COLUMN {quoted_column} {column_type}
            """
        )

        print(
            "✅ カラム追加: "
            f"{column_name}"
        )


# ==================================================
# machine_masterから検索マスタ作成
# ==================================================

def build_master_data(
    connection: sqlite3.Connection,
) -> list[MasterItem]:
    """
    machine_masterテーブルから、
    master_machine_categoryがpachiの
    機種を取得する。

    通常検索には次の8カラムを使用する。

    ・pworld型式正規化済み検索
    ・pworld名称正規化済み検索
    ・ptown型式正規化済み検索
    ・ptown名称正規化済み検索
    ・特殊検索1～4

    master_machine_typeが
    「スマパチ」または「P機」の機種だけを
    検索マスタへ登録する。
    """
    quoted_master_table = quote_identifier(
        MASTER_TABLE_NAME
    )

    quoted_category = quote_identifier(
        MASTER_CATEGORY_COLUMN
    )

    select_columns = [
        "master_machine_id",
        "master_machine_pworld_url",
        "master_machine_pworld_image_url",
        "master_machine_model",
        "master_machine_name",
        "master_machine_maker",
        "master_machine_introduced_date",
        "master_machine_type",
        "master_machine_gouki",
        "master_machine_game_system",
        "master_machine_memo",
        *NORMAL_SEARCH_COLUMNS,
    ]

    quoted_select_columns = ",\n            ".join(
        quote_identifier(
            column_name
        )
        for column_name in select_columns
    )

    sql = f"""
        SELECT
            {quoted_select_columns}

        FROM {quoted_master_table}

        WHERE {quoted_category} = ?

          AND master_machine_name IS NOT NULL
          AND TRIM(master_machine_name) != ''

        ORDER BY
            CAST(master_machine_id AS INTEGER) ASC,
            master_machine_id ASC
    """

    rows = connection.execute(
        sql,
        (
            MASTER_CATEGORY_VALUE,
        ),
    ).fetchall()

    if not rows:
        raise RuntimeError(
            "machine_masterテーブルに"
            "master_machine_category=pachiの"
            "機種がありません。"
        )

    master_data: list[MasterItem] = []

    normal_search_start_index = 11

    for row in rows:
        master_machine_id = clean_text(
            row[0]
        )

        pworld_url = clean_text(
            row[1]
        )

        pworld_image_url = clean_text(
            row[2]
        )

        model = clean_text(
            row[3]
        )

        master_name = clean_text(
            row[4]
        )

        maker = clean_text(
            row[5]
        )

        introduced_date = clean_text(
            row[6]
        )

        machine_type = clean_text(
            row[7]
        )

        generation = clean_text(
            row[8]
        )

        game_system = clean_text(
            row[9]
        )

        memo = clean_text(
            row[10]
        )

        if not master_machine_id:
            continue

        if not master_name:
            continue

        # pachiの照合対象区分
        if machine_type not in {
            "スマパチ",
            "P機",
        }:
            continue

        common_item_values = {
            "master_machine_id": (
                master_machine_id
            ),
            "pworld_url": (
                pworld_url
            ),
            "pworld_image_url": (
                pworld_image_url
            ),
            "model": (
                model
            ),
            "master_name": (
                master_name
            ),
            "maker": (
                maker
            ),
            "introduced_date": (
                introduced_date
            ),
            "machine_type": (
                machine_type
            ),
            "generation": (
                generation
            ),
            "game_system": (
                game_system
            ),
            "memo": (
                memo
            ),
        }

        # 通常検索語8カラム
        for offset in range(
            len(
                NORMAL_SEARCH_COLUMNS
            )
        ):
            search_word = clean_text(
                row[
                    normal_search_start_index
                    + offset
                ]
            )

            if not search_word:
                continue

            master_data.append(
                MasterItem(
                    **common_item_values,
                    search_word=search_word,
                )
            )

    # 長い検索語を優先する。
    #
    # 例:
    # 「海物語」よりも
    # 「大海物語5スペシャル」を先に判定する。
    master_data.sort(
        key=lambda item: len(
            item.search_word
        ),
        reverse=True,
    )

    return master_data


# ==================================================
# 通常照合
# ==================================================

def find_normal_washoi_match(
    machine_name: str,
    master_data: list[MasterItem],
) -> MasterItem | None:
    """
    商品名とpachi検索マスタを照合する。

    判定条件:

    1. 商品名に「スマパチ」が含まれる場合、
       master_machine_typeが
       「スマパチ」のマスタだけを対象にする。

    2. 商品名に「スマパチ」が含まれない場合、
       master_machine_typeが
       「P機」のマスタだけを対象にする。

    3. 検索語が商品名に含まれる。
    """
    product_machine_type = (
        "スマパチ"
        if "スマパチ" in machine_name
        else "P機"
    )

    for item in master_data:
        if (
            item.machine_type
            != product_machine_type
        ):
            continue

        if (
            item.search_word
            in machine_name
        ):
            return item

    return None


# ==================================================
# DB照合・更新
# ==================================================

def update_master_machine_data(
    connection: sqlite3.Connection,
    target_table_name: str,
    master_data: list[MasterItem],
) -> dict[str, int]:
    """
    result_tableのcategoryがpachiの
    レコードだけを対象に、
    normalized_machine_nameを照合する。

    一致したmachine_masterの情報を、
    result_tableのmaster_machine_*カラムへ
    書き込む。
    """
    quoted_table = quote_identifier(
        target_table_name
    )

    quoted_source = quote_identifier(
        SOURCE_COLUMN
    )

    quoted_category = quote_identifier(
        TARGET_CATEGORY_COLUMN
    )

    output_column_names = list(
        OUTPUT_COLUMNS.keys()
    )

    quoted_output_columns = [
        quote_identifier(
            column_name
        )
        for column_name
        in output_column_names
    ]

    set_clause = ",\n            ".join(
        f"{column_name} = ?"
        for column_name
        in quoted_output_columns
    )

    select_sql = f"""
        SELECT
            rowid,
            {quoted_source}

        FROM {quoted_table}

        WHERE {quoted_category} = ?
    """

    update_sql = f"""
        UPDATE {quoted_table}

        SET
            {set_clause}

        WHERE rowid = ?
    """

    read_cursor = connection.execute(
        select_sql,
        (
            TARGET_CATEGORY_VALUE,
        ),
    )

    processed_count = 0
    empty_count = 0
    target_count = 0
    matched_count = 0

    smart_pachi_target_count = 0
    p_machine_target_count = 0

    smart_pachi_matched_count = 0
    p_machine_matched_count = 0

    # 未一致時は出力カラムを空文字へ戻す。
    empty_output_values = tuple(
        ""
        for _ in output_column_names
    )

    def create_update_values(
        matched: MasterItem,
        rowid: int,
    ) -> tuple[Any, ...]:
        """
        OUTPUT_COLUMNSの定義順に
        result_tableへ書き込む値を返す。

        1. master_machine_name
        2. master_machine_id
        3. master_machine_pworld_url
        4. master_machine_pworld_image_url
        5. master_machine_model
        6. master_machine_maker
        7. master_machine_introduced_date
        8. master_machine_type
        9. master_machine_gouki
        10. master_machine_game_system
        11. master_machine_memo
        12. rowid
        """
        return (
            matched.master_name,
            matched.master_machine_id,
            matched.pworld_url,
            matched.pworld_image_url,
            matched.model,
            matched.maker,
            matched.introduced_date,
            matched.machine_type,
            matched.generation,
            matched.game_system,
            matched.memo,
            rowid,
        )

    while True:
        rows = read_cursor.fetchmany(
            BATCH_SIZE
        )

        if not rows:
            break

        update_values: list[
            tuple[Any, ...]
        ] = []

        for rowid, value in rows:
            machine_name = clean_text(
                value
            )

            processed_count += 1

            # 正規化機種名が空欄の場合
            if not machine_name:
                empty_count += 1

                update_values.append(
                    empty_output_values
                    + (
                        rowid,
                    )
                )

                continue

            target_count += 1

            product_machine_type = (
                "スマパチ"
                if "スマパチ" in machine_name
                else "P機"
            )

            if (
                product_machine_type
                == "スマパチ"
            ):
                smart_pachi_target_count += 1

            else:
                p_machine_target_count += 1

            matched = find_normal_washoi_match(
                machine_name=machine_name,
                master_data=master_data,
            )

            if matched is not None:
                matched_count += 1

                if (
                    product_machine_type
                    == "スマパチ"
                ):
                    smart_pachi_matched_count += 1

                else:
                    p_machine_matched_count += 1

                update_values.append(
                    create_update_values(
                        matched=matched,
                        rowid=rowid,
                    )
                )

                continue

            # 未一致
            update_values.append(
                empty_output_values
                + (
                    rowid,
                )
            )

        connection.executemany(
            update_sql,
            update_values,
        )

        print(
            f"\r処理中: "
            f"{processed_count:,}件",
            end="",
            flush=True,
        )

    if processed_count:
        print()

    unmatched_count = (
        target_count
        - matched_count
    )

    smart_pachi_unmatched_count = (
        smart_pachi_target_count
        - smart_pachi_matched_count
    )

    p_machine_unmatched_count = (
        p_machine_target_count
        - p_machine_matched_count
    )

    return {
        "processed_count": (
            processed_count
        ),
        "empty_count": (
            empty_count
        ),
        "target_count": (
            target_count
        ),
        "matched_count": (
            matched_count
        ),
        "unmatched_count": (
            unmatched_count
        ),
        "smart_pachi_target_count": (
            smart_pachi_target_count
        ),
        "p_machine_target_count": (
            p_machine_target_count
        ),
        "smart_pachi_matched_count": (
            smart_pachi_matched_count
        ),
        "p_machine_matched_count": (
            p_machine_matched_count
        ),
        "smart_pachi_unmatched_count": (
            smart_pachi_unmatched_count
        ),
        "p_machine_unmatched_count": (
            p_machine_unmatched_count
        ),
    }


# ==================================================
# 照合結果確認
# ==================================================

def show_match_samples(
    connection: sqlite3.Connection,
    target_table_name: str,
    limit: int = 10,
) -> None:
    """
    result_tableのcategoryがpachiで、
    照合済みのレコードを数件表示する。
    """
    quoted_table = quote_identifier(
        target_table_name
    )

    quoted_source = quote_identifier(
        SOURCE_COLUMN
    )

    quoted_output = quote_identifier(
        OUTPUT_COLUMN
    )

    quoted_master_id = quote_identifier(
        "master_machine_id"
    )

    quoted_url = quote_identifier(
        "master_machine_pworld_url"
    )

    quoted_machine_type = quote_identifier(
        "master_machine_type"
    )

    quoted_introduced_date = quote_identifier(
        "master_machine_introduced_date"
    )

    quoted_game_system = quote_identifier(
        "master_machine_game_system"
    )

    quoted_memo = quote_identifier(
        "master_machine_memo"
    )

    quoted_category = quote_identifier(
        TARGET_CATEGORY_COLUMN
    )

    rows = connection.execute(
        f"""
        SELECT
            {quoted_source},
            {quoted_master_id},
            {quoted_output},
            {quoted_url},
            {quoted_machine_type},
            {quoted_introduced_date},
            {quoted_game_system},
            {quoted_memo}

        FROM {quoted_table}

        WHERE {quoted_category} = ?
          AND {quoted_output} IS NOT NULL
          AND {quoted_output} != ''

        LIMIT ?
        """,
        (
            TARGET_CATEGORY_VALUE,
            limit,
        ),
    ).fetchall()

    if not rows:
        print(
            "照合結果のサンプルはありません。"
        )

        return

    print(
        "\n--- 照合結果サンプル ---"
    )

    for (
        normalized_name,
        master_machine_id,
        master_name,
        pworld_url,
        machine_type,
        introduced_date,
        game_system,
        memo,
    ) in rows:
        print(
            f"{normalized_name}"
            "  ->  "
            f"ID: {master_machine_id or ''}"
            f" / {master_name or ''}"
        )

        print(
            "    機種タイプ: "
            f"{machine_type or ''}"
        )

        print(
            "    URL: "
            f"{pworld_url or ''}"
        )

        print(
            "    導入日: "
            f"{introduced_date or ''}"
        )

        print(
            "    ゲームシステム: "
            f"{game_system or ''}"
        )

        print(
            "    メモ: "
            f"{memo or ''}"
        )


# ==================================================
# 未一致結果確認
# ==================================================

def show_unmatched_samples(
    connection: sqlite3.Connection,
    target_table_name: str,
    limit: int = 20,
) -> None:
    """
    result_tableのcategoryがpachiで、
    未一致のデータを表示する。
    """
    quoted_table = quote_identifier(
        target_table_name
    )

    quoted_source = quote_identifier(
        SOURCE_COLUMN
    )

    quoted_output = quote_identifier(
        OUTPUT_COLUMN
    )

    quoted_category = quote_identifier(
        TARGET_CATEGORY_COLUMN
    )

    rows = connection.execute(
        f"""
        SELECT
            {quoted_source}

        FROM {quoted_table}

        WHERE {quoted_category} = ?
          AND {quoted_source} IS NOT NULL
          AND {quoted_source} != ''
          AND (
              {quoted_output} IS NULL
              OR {quoted_output} = ''
          )

        LIMIT ?
        """,
        (
            TARGET_CATEGORY_VALUE,
            limit,
        ),
    ).fetchall()

    if not rows:
        print(
            "\n未一致データはありません。"
        )

        return

    print(
        "\n--- 未一致サンプル ---"
    )

    for (
        normalized_name,
    ) in rows:
        pachi_type = (
            "スマパチ"
            if "スマパチ"
            in str(
                normalized_name
            )
            else "P機"
        )

        print(
            f"[{pachi_type}] "
            f"{normalized_name}"
        )


# ==================================================
# 検索マスタ確認
# ==================================================

def show_master_summary(
    master_data: list[MasterItem],
) -> None:
    """
    機種タイプごとの検索マスタ件数を
    表示する。
    """
    smart_pachi_master_count = sum(
        1
        for item in master_data
        if item.machine_type
        == "スマパチ"
    )

    p_machine_master_count = sum(
        1
        for item in master_data
        if item.machine_type
        == "P機"
    )

    print(
        "✅ 検索マスタ合計: "
        f"{len(master_data):,}件"
    )

    print(
        "   スマパチ検索マスタ: "
        f"{smart_pachi_master_count:,}件"
    )

    print(
        "   P機検索マスタ: "
        f"{p_machine_master_count:,}件"
    )


# ==================================================
# メイン処理
# ==================================================

def main() -> None:
    """
    machine_masterを使用して、
    result_tableのpachi商品を照合・更新する。
    """
    # result_tableとmachine_masterの
    # 対象カテゴリ設定が同じか確認する。
    if (
        TARGET_CATEGORY_VALUE
        != MASTER_CATEGORY_VALUE
    ):
        raise RuntimeError(
            "照合カテゴリが一致していません。"
            f" result_table="
            f"{TARGET_CATEGORY_VALUE}"
            f" machine_master="
            f"{MASTER_CATEGORY_VALUE}"
        )

    if not Path(
        DB_PATH
    ).is_file():
        raise FileNotFoundError(
            "[ERROR] データベースが"
            "見つかりません: "
            f"{DB_PATH}"
        )

    connection = sqlite3.connect(
        str(
            DB_PATH
        )
    )

    try:
        # ------------------------------------------
        # テーブル確認
        # ------------------------------------------

        validate_table_name(
            connection=connection,
            target_table_name=(
                TARGET_TABLE_NAME
            ),
        )

        validate_table_name(
            connection=connection,
            target_table_name=(
                MASTER_TABLE_NAME
            ),
        )

        validate_master_table_columns(
            connection
        )

        ensure_output_columns(
            connection=connection,
            target_table_name=(
                TARGET_TABLE_NAME
            ),
        )

        # ALTER TABLEがあった場合に先に確定する。
        connection.commit()

        # ------------------------------------------
        # machine_masterから検索マスタ作成
        # ------------------------------------------

        master_data = build_master_data(
            connection
        )

        print(
            "✅ machine_masterから"
            "pachi検索マスタを取得しました"
        )

        show_master_summary(
            master_data
        )

        if not master_data:
            raise RuntimeError(
                "pachi検索マスタが0件です。"
                "machine_masterの"
                "検索カラムを確認してください。"
            )

        # ------------------------------------------
        # result_table更新
        # ------------------------------------------

        connection.execute(
            "BEGIN"
        )

        counts = update_master_machine_data(
            connection=connection,
            target_table_name=(
                TARGET_TABLE_NAME
            ),
            master_data=master_data,
        )

        connection.commit()

        show_match_samples(
            connection=connection,
            target_table_name=(
                TARGET_TABLE_NAME
            ),
            limit=10,
        )

        show_unmatched_samples(
            connection=connection,
            target_table_name=(
                TARGET_TABLE_NAME
            ),
            limit=20,
        )

    except Exception:
        connection.rollback()

        raise

    finally:
        connection.close()

    # ----------------------------------------------
    # 集計表示
    # ----------------------------------------------

    elapsed_time = (
        time.time()
        - START_TIME
    )

    print(
        "\n--- 照合結果 ---"
    )

    print(
        "マスターテーブル: "
        f"{MASTER_TABLE_NAME}"
    )

    print(
        "マスターカテゴリ: "
        f"{MASTER_CATEGORY_VALUE}"
    )

    print(
        "検索マスタ合計: "
        f"{len(master_data):,}件"
    )

    print(
        "DB処理行数: "
        f"{counts['processed_count']:,}件"
    )

    print(
        "照合対象: "
        f"{counts['target_count']:,}件"
    )

    print(
        "正規化名が空欄: "
        f"{counts['empty_count']:,}件"
    )

    print(
        "スマパチ対象: "
        f"{counts['smart_pachi_target_count']:,}件"
    )

    print(
        "P機対象: "
        f"{counts['p_machine_target_count']:,}件"
    )

    print(
        "スマパチ一致: "
        f"{counts['smart_pachi_matched_count']:,}件"
    )

    print(
        "P機一致: "
        f"{counts['p_machine_matched_count']:,}件"
    )

    print(
        "スマパチ未一致: "
        f"{counts['smart_pachi_unmatched_count']:,}件"
    )

    print(
        "P機未一致: "
        f"{counts['p_machine_unmatched_count']:,}件"
    )

    print(
        "一致合計: "
        f"{counts['matched_count']:,}件"
    )

    print(
        "未一致合計: "
        f"{counts['unmatched_count']:,}件"
    )

    print(
        "対象カテゴリ: "
        f"{TARGET_CATEGORY_VALUE}"
    )

    print(
        "データベース: "
        f"{DB_PATH}"
    )

    print(
        "処理時間: "
        f"{elapsed_time:.2f}秒"
    )


if __name__ == "__main__":
    main()


# In[ ]:




