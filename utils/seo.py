# utils/seo.py

from urllib.parse import urljoin

from utils.config import (
    SITE_NAME,
    SITE_URL,
    SITE_DESCRIPTION,
    DEFAULT_OG_IMAGE,
    DEFAULT_ROBOTS,
    FAVICON_URL,
    APPLE_TOUCH_ICON_URL,
)


def build_absolute_url(path: str = "/") -> str:
    """
    サイト内パスから絶対URLを生成する。

    例:
        "/"                     -> "https://blog-pachislot.com/"
        "/machines/"            -> "https://blog-pachislot.com/machines/"
        "machines/123/"         -> "https://blog-pachislot.com/machines/123/"
        完全なURL                -> そのまま返す
    """
    if not path:
        path = "/"

    path = str(path).strip()

    if path.startswith(("http://", "https://")):
        return path

    base_url = SITE_URL.rstrip("/") + "/"
    relative_path = path.lstrip("/")

    return urljoin(base_url, relative_path)


def normalize_page_title(
    title: str | None = None,
    *,
    include_site_name: bool = True,
) -> str:
    """
    ページタイトルを生成する。

    例:
        title=None
            -> "実機相場サイト"

        title="機種一覧"
            -> "機種一覧 | 実機相場サイト"

        title="機種一覧 | 実機相場サイト"
            -> そのまま返す
    """
    if not title:
        return SITE_NAME

    title = str(title).strip()

    if not include_site_name:
        return title

    if SITE_NAME in title:
        return title

    return f"{title} | {SITE_NAME}"


def normalize_meta_description(
    description: str | None = None,
) -> str:
    """
    meta descriptionを生成する。

    descriptionが空の場合はSITE_DESCRIPTIONを使用する。
    改行や連続した空白は1つの空白へ整理する。
    """
    if not description:
        description = SITE_DESCRIPTION

    description = str(description)

    return " ".join(description.split())


def normalize_robots(
    robots: str | None = None,
) -> str:
    """
    robotsの値を生成する。

    通常ページ:
        index,follow

    404ページなど:
        noindex,nofollow
    """
    if not robots:
        return DEFAULT_ROBOTS

    return str(robots).strip()


def normalize_og_image(
    og_image: str | None = None,
) -> str:
    """
    OGP画像URLを生成する。

    og_imageが未指定の場合:
        DEFAULT_OG_IMAGE

    相対パスの場合:
        SITE_URLを付けた絶対URL
    """
    if not og_image:
        return DEFAULT_OG_IMAGE

    return build_absolute_url(og_image)


def build_seo_data(
    *,
    title: str | None = None,
    description: str | None = None,
    canonical_path: str = "/",
    robots: str | None = None,
    og_image: str | None = None,
    og_type: str = "website",
    og_image_alt: str | None = None,
    include_site_name: bool = True,
) -> dict:
    """
    Jinjaテンプレートへ渡すSEO情報をまとめて生成する。

    使用例:

        seo = build_seo_data(
            title="機種一覧",
            description="パチンコ・パチスロ実機の一覧です。",
            canonical_path="/machines/",
        )

        html = template.render(
            ...,
            **seo,
        )

    戻り値:
        {
            "site_name": ...,
            "page_title": ...,
            "meta_description": ...,
            "canonical_url": ...,
            "robots": ...,
            "og_type": ...,
            "og_image": ...,
            "og_image_alt": ...,
            "favicon_url": ...,
            "apple_touch_icon_url": ...,
        }
    """
    page_title = normalize_page_title(
        title,
        include_site_name=include_site_name,
    )

    meta_description = normalize_meta_description(description)

    canonical_url = build_absolute_url(canonical_path)

    robots_value = normalize_robots(robots)

    og_image_url = normalize_og_image(og_image)

    if not og_image_alt:
        og_image_alt = page_title

    return {
        "site_name": SITE_NAME,
        "page_title": page_title,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "robots": robots_value,
        "og_type": og_type,
        "og_image": og_image_url,
        "og_image_alt": og_image_alt,
        "favicon_url": FAVICON_URL,
        "apple_touch_icon_url": APPLE_TOUCH_ICON_URL,
    }


def build_noindex_seo_data(
    *,
    title: str,
    description: str | None = None,
    canonical_path: str = "/",
    og_image: str | None = None,
    og_type: str = "website",
    og_image_alt: str | None = None,
    include_site_name: bool = True,
) -> dict:
    """
    noindexページ用のSEO情報を生成する。

    404、検索結果、公開対象外ページなどで使用する。
    """
    return build_seo_data(
        title=title,
        description=description,
        canonical_path=canonical_path,
        robots="noindex,nofollow",
        og_image=og_image,
        og_type=og_type,
        og_image_alt=og_image_alt,
        include_site_name=include_site_name,
    )