from __future__ import annotations

from typing import TypedDict


class Breadcrumb(TypedDict):
    """パンくずリスト1項目の型定義。"""

    title: str
    url: str | None


def create_breadcrumb(
    title: str,
    url: str | None = None,
) -> Breadcrumb:
    """
    パンくずリストの1項目を作成する。

    Args:
        title:
            表示名。
        url:
            サイトルートを基準にした相対URL。
            現在のページは None を指定する。

    Returns:
        パンくずリストの1項目。
    """
    return {
        "title": title,
        "url": url,
    }


def create_home_breadcrumb() -> Breadcrumb:
    """ホーム用のパンくずを作成する。"""
    return create_breadcrumb(
        title="ホーム",
        url="",
    )


def create_machine_list_breadcrumbs() -> list[Breadcrumb]:
    """機種一覧ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="機種一覧",
            url=None,
        ),
    ]


def create_machine_detail_breadcrumbs(
    machine_name: str,
) -> list[Breadcrumb]:
    """機種詳細ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="機種一覧",
            url="machines/",
        ),
        create_breadcrumb(
            title=machine_name,
            url=None,
        ),
    ]


def create_maker_list_breadcrumbs() -> list[Breadcrumb]:
    """メーカー一覧ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="メーカー一覧",
            url=None,
        ),
    ]


def create_maker_detail_breadcrumbs(
    maker_name: str,
) -> list[Breadcrumb]:
    """メーカー詳細ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="メーカー一覧",
            url="makers/",
        ),
        create_breadcrumb(
            title=maker_name,
            url=None,
        ),
    ]


def create_ranking_list_breadcrumbs() -> list[Breadcrumb]:
    """ランキング一覧ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="ランキング一覧",
            url=None,
        ),
    ]


def create_ranking_detail_breadcrumbs(
    ranking_name: str,
) -> list[Breadcrumb]:
    """ランキング詳細ページ用のパンくずを作成する。"""
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title="ランキング一覧",
            url="rankings/",
        ),
        create_breadcrumb(
            title=ranking_name,
            url=None,
        ),
    ]


def create_page_breadcrumbs(
    page_title: str,
) -> list[Breadcrumb]:
    """
    固定ページ用のパンくずを作成する。

    プライバシーポリシー、利用規約、サイトについてなど、
    ホーム直下の固定ページで使用する。
    """
    return [
        create_home_breadcrumb(),
        create_breadcrumb(
            title=page_title,
            url=None,
        ),
    ]