import html
import os
import smtplib
import sqlite3
import sys
import time

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


# ==================================================
# importパス設定
# ==================================================

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


# ==================================================
# config読込
# ==================================================

from utils.config import (
    DB_PATH,
    SMTP_SERVER,
    SMTP_PORT,
    MAIL_SENDER_EMAIL,
    MAIL_APP_PASSWORD,
    MAIL_RECEIVER_EMAILS,
)


# ==================================================
# 初期設定
# ==================================================

start_time = time.time()

print(
    f"[INFO] DB: {DB_PATH}"
)


# ==================================================
# メール送信
# ==================================================

def send_email(
    subject: str,
    html_body: str,
) -> None:

    msg = MIMEMultipart(
        "alternative"
    )

    msg["From"] = formataddr(
        (
            "実機相場ナビ",
            MAIL_SENDER_EMAIL,
        )
    )

    msg["To"] = ", ".join(
        MAIL_RECEIVER_EMAILS
    )

    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            html_body,
            "html",
            "utf-8",
        )
    )

    with smtplib.SMTP(
        SMTP_SERVER,
        SMTP_PORT,
    ) as server:

        server.starttls()

        server.login(
            MAIL_SENDER_EMAIL,
            MAIL_APP_PASSWORD,
        )

        server.sendmail(
            MAIL_SENDER_EMAIL,
            MAIL_RECEIVER_EMAILS,
            msg.as_string(),
        )


# ==================================================
# 補助関数
# ==================================================

def get_category_label(
    category: str,
) -> str:

    category_labels = {
        "pachi": "パチンコ",
        "slot": "スロット",
    }

    return category_labels.get(
        category,
        category or "カテゴリ不明",
    )


def table_exists(
    conn: sqlite3.Connection,
    table_name: str,
) -> bool:

    row = conn.execute(
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


# ==================================================
# 対象日
# ==================================================

today_str = datetime.now().strftime(
    "%Y-%m-%d"
)


# ==================================================
# DB集計
# ==================================================

with sqlite3.connect(
    DB_PATH
) as conn:

    # ----------------------------------------------
    # ショップ・カテゴリ別集計
    # ----------------------------------------------

    rows = conn.execute(
        """
        SELECT
            COALESCE(
                shop_name,
                '店舗名不明'
            ) AS shop,

            COALESCE(
                category,
                'unknown'
            ) AS category,

            COUNT(*) AS total_count,

            SUM(
                CASE
                    WHEN master_machine_name IS NOT NULL
                     AND TRIM(master_machine_name) <> ''
                    THEN 1
                    ELSE 0
                END
            ) AS matched_count,

            SUM(
                CASE
                    WHEN master_machine_name IS NULL
                      OR TRIM(master_machine_name) = ''
                    THEN 1
                    ELSE 0
                END
            ) AS unmatched_count

        FROM result_table

        WHERE created_at LIKE ?

        GROUP BY
            COALESCE(
                shop_name,
                '店舗名不明'
            ),
            COALESCE(
                category,
                'unknown'
            )

        ORDER BY
            shop,
            category
        """,
        (
            f"{today_str}%",
        ),
    ).fetchall()

    # ----------------------------------------------
    # HTTP 400エラー集計
    # ----------------------------------------------

    error_400_rows = []

    if table_exists(
        conn,
        "scraping_log",
    ):
        error_400_rows = conn.execute(
            """
            SELECT
                COALESCE(
                    shop_name,
                    '店舗名不明'
                ) AS shop,

                COALESCE(
                    category,
                    'unknown'
                ) AS category,

                COUNT(*) AS error_count,

                GROUP_CONCAT(
                    DISTINCT request_url
                ) AS error_urls

            FROM scraping_log

            WHERE created_at LIKE ?
              AND status_code = 400

            GROUP BY
                COALESCE(
                    shop_name,
                    '店舗名不明'
                ),
                COALESCE(
                    category,
                    'unknown'
                )

            ORDER BY
                shop,
                category
            """,
            (
                f"{today_str}%",
            ),
        ).fetchall()


# ==================================================
# 合計
# ==================================================

total_count = sum(
    row[2]
    for row in rows
)

total_matched = sum(
    row[3]
    for row in rows
)

total_unmatched = sum(
    row[4]
    for row in rows
)

total_400_errors = sum(
    row[2]
    for row in error_400_rows
)


# ==================================================
# ショップ・カテゴリ別HTML
# ==================================================

shop_html = "".join(
    f"""
    <tr>
        <td>
            {html.escape(shop_name)}
        </td>

        <td>
            {html.escape(
                get_category_label(category)
            )}
        </td>

        <td style="text-align:right;">
            {count:,}件
        </td>

        <td style="text-align:right;">
            {matched_count:,}件
        </td>

        <td style="text-align:right;">
            {unmatched_count:,}件
        </td>
    </tr>
    """
    for (
        shop_name,
        category,
        count,
        matched_count,
        unmatched_count,
    ) in rows
)


if not shop_html:
    shop_html = """
    <tr>
        <td colspan="5">
            本日の取得データなし
        </td>
    </tr>
    """


# ==================================================
# HTTP 400エラーHTML
# ==================================================

error_400_html = "".join(
    f"""
    <tr>
        <td>
            {html.escape(shop_name)}
        </td>

        <td>
            {html.escape(
                get_category_label(category)
            )}
        </td>

        <td style="text-align:right;">
            {error_count:,}件
        </td>

        <td style="
            max-width:600px;
            overflow-wrap:anywhere;
        ">
            {
                html.escape(
                    error_urls or ""
                ).replace(
                    ",",
                    "<br>",
                )
            }
        </td>
    </tr>
    """
    for (
        shop_name,
        category,
        error_count,
        error_urls,
    ) in error_400_rows
)


if not error_400_html:
    error_400_html = """
    <tr>
        <td colspan="4">
            本日のHTTP 400エラーはありません
        </td>
    </tr>
    """


# ==================================================
# HTTP 400エラー状態
# ==================================================

if total_400_errors > 0:

    error_status_html = f"""
    <span style="
        color:#c62828;
        font-weight:bold;
    ">
        HTTP 400エラーあり：{total_400_errors:,}件
    </span>
    """

else:

    error_status_html = """
    <span style="
        color:#2e7d32;
        font-weight:bold;
    ">
        HTTP 400エラーなし
    </span>
    """


# ==================================================
# メール本文
# ==================================================

html_body = f"""
<h2>
    {today_str} 相場ナビ取得結果
</h2>

<p>
    <strong>
        合計取得件数：{total_count:,}件
    </strong>
    <br>

    一致件数：{total_matched:,}件
    <br>

    不一致件数：{total_unmatched:,}件
    <br>

    {error_status_html}
</p>

<h3>
    ショップ・カテゴリ別取得結果
</h3>

<table
    border="1"
    cellpadding="6"
    cellspacing="0"
    style="border-collapse:collapse;"
>
    <tr>
        <th>ショップ</th>
        <th>カテゴリ</th>
        <th>取得件数</th>
        <th>一致件数</th>
        <th>不一致件数</th>
    </tr>

    {shop_html}
</table>

<h3>
    HTTP 400エラー
</h3>

<table
    border="1"
    cellpadding="6"
    cellspacing="0"
    style="border-collapse:collapse;"
>
    <tr>
        <th>ショップ</th>
        <th>カテゴリ</th>
        <th>発生件数</th>
        <th>URL</th>
    </tr>

    {error_400_html}
</table>
"""


# ==================================================
# 設定チェック
# ==================================================

if not MAIL_SENDER_EMAIL:
    raise RuntimeError(
        "MAIL_SENDER_EMAILが設定されていません"
    )


if not MAIL_APP_PASSWORD:
    raise RuntimeError(
        "MAIL_APP_PASSWORDが設定されていません"
    )


if not MAIL_RECEIVER_EMAILS:
    raise RuntimeError(
        "MAIL_RECEIVER_EMAILSが設定されていません"
    )


# ==================================================
# メール件名
# ==================================================

subject = (
    f"{today_str} 相場ナビ取得結果"
    f"（取得{total_count:,}件"
    f"／一致{total_matched:,}件"
    f"／不一致{total_unmatched:,}件"
    f"／400エラー{total_400_errors:,}件）"
)


# ==================================================
# メール送信
# ==================================================

send_email(
    subject,
    html_body,
)


# ==================================================
# 結果表示
# ==================================================

print(
    f"[INFO] 対象日: {today_str}"
)

print(
    f"[INFO] ショップ・カテゴリ別集計: {rows}"
)

print(
    f"[INFO] HTTP 400エラー: {error_400_rows}"
)

print(
    f"[INFO] 完了 "
    f"取得={total_count:,}件 "
    f"一致={total_matched:,}件 "
    f"不一致={total_unmatched:,}件 "
    f"400エラー={total_400_errors:,}件 "
    f"（{time.time() - start_time:.1f}秒）"
)