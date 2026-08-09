#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import re
import sqlite3
import sys
import time

from datetime import datetime
from urllib.parse import urljoin

import requests

from bs4 import BeautifulSoup


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
    PROXY_LIST,
    PROXY_MODE,
    PROXY_ROTATE_EVERY,
)


# ==================================================
# 初期設定
# ==================================================

start_time = time.time()

table_name = "result_table"


# ==================
# スクレイピングサイト設定
# ==================

SHOP_NAME = (
    "安心・安全・高品質の中古パチスロ・"
    "中古パチンコ実機販売店【ホームスロット】"
)

SHOP_PRODUCT_ID = 2
CATEGORY = "slot"

BASE_URL = (
    "https://home-slot.net/"
    "SHOP/191356/t01/list{}.html"
)

MAX_PAGE = 100

# ページ間の待機秒数
REQUEST_INTERVAL = 10

# 1回のリクエストのタイムアウト秒数
REQUEST_TIMEOUT = 120

# 1ページあたりの最大試行回数
MAX_RETRIES = 5

# リトライまでの待機秒数
RETRY_INTERVAL = 30


# ==================
# プロキシ
# ==================

def _resolve_proxy_for_batch(
    batch_index: int,
) -> str | None:

    mode = (
        PROXY_MODE or "none"
    ).strip().lower()

    if mode == "none":
        print(
            f"[INFO] Proxy for batch {batch_index}: "
            "(none直結)"
        )
        return None

    if mode != "list":

        raw = (
            PROXY_MODE or ""
        ).strip()

        if raw.lower() == "none" or raw == "":
            print(
                f"[INFO] Proxy for batch {batch_index}: "
                "(none直結)"
            )
            return None

        proxy = (
            raw
            if "://" in raw
            else f"http://{raw}"
        )

        print(
            f"[INFO] Proxy for batch {batch_index}: "
            f"{proxy}"
        )

        return proxy

    if not PROXY_LIST:
        print(
            f"[INFO] Proxy for batch {batch_index}: "
            "(none直結)"
        )
        return None

    step = max(
        1,
        int(PROXY_ROTATE_EVERY or 1),
    )

    idx = (
        batch_index // step
    ) % len(PROXY_LIST)

    pick = str(
        PROXY_LIST[idx]
    ).strip()

    if pick.lower() == "none" or pick == "":
        print(
            f"[INFO] Proxy for batch {batch_index}: "
            "(none直結)"
        )
        return None

    proxy = (
        pick
        if "://" in pick
        else f"http://{pick}"
    )

    print(
        f"[INFO] Proxy for batch {batch_index}: "
        f"{proxy}"
    )

    return proxy


def open_session(
    batch_index: int = 0,
) -> requests.Session:

    proxy = _resolve_proxy_for_batch(
        batch_index
    )

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/138.0.0.0 "
            "Safari/537.36"
        )
    })

    if proxy:
        session.proxies = {
            "http": proxy,
            "https": proxy,
        }

    return session


# ==================
# ページ取得・リトライ
# ==================

def get_page(
    session: requests.Session,
    url: str,
) -> requests.Response | None:

    for retry_count in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:
            print(
                f"[REQUEST] 取得開始 "
                f"({retry_count}/{MAX_RETRIES})"
            )

            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                return response

            print(
                f"[ERROR] HTTP "
                f"{response.status_code} "
                f"({retry_count}/{MAX_RETRIES})"
            )

        except requests.exceptions.ReadTimeout:
            print(
                f"[ERROR] 読み込みタイムアウト "
                f"({retry_count}/{MAX_RETRIES})"
            )

        except requests.exceptions.ConnectTimeout:
            print(
                f"[ERROR] 接続タイムアウト "
                f"({retry_count}/{MAX_RETRIES})"
            )

        except requests.exceptions.ConnectionError as e:
            print(
                f"[ERROR] 接続エラー "
                f"({retry_count}/{MAX_RETRIES}): {e}"
            )

        except requests.RequestException as e:
            print(
                f"[ERROR] リクエストエラー "
                f"({retry_count}/{MAX_RETRIES}): {e}"
            )

        # 最終試行でなければ待機して再試行
        if retry_count < MAX_RETRIES:
            print(
                f"[RETRY] {RETRY_INTERVAL}秒後に"
                "同じページを再試行します"
            )

            time.sleep(
                RETRY_INTERVAL
            )

    print(
        f"[ERROR] {MAX_RETRIES}回取得に失敗しました"
    )

    return None


# ==================
# DB
# ==================

def save_product(
    data: dict,
) -> None:

    conn = sqlite3.connect(
        DB_PATH
    )

    try:
        cur = conn.cursor()

        sql = f"""
        INSERT INTO {table_name}
        (
            shop_name,
            shop_product_id,
            category,
            machine_name,
            product_url,
            image_url,
            price,
            created_at
        )
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?)
        """

        cur.execute(
            sql,
            (
                SHOP_NAME,
                SHOP_PRODUCT_ID,
                CATEGORY,
                data["machine_name"],
                data["product_url"],
                data["image_url"],
                data["price"],
                datetime.now(),
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ==================
# スクレイピング開始
# ==================

session = open_session()
total_count = 0


try:

    # ==================
    # ページループ
    # ==================

    for page in range(
        1,
        MAX_PAGE + 1,
    ):

        url = BASE_URL.format(
            page
        )

        print(
            f"\n{'=' * 80}"
        )
        print(
            f"Page {page}"
        )
        print(
            url
        )

        # --------------------------
        # ページ取得
        # --------------------------

        response = get_page(
            session,
            url,
        )

        if response is None:
            print(
                f"[ERROR] Page {page}の取得に"
                "失敗したため終了します"
            )
            break

        # 文字コードを自動判定
        response.encoding = (
            response.apparent_encoding
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        item_list = soup.find(
            "div",
            id="itemList",
        )

        if item_list is None:
            print(
                "[ERROR] itemListが見つかりません"
            )
            break

        # 商品一覧
        # 1商品 = section.column4
        products = item_list.select(
            "section.column4"
        )

        found_count = len(
            products
        )

        saved_count = 0

        for product in products:

            # --------------------------
            # タイトル・商品URL
            # --------------------------

            a = product.select_one(
                "h2 > a"
            )

            if a is None:
                continue

            machine_name = a.get_text(
                " ",
                strip=True,
            )

            href = str(
                a.get(
                    "href",
                    "",
                )
                or ""
            ).strip()

            if not machine_name:
                print(
                    "[SKIP] 商品名が空です"
                )
                continue

            if not href:
                print(
                    f"[SKIP] 商品URLが空です: "
                    f"{machine_name}"
                )
                continue

            product_url = urljoin(
                url,
                href,
            )

            # --------------------------
            # 画像URL
            # --------------------------

            image_url = ""

            img = product.select_one(
                "span.item-list-span-img img"
            )

            if img:

                image_src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or img.get("data-lazy-src")
                    or ""
                )

                if image_src:
                    image_url = urljoin(
                        url,
                        image_src,
                    )

            # --------------------------
            # 価格
            # --------------------------

            price = ""

            price_tag = product.select_one(
                "span.selling_price"
            )

            if price_tag:

                price_text = price_tag.get_text(
                    strip=True
                )

                price = re.sub(
                    r"[^\d]",
                    "",
                    price_text,
                )

            # --------------------------
            # 表示
            # --------------------------

            print(
                "-" * 80
            )
            print(
                "ショップ:",
                SHOP_NAME,
            )
            print(
                "カテゴリ:",
                CATEGORY,
            )
            print(
                "機種名  :",
                machine_name,
            )
            print(
                "商品URL :",
                product_url,
            )
            print(
                "画像URL :",
                image_url,
            )
            print(
                "価格    :",
                price,
            )

            # --------------------------
            # DB保存
            # --------------------------

            try:
                save_product({
                    "machine_name": machine_name,
                    "product_url": product_url,
                    "image_url": image_url,
                    "price": price,
                })

                print(
                    "[DB] 保存完了"
                )

            except sqlite3.Error as e:
                print(
                    f"[DB ERROR] 保存失敗: {e}"
                )
                continue

            saved_count += 1
            total_count += 1

        print(
            f"\nページ検出件数 : {found_count}"
        )
        print(
            f"ページ保存件数 : {saved_count}"
        )

        # 商品が無くなったら終了
        if found_count == 0:
            print(
                "商品がありません。終了します。"
            )
            break

        # 次のページへ進む前に待機
        if page < MAX_PAGE:
            print(
                f"[WAIT] 次のページまで"
                f"{REQUEST_INTERVAL}秒待機します"
            )

            time.sleep(
                REQUEST_INTERVAL
            )


finally:

    # ==================
    # 終了
    # ==================

    session.close()


# ==================
# 結果表示
# ==================

print(
    "\n" + "=" * 80
)
print(
    f"総取得件数 : {total_count}"
)
print(
    "=" * 80
)

end_time = time.time()

print(
    "[INFO] スクリプト完了"
    f"（実行時間: "
    f"{end_time - start_time:.2f} 秒）"
)


# In[ ]:




