
# utils/static_utils.py

import shutil

from collections.abc import Iterable
from pathlib import Path


def should_copy_image(
    source_path: Path,
    output_path: Path,
) -> bool:
    """
    画像ファイルをコピーする必要があるか判定する。

    次の場合はコピーする。
    ・出力先にファイルが存在しない
    ・ファイルサイズが異なる
    ・コピー元の更新日時が新しい

    shutil.copy2()で更新日時も維持するため、
    2回目以降の差分判定が可能になる。
    """
    if not output_path.is_file():
        return True

    source_stat = source_path.stat()
    output_stat = output_path.stat()

    # ファイルサイズが異なる場合
    if source_stat.st_size != output_stat.st_size:
        return True

    # コピー元のほうが新しい場合
    if source_stat.st_mtime_ns > output_stat.st_mtime_ns:
        return True

    return False


def copy_image_directory_incrementally(
    source_dir: Path,
    output_dir: Path,
) -> tuple[int, int]:
    """
    画像ディレクトリを差分コピーする。

    コピー元に存在し、次のいずれかに該当する画像だけコピーする。

    ・出力先に存在しない
    ・ファイルサイズが異なる
    ・コピー元の更新日時が新しい

    戻り値:
        copied_count:
            コピーしたファイル数

        skipped_count:
            変更がないためコピーしなかったファイル数
    """
    copied_count = 0
    skipped_count = 0

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for source_file_path in source_dir.rglob("*"):
        if not source_file_path.is_file():
            continue

        relative_file_path = (
            source_file_path.relative_to(
                source_dir
            )
        )

        output_file_path = (
            output_dir
            / relative_file_path
        )

        if not should_copy_image(
            source_path=source_file_path,
            output_path=output_file_path,
        ):
            skipped_count += 1
            continue

        output_file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            source_file_path,
            output_file_path,
        )

        copied_count += 1

    return (
        copied_count,
        skipped_count,
    )


def copy_static_files(
    project_root_dir: str | Path,
    output_root_dir: str | Path,
    relative_paths: Iterable[str | Path],
) -> None:
    """
    staticディレクトリ内の指定ファイルまたは
    ディレクトリを、相対パス構造を維持したまま
    outputへコピーする。

    static/imgディレクトリだけは差分コピーする。

    CSS・JavaScriptなど、img以外のファイルと
    ディレクトリは従来どおり毎回コピーする。

    ファイル指定例:
        relative_paths=(
            "css/machine_detail.css",
            "js/machine_detail.js",
        )

    ディレクトリ指定例:
        relative_paths=(
            "css",
            "js",
            "img",
        )

    コピー元:
        project_root/static/...

    コピー先:
        output_root/...
    """
    project_root_path = Path(
        project_root_dir
    ).resolve()

    output_root_path = Path(
        output_root_dir
    ).resolve()

    static_root_path = (
        project_root_path
        / "static"
    )

    if not static_root_path.is_dir():
        raise FileNotFoundError(
            "staticディレクトリが見つかりません: "
            f"{static_root_path}"
        )

    for relative_path in relative_paths:
        relative_item_path = Path(
            relative_path
        )

        # 絶対パスや親ディレクトリ参照を防止
        if relative_item_path.is_absolute():
            raise ValueError(
                "relative_pathsには相対パスを指定してください: "
                f"{relative_item_path}"
            )

        if ".." in relative_item_path.parts:
            raise ValueError(
                "親ディレクトリを参照するパスは指定できません: "
                f"{relative_item_path}"
            )

        source_path = (
            static_root_path
            / relative_item_path
        )

        output_path = (
            output_root_path
            / relative_item_path
        )

        if not source_path.exists():
            raise FileNotFoundError(
                "静的ファイルまたはディレクトリが"
                "見つかりません: "
                f"{source_path}"
            )

        # ==========================================
        # ファイルの場合
        # ==========================================

        if source_path.is_file():
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                source_path,
                output_path,
            )

            print(
                "[静的ファイルコピー] "
                f"{source_path} -> {output_path}"
            )

            continue

        # ==========================================
        # imgディレクトリの場合
        # 差分コピー
        # ==========================================

        if (
            source_path.is_dir()
            and relative_item_path.parts
            and relative_item_path.parts[0] == "img"
        ):
            copied_count, skipped_count = (
                copy_image_directory_incrementally(
                    source_dir=source_path,
                    output_dir=output_path,
                )
            )

            print(
                "[画像差分コピー] "
                f"{source_path} -> {output_path} "
                f"コピー: {copied_count:,}件 / "
                f"変更なし: {skipped_count:,}件"
            )

            continue

        # ==========================================
        # img以外のディレクトリの場合
        # 従来どおり毎回コピー
        # ==========================================

        if source_path.is_dir():
            output_path.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copytree(
                source_path,
                output_path,
                dirs_exist_ok=True,
                copy_function=shutil.copy2,
            )

            print(
                "[静的ディレクトリコピー] "
                f"{source_path} -> {output_path}"
            )

            continue

        raise ValueError(
            "コピーできない静的項目です: "
            f"{source_path}"
        )


def copy_common_static_files(
    project_root_dir: str | Path,
    output_root_dir: str | Path,
) -> None:
    """
    共通静的ファイルおよびディレクトリを
    staticからoutputへコピーする。

    コピー対象:
        static/css                  -> output/css
        static/js                   -> output/js
        static/img                  -> output/img
        static/favicon.ico          -> output/favicon.ico
        static/favicon-48x48.png    -> output/favicon-48x48.png
        static/favicon-96x96.png    -> output/favicon-96x96.png
        static/favicon-192x192.png  -> output/favicon-192x192.png
        static/favicon-512x512.png  -> output/favicon-512x512.png
        static/apple-touch-icon.png -> output/apple-touch-icon.png
        static/site.webmanifest     -> output/site.webmanifest
        static/robots.txt           -> output/robots.txt

    imgのみ差分コピーになる。
    その他のファイルおよびディレクトリは
    毎回コピーする。
    """
    copy_static_files(
        project_root_dir=project_root_dir,
        output_root_dir=output_root_dir,
        relative_paths=(
            "css",
            "js",
            "img",
            "favicon.ico",
            "favicon-48x48.png",
            "favicon-96x96.png",
            "favicon-192x192.png",
            "favicon-512x512.png",
            "apple-touch-icon.png",
            "site.webmanifest",
            "robots.txt",
        ),
    )