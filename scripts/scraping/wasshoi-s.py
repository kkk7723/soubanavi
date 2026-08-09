#!/usr/bin/env python
# coding: utf-8

# In[1]:


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
now = datetime.now()

table_name = "result_table"



# ==================
# スクレイピングサイト設定
# ==================

SHOP_NAME = "パチスロ中古実機販売なら【パチスロわっしょい】"
SHOP_PRODUCT_ID = 5
CATEGORY = "slot"

BASE_URL = (
    "https://www.pachislowasshoi.jp/"
    "SHOP/33899/t01/list{}.html"
)

MAX_PAGE = 100
REQUEST_INTERVAL = 10  # ページ間の待機秒数


# ==================
# プロキシ
# ==================

def _resolve_proxy_for_batch(batch_index: int) -> str | None:

    mode = (PROXY_MODE or "none").strip().lower()

    if mode == "none":
        print(
            f"[INFO] Proxy for batch {batch_index}: "
            "(none直結)"
        )
        return None

    if mode != "list":

        raw = (PROXY_MODE or "").strip()

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
        int(PROXY_ROTATE_EVERY or 1)
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


def open_session(batch_index: int = 0) -> requests.Session:

    proxy = _resolve_proxy_for_batch(batch_index)

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
            "https": proxy
        }

    return session


# ==================
# DB
# ==================

def save_product(data: dict) -> None:

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
                datetime.now()
            )
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

    for page in range(MAX_PAGE):

        # list1.html、list2.html、list3.html……
        list_no = page + 1

        url = BASE_URL.format(list_no)

        print(f"\n{'=' * 80}")
        print(f"Page   : {page + 1}")
        print(f"URL    : {url}")

        try:
            response = session.get(
                url,
                timeout=30
            )

            response.raise_for_status()

        except requests.RequestException as e:
            print(
                f"[ERROR] ページ取得失敗: {e}"
            )
            break

        # 文字化け対策
        response.encoding = response.apparent_encoding

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # --------------------------
        # 商品一覧テーブル
        # --------------------------

        item_list = soup.select_one(
            "table.itemList"
        )

        if item_list is None:
            print(
                "[ERROR] table.itemListが見つかりません"
            )
            break

        # --------------------------
        # 1商品 = div.layout1
        # --------------------------

        products = item_list.select(
            "div.layout1"
        )

        page_count = 0

        for product in products:

            # ==========================
            # タイトル・商品URL
            # ==========================

            title_a = product.select_one(
                "h2.goods > a"
            )

            if title_a is None:
                continue

            machine_name = title_a.get_text(
                " ",
                strip=True
            )

            product_href = title_a.get(
                "href",
                ""
            ).strip()

            product_url = urljoin(
                url,
                product_href
            )

            # ==========================
            # 画像URL
            # ==========================

            image_url = ""

            img = product.select_one(
                "div.item img"
            )

            if img:

                image_src = img.get(
                    "src",
                    ""
                ).strip()

                if image_src:
                    image_url = urljoin(
                        url,
                        image_src
                    )

            # ==========================
            # 価格
            # ==========================

            price = ""

            price_tag = product.select_one(
                "div.price span"
            )

            if price_tag:

                price_text = price_tag.get_text(
                    " ",
                    strip=True
                )

                # 「110,000円」→「110000」
                price = re.sub(
                    r"[^\d]",
                    "",
                    price_text
                )

            # ==========================
            # 表示
            # ==========================

            print("-" * 80)
            print("ショップ:", SHOP_NAME)
            print("カテゴリ:", CATEGORY)
            print("機種名  :", machine_name)
            print("商品URL :", product_url)
            print("画像URL :", image_url)
            print("価格    :", price)

            # ==========================
            # DB保存
            # ==========================

            try:
                save_product({
                    "machine_name": machine_name,
                    "product_url": product_url,
                    "image_url": image_url,
                    "price": price
                })

                print("[DB] 保存完了")

            except sqlite3.Error as e:
                print(
                    f"[DB ERROR] 保存失敗: {e}"
                )
                continue

            page_count += 1
            total_count += 1

        print(
            f"\nページ取得件数 : {page_count}"
        )

        # 商品が無くなったら終了
        if page_count == 0:
            print(
                "商品がありません。終了します。"
            )
            break

        # 次のページへ進む前に待機
        if page < MAX_PAGE - 1:
            print(
                f"[WAIT] 次のページまで"
                f"{REQUEST_INTERVAL}秒待機します"
            )

            time.sleep(REQUEST_INTERVAL)


finally:

    # ==================
    # セッション終了
    # ==================

    session.close()


# ==================
# 結果表示
# ==================

print("\n" + "=" * 80)
print(f"総取得件数 : {total_count}")
print("=" * 80)


# ==================
# 終了
# ==================

end_time = time.time()

print(
    "[INFO] スクリプト完了"
    f"（実行時間: {end_time - start_time:.2f} 秒）"
)


# In[ ]:




