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
now = datetime.now()

table_name = "result_table"


# ==================
# スクレイピングサイト設定
# ==================

SHOP_NAME = "中古パチンコ・スロット実機販売専門店【中一商事】"
SHOP_PRODUCT_ID = 4
CATEGORY = "pachi"

BASE_URL = (
    "https://www.nakaiti.com/cgi-bin/search.cgi"
    "?mode=search"
    "&page={}"
    "&keyword=%92%86%8c%c3%83p%83%60%83%93%83R"
    "&category="
    "&order=.html"
)

MAX_PAGE = 60


# ==================
# アクセス制御設定
# ==================

REQUEST_INTERVAL = 60
MAX_RETRIES = 5
RETRY_BASE_WAIT = 300


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

total_count = 0


# ==================
# ページループ
# ==================

for page_index in range(MAX_PAGE):

    # page=0, 36, 72, 108...
    page_no = page_index * 36

    url = BASE_URL.format(page_no)

    print(f"\n{'=' * 80}")
    print(f"Page   : {page_index + 1}")
    print(f"Offset : {page_no}")
    print(f"URL    : {url}")

    response = None
    session = None

    # 429などに対する再試行
    for retry_count in range(MAX_RETRIES):

        # 再試行時にプロキシを切り替えられるようにする
        batch_index = page_index + retry_count

        session = open_session(batch_index)

        try:
            response = session.get(
                url,
                timeout=30
            )

            # 429の場合
            if response.status_code == 429:

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if retry_after and retry_after.isdigit():
                    wait_seconds = int(retry_after)
                else:
                    wait_seconds = (
                        RETRY_BASE_WAIT
                        * (2 ** retry_count)
                    )

                print(
                    "[WARN] 429 Too Many Requests "
                    f"({retry_count + 1}/{MAX_RETRIES})"
                )

                print(
                    f"[WAIT] {wait_seconds}秒待機します"
                )

                session.close()
                session = None

                time.sleep(wait_seconds)

                continue

            response.raise_for_status()

            # 正常取得できたら再試行ループ終了
            break

        except requests.RequestException as e:

            print(
                "[ERROR] ページ取得失敗 "
                f"({retry_count + 1}/{MAX_RETRIES}): "
                f"{e}"
            )

            if session is not None:
                session.close()
                session = None

            if retry_count >= MAX_RETRIES - 1:
                response = None
                break

            wait_seconds = (
                RETRY_BASE_WAIT
                * (2 ** retry_count)
            )

            print(
                f"[WAIT] {wait_seconds}秒後に再試行します"
            )

            time.sleep(wait_seconds)

    # 最大回数再試行しても取得できなかった場合
    if response is None or response.status_code != 200:

        print(
            "[ERROR] 最大再試行回数に達しました。"
            "終了します。"
        )

        if session is not None:
            session.close()

        break

    # 文字化け対策
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------
    # 商品一覧
    # --------------------------

    item_list = soup.select_one(
        "div.pop-model-contents-area"
    )

    if item_list is None:

        print(
            "[ERROR] div.pop-model-contents-areaが"
            "見つかりません"
        )

        if session is not None:
            session.close()

        break

    # 1商品 = div.pop-model-contents
    products = item_list.select(
        "div.pop-model-contents"
    )

    page_count = 0

    for product in products:

        # ==========================
        # タイトル・商品URL
        # ==========================

        title_a = product.select_one(
            "h3.pop-model-title-link-size "
            "a.pop-model-title-link"
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
            "p.pop-modecl-thumb img"
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
            "span.goods_price"
        )

        if price_tag:

            price_text = price_tag.get_text(
                " ",
                strip=True
            )

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

    if session is not None:
        session.close()
        session = None

    # 商品がなくなったら終了
    if page_count == 0:
        print(
            "商品がありません。終了します。"
        )
        break

    # 最終ページでなければ待機
    if page_index < MAX_PAGE - 1:

        print(
            f"[WAIT] 次のページまで"
            f"{REQUEST_INTERVAL}秒待機します"
        )

        time.sleep(REQUEST_INTERVAL)


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




