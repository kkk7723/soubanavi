#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sys
import time

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import TemplateNotFound


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
    ASSET_PREFIX,
    OUTPUT_DIR,
    PROJECT_ROOT,
    ROOT_PREFIX,
    SITE_DESCRIPTION,
    SITE_NAME,
    TEMPLATE_DIR,
)

from utils.page_utils import (
    create_jinja_environment,
)

from utils.seo import (
    build_seo_data,
)

from utils.static_utils import (
    copy_common_static_files,
)


# ==================================================
# ページ設定
# ==================================================

USER_PAGE_SETTINGS = (
    {
        "page_key": "history",
        "template_name": "user/history.html",
        "output_directory_name": "history",
        "page_title": (
            "閲覧履歴｜実機相場ナビ"
        ),
        "meta_description": (
            "実機相場ナビで最近閲覧した"
            "パチンコ・パチスロ中古実機を"
            "確認できるページです。"
        ),
        "canonical_path": "/history/",
    },
    {
        "page_key": "favorites",
        "template_name": "user/favorites.html",
        "output_directory_name": "favorites",
        "page_title": (
            "お気に入り｜実機相場ナビ"
        ),
        "meta_description": (
            "実機相場ナビでお気に入りに登録した"
            "パチンコ・パチスロ中古実機を"
            "確認できるページです。"
        ),
        "canonical_path": "/favorites/",
    },
)


# ==================================================
# テンプレート用データ作成
# ==================================================

def build_user_page_context(
    page_setting: dict[str, str],
    generated_at: datetime,
) -> dict[str, Any]:
    """
    履歴・お気に入りページへ渡す
    テンプレート変数を作成する。

    Parameters
    ----------
    page_setting : dict[str, str]
        対象ページの設定。

    generated_at : datetime
        HTML生成日時。

    Returns
    -------
    dict[str, Any]
        Jinja2テンプレートへ渡す値。
    """
    seo = build_seo_data(
        title=page_setting[
            "page_title"
        ],
        description=page_setting[
            "meta_description"
        ],
        canonical_path=page_setting[
            "canonical_path"
        ],
        robots="noindex,follow",
        og_type="website",
    )


    return {
        # SEO情報
        **seo,

        # 共通テンプレート用
        "site_name": SITE_NAME,
        "site_description": SITE_DESCRIPTION,
        "current_year": generated_at.year,
        "is_top_page": False,

        # ページ情報
        "page_key": page_setting[
            "page_key"
        ],
        "page_title": page_setting[
            "page_title"
        ],
        "page_description": page_setting[
            "meta_description"
        ],

        # パンくず
        "breadcrumbs": [
            {
                "title": "トップ",
                "url": "../",
            },
            {
                "title": (
                    "閲覧履歴"
                    if page_setting[
                        "page_key"
                    ] == "history"
                    else "お気に入り"
                ),
                "url": None,
            },
        ],

        # 日時情報
        "generated_at": generated_at,
        "updated_at": generated_at,

        # output/history/index.html、
        # output/favorites/index.htmlから見た相対パス
        "root_prefix": "../",
        "asset_prefix": "../",
    }


# ==================================================
# 出力先作成
# ==================================================

def get_output_file_path(
    output_directory_name: str,
) -> Path:
    """
    ページごとの出力ファイルパスを返す。

    Parameters
    ----------
    output_directory_name : str
        output直下に作成するディレクトリ名。

    Returns
    -------
    Path
        index.htmlの出力先。
    """
    return (
        Path(OUTPUT_DIR)
        / output_directory_name
        / "index.html"
    )


# ==================================================
# 静的ファイルコピー
# ==================================================

def copy_user_page_static_files() -> None:
    """
    履歴・お気に入りページで使用する
    共通静的ファイルをoutputへコピーする。

    専用CSS・専用JavaScriptは作成せず、
    common.cssとcommon.jsを使用する。
    """
    copy_common_static_files(
        project_root_dir=PROJECT_ROOT,
        output_root_dir=OUTPUT_DIR,
    )


# ==================================================
# 1ページ生成
# ==================================================

def generate_user_page(
    environment: Any,
    page_setting: dict[str, str],
    generated_at: datetime,
) -> Path:
    """
    履歴またはお気に入りページを生成する。

    Parameters
    ----------
    environment : Any
        Jinja2環境。

    page_setting : dict[str, str]
        対象ページの設定。

    generated_at : datetime
        HTML生成日時。

    Returns
    -------
    Path
        生成したファイルのパス。
    """
    template_name = page_setting[
        "template_name"
    ]

    output_file_path = get_output_file_path(
        page_setting[
            "output_directory_name"
        ]
    )


    try:
        template = environment.get_template(
            template_name
        )

    except TemplateNotFound as error:
        raise FileNotFoundError(
            "Jinja2テンプレートが"
            "見つかりません: "
            f"{error.name}"
        ) from error


    context = build_user_page_context(
        page_setting=page_setting,
        generated_at=generated_at,
    )


    html = template.render(
        **context
    )


    output_file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    output_file_path.write_text(
        html,
        encoding="utf-8",
        newline="",
    )


    return output_file_path


# ==================================================
# 履歴・お気に入りページ生成
# ==================================================

def generate_user_pages() -> None:
    """
    templates/user/history.htmlと
    templates/user/favorites.htmlを使用して、

    output/history/index.htmlと
    output/favorites/index.htmlを生成する。
    """
    start_time = time.time()
    generated_at = datetime.now()


    Path(OUTPUT_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )


    # 共通CSS・JavaScript・画像などをコピー
    copy_user_page_static_files()


    # Jinja2環境を作成
    environment = create_jinja_environment(
        template_dir=TEMPLATE_DIR,
        site_name=SITE_NAME,
        site_description=SITE_DESCRIPTION,
        root_prefix=ROOT_PREFIX,
        asset_prefix=ASSET_PREFIX,
    )


    generated_files: list[Path] = []


    for page_setting in USER_PAGE_SETTINGS:
        output_file_path = generate_user_page(
            environment=environment,
            page_setting=page_setting,
            generated_at=generated_at,
        )

        generated_files.append(
            output_file_path
        )


    elapsed_time = (
        time.time()
        - start_time
    )


    # ==========================================
    # 実行結果表示
    # ==========================================

    print("=" * 60)

    print(
        "履歴・お気に入りページを"
        "生成しました。"
    )

    print("-" * 60)


    for output_file_path in generated_files:
        print(
            "出力先: "
            f"{output_file_path}"
        )


    print("-" * 60)

    print(
        "生成ページ数: "
        f"{len(generated_files):,}ページ"
    )

    print(
        "処理時間: "
        f"{elapsed_time:.2f}秒"
    )

    print("=" * 60)


# ==================================================
# 実行
# ==================================================

def main() -> None:
    """
    履歴・お気に入りページ生成処理を実行する。
    """
    try:
        generate_user_pages()

    except FileNotFoundError as error:
        print("-" * 60)

        print(
            "履歴・お気に入りページ生成に"
            "必要なファイルが見つかりません。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            "テンプレート配置を確認してください。"
        )

        print(
            f"{Path(TEMPLATE_DIR) / 'user' / 'history.html'}"
        )

        print(
            f"{Path(TEMPLATE_DIR) / 'user' / 'favorites.html'}"
        )

        raise

    except Exception as error:
        print("-" * 60)

        print(
            "履歴・お気に入りページ生成中に"
            "エラーが発生しました。"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


if __name__ == "__main__":
    main()


# In[ ]:




