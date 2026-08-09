#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sys
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.etree.ElementTree import (
    Element,
    ElementTree,
    SubElement,
    indent,
)


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
# soubanavi/scripts/generate/
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


# importパス設定後に読み込む
from utils.config import (
    OUTPUT_DIR,
    SITE_URL,
)



# ==================================================
# 初期設定
# ==================================================

START_TIME = time.time()


# ==================================================
# サイト設定
# ==================================================

# 公開サイトのURL
# 必ず実際のドメインへ変更してください。

# sitemap.xml出力先
SITEMAP_OUTPUT_FILE_PATH = os.path.join(
    OUTPUT_DIR,
    "sitemap.xml",
)


# ==================================================
# 除外設定
# ==================================================

# サイトマップへ掲載しないHTMLファイル
EXCLUDED_HTML_FILES = {
    "404.html",
}


# サイトマップへ掲載しないフォルダ
#
# 必要になった場合に追加してください。
EXCLUDED_DIRECTORIES: set[str] = {
    "private",
    "test",
}


# ==================================================
# URL設定
# ==================================================

# URLへ付けるchangefreq
DEFAULT_CHANGEFREQ = "daily"


# 通常ページのpriority
DEFAULT_PRIORITY = "0.7"


# URLごとのpriority
PRIORITY_MAP = {
    "/": "1.0",
    "/machines/": "0.9",
    "/makers/": "0.9",
    "/rankings/": "0.9",
}


# URLごとのchangefreq
CHANGEFREQ_MAP = {
    "/": "daily",
    "/machines/": "daily",
    "/makers/": "weekly",
    "/rankings/": "daily",
}


# ==================================================
# 補助関数
# ==================================================

def normalize_site_url(
    site_url: str,
) -> str:
    """
    サイトURLを正規化する。

    例:
    https://example.com/
    ↓
    https://example.com
    """
    normalized_url = str(
        site_url
    ).strip()

    if not normalized_url:
        raise ValueError(
            "SITE_URLが空です。"
        )

    if not normalized_url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        raise ValueError(
            "SITE_URLはhttp://または"
            "https://から始めてください: "
            f"{normalized_url}"
        )

    return normalized_url.rstrip(
        "/"
    )


def validate_output_directory() -> None:
    """
    outputフォルダが存在するか確認する。
    """
    if not os.path.isdir(
        OUTPUT_DIR
    ):
        raise FileNotFoundError(
            "outputフォルダが"
            "見つかりません: "
            f"{OUTPUT_DIR}"
        )


def should_exclude_html_file(
    html_file_path: Path,
    output_root_path: Path,
) -> bool:
    """
    HTMLファイルをサイトマップから
    除外するか判定する。
    """
    relative_path = html_file_path.relative_to(
        output_root_path
    )

    # ファイル名による除外
    if relative_path.as_posix() in EXCLUDED_HTML_FILES:
        return True

    if html_file_path.name in EXCLUDED_HTML_FILES:
        return True

    # フォルダ名による除外
    relative_parts = set(
        relative_path.parts[:-1]
    )

    if (
        relative_parts
        & EXCLUDED_DIRECTORIES
    ):
        return True

    return False


def html_path_to_url_path(
    html_file_path: Path,
    output_root_path: Path,
) -> str:
    """
    HTMLファイルのパスを
    公開URLのパスへ変換する。

    例:
    output/index.html
    ↓
    /

    output/machines/index.html
    ↓
    /machines/

    output/machines/101.html
    ↓
    /machines/101.html
    """
    relative_path = html_file_path.relative_to(
        output_root_path
    )

    relative_posix_path = (
        relative_path.as_posix()
    )

    # ルートのindex.html
    if relative_posix_path == "index.html":
        return "/"

    # 各フォルダのindex.html
    if relative_posix_path.endswith(
        "/index.html"
    ):
        directory_path = (
            relative_posix_path[
                :-len("index.html")
            ]
        )

        return f"/{directory_path}"

    # 通常のHTMLファイル
    return f"/{relative_posix_path}"


def encode_url_path(
    url_path: str,
) -> str:
    """
    URLパスをURL用にエンコードする。

    スラッシュ、ピリオド、ハイフンなどは
    そのまま残す。
    """
    return quote(
        url_path,
        safe="/.-_~",
    )


def build_page_url(
    site_url: str,
    url_path: str,
) -> str:
    """
    サイトURLとURLパスから
    ページURLを作成する。
    """
    encoded_path = encode_url_path(
        url_path
    )

    if encoded_path == "/":
        return f"{site_url}/"

    return (
        f"{site_url}"
        f"{encoded_path}"
    )


def get_file_lastmod(
    file_path: Path,
) -> str:
    """
    ファイルの最終更新日時を
    sitemap用のUTC日時に変換する。

    例:
    2026-07-23T02:30:00+00:00
    """
    modified_timestamp = (
        file_path.stat().st_mtime
    )

    modified_datetime = (
        datetime.fromtimestamp(
            modified_timestamp,
            tz=timezone.utc,
        )
    )

    return modified_datetime.replace(
        microsecond=0
    ).isoformat()


def get_page_priority(
    url_path: str,
) -> str:
    """
    URLに対応するpriorityを取得する。
    """
    if url_path in PRIORITY_MAP:
        return PRIORITY_MAP[
            url_path
        ]

    # 機種詳細
    if url_path.startswith(
        "/machines/"
    ):
        return "0.8"

    # メーカー詳細
    if url_path.startswith(
        "/makers/"
    ):
        return "0.8"

    # ランキング詳細
    if url_path.startswith(
        "/rankings/"
    ):
        return "0.8"

    return DEFAULT_PRIORITY


def get_page_changefreq(
    url_path: str,
) -> str:
    """
    URLに対応するchangefreqを取得する。
    """
    if url_path in CHANGEFREQ_MAP:
        return CHANGEFREQ_MAP[
            url_path
        ]

    if url_path.startswith(
        "/machines/"
    ):
        return "daily"

    if url_path.startswith(
        "/rankings/"
    ):
        return "daily"

    if url_path.startswith(
        "/makers/"
    ):
        return "weekly"

    return DEFAULT_CHANGEFREQ


# ==================================================
# HTMLファイル取得
# ==================================================

def get_html_files() -> list[Path]:
    """
    outputフォルダ内のHTMLファイルを
    再帰的に取得する。
    """
    output_root_path = Path(
        OUTPUT_DIR
    ).resolve()

    html_files = []

    for html_file_path in (
        output_root_path.rglob(
            "*.html"
        )
    ):
        if not html_file_path.is_file():
            continue

        if should_exclude_html_file(
            html_file_path,
            output_root_path,
        ):
            continue

        html_files.append(
            html_file_path
        )

    return sorted(
        html_files,
        key=lambda path: (
            html_path_to_url_path(
                path,
                output_root_path,
            )
        ),
    )


# ==================================================
# サイトマップデータ作成
# ==================================================

def create_sitemap_entries(
    site_url: str,
    html_files: list[Path],
) -> list[dict[str, str]]:
    """
    HTMLファイルからサイトマップ用の
    URL情報を作成する。
    """
    output_root_path = Path(
        OUTPUT_DIR
    ).resolve()

    entries = []

    seen_urls = set()

    for html_file_path in html_files:
        url_path = html_path_to_url_path(
            html_file_path,
            output_root_path,
        )

        page_url = build_page_url(
            site_url,
            url_path,
        )

        # 重複URLを除外
        if page_url in seen_urls:
            continue

        seen_urls.add(
            page_url
        )

        entry = {
            "loc": page_url,
            "lastmod": get_file_lastmod(
                html_file_path
            ),
            "changefreq": (
                get_page_changefreq(
                    url_path
                )
            ),
            "priority": (
                get_page_priority(
                    url_path
                )
            ),
        }

        entries.append(
            entry
        )

    return entries


# ==================================================
# XML作成
# ==================================================

def create_sitemap_xml(
    entries: list[dict[str, str]],
) -> ElementTree:
    """
    サイトマップXMLを作成する。
    """
    namespace = (
        "http://www.sitemaps.org/"
        "schemas/sitemap/0.9"
    )

    urlset_element = Element(
        "urlset",
        {
            "xmlns": namespace,
        },
    )

    for entry in entries:
        url_element = SubElement(
            urlset_element,
            "url",
        )

        loc_element = SubElement(
            url_element,
            "loc",
        )

        loc_element.text = entry[
            "loc"
        ]

        lastmod_element = SubElement(
            url_element,
            "lastmod",
        )

        lastmod_element.text = entry[
            "lastmod"
        ]

        changefreq_element = SubElement(
            url_element,
            "changefreq",
        )

        changefreq_element.text = entry[
            "changefreq"
        ]

        priority_element = SubElement(
            url_element,
            "priority",
        )

        priority_element.text = entry[
            "priority"
        ]

    xml_tree = ElementTree(
        urlset_element
    )

    # Python 3.9以降でインデントを整える
    indent(
        xml_tree,
        space="    ",
        level=0,
    )

    return xml_tree


# ==================================================
# XML書き込み
# ==================================================

def write_sitemap_xml(
    xml_tree: ElementTree,
) -> None:
    """
    sitemap.xmlを保存する。
    """
    output_file_path = Path(
        SITEMAP_OUTPUT_FILE_PATH
    )

    output_file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    xml_tree.write(
        output_file_path,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )


# ==================================================
# サイトマップ生成
# ==================================================

def generate_sitemap() -> None:
    """
    outputフォルダ内のHTMLを走査して
    sitemap.xmlを生成する。
    """
    site_url = normalize_site_url(
        SITE_URL
    )

    validate_output_directory()

    html_files = get_html_files()

    if not html_files:
        raise RuntimeError(
            "サイトマップへ登録できる"
            "HTMLファイルがありません。"
        )

    entries = create_sitemap_entries(
        site_url,
        html_files,
    )

    if not entries:
        raise RuntimeError(
            "サイトマップへ登録できる"
            "URLがありません。"
        )

    xml_tree = create_sitemap_xml(
        entries
    )

    write_sitemap_xml(
        xml_tree
    )

    elapsed_time = (
        time.time()
        - START_TIME
    )

    print("=" * 60)
    print("サイトマップを生成しました。")

    print(
        "出力先: "
        f"{SITEMAP_OUTPUT_FILE_PATH}"
    )

    print(
        "登録URL数: "
        f"{len(entries):,}件"
    )

    print(
        "除外ファイル: "
        + ", ".join(
            sorted(
                EXCLUDED_HTML_FILES
            )
        )
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
        generate_sitemap()

    except Exception as error:
        print("-" * 60)

        print(
            "サイトマップ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


# In[ ]:




