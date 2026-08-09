#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# upload_output.py

from __future__ import annotations

import posixpath
import shlex
import sys
import time
import zipfile

from datetime import datetime
from pathlib import Path

import paramiko


# ==================================================
# プロジェクトルート設定
# ==================================================

try:
    SCRIPT_DIR = (
        Path(__file__)
        .resolve()
        .parent
    )
except NameError:
    # JupyterLab上で実行した場合
    SCRIPT_DIR = (
        Path.cwd()
        .resolve()
    )


def find_project_root(
    start_dir: Path,
) -> Path:
    """
    現在位置から親ディレクトリを順番に遡り、
    utils/config.pyが存在する
    プロジェクトルートを取得する。
    """
    start_dir = start_dir.resolve()

    for candidate in (
        start_dir,
        *start_dir.parents,
    ):
        config_path = (
            candidate
            / "utils"
            / "config.py"
        )

        if config_path.is_file():
            return candidate

    raise FileNotFoundError(
        "utils/config.pyが見つかりません。\n"
        f"検索開始位置: {start_dir}"
    )


PROJECT_ROOT = find_project_root(
    SCRIPT_DIR
)

project_root_text = str(
    PROJECT_ROOT
)

if project_root_text not in sys.path:
    sys.path.insert(
        0,
        project_root_text,
    )


# ==================================================
# config.py読み込み
# ==================================================

from utils.config import (
    DELETE_LOCAL_ZIP_AFTER_UPLOAD,
    OUTPUT_DIR,
    PROJECT_DIR,
    PROJECT_ROOT,
    REMOTE_PUBLIC_DIR,
    SSH_HOST,
    SSH_PORT,
    SSH_PRIVATE_KEY_PASSWORD,
    SSH_PRIVATE_KEY_PATH,
    SSH_USER,
    UPLOAD_DIR,
    UPLOAD_EXTENSIONS,
    UPLOAD_ZIP_COMPRESSION_LEVEL,
)


# ==================================================
# アップロード設定
# ==================================================

UPLOAD_TIMESTAMP = (
    datetime.now()
    .strftime("%Y%m%d_%H%M%S")
)

ZIP_FILE_NAME = (
    f"upload_{PROJECT_DIR}_{UPLOAD_TIMESTAMP}.zip"
)

ZIP_PATH = (
    UPLOAD_DIR
    / ZIP_FILE_NAME
)


# ==================================================
# 設定確認
# ==================================================

def validate_settings() -> None:
    """
    アップロード前に必要な設定と
    ディレクトリを確認する。
    """
    if not OUTPUT_DIR.is_dir():
        raise FileNotFoundError(
            "outputディレクトリが見つかりません: "
            f"{OUTPUT_DIR}"
        )

    if not SSH_PRIVATE_KEY_PATH.is_file():
        raise FileNotFoundError(
            "SSH秘密鍵が見つかりません: "
            f"{SSH_PRIVATE_KEY_PATH}"
        )

    if not SSH_HOST.strip():
        raise ValueError(
            "SSH_HOSTが設定されていません。"
        )

    if not SSH_USER.strip():
        raise ValueError(
            "SSH_USERが設定されていません。"
        )

    if not REMOTE_PUBLIC_DIR.strip():
        raise ValueError(
            "REMOTE_PUBLIC_DIRが設定されていません。"
        )

    if not UPLOAD_EXTENSIONS:
        raise ValueError(
            "UPLOAD_EXTENSIONSが空です。"
        )

    UPLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ==================================================
# リモートパス処理
# ==================================================

def normalize_remote_path(
    remote_path: str,
) -> str:
    """
    SSHユーザーのホームディレクトリを基準とした
    相対パスへ整形する。

    例:
        ~/example.com/public_html
        ↓
        example.com/public_html
    """
    normalized_path = (
        remote_path
        .replace("\\", "/")
        .strip()
    )

    if normalized_path.startswith("~/"):
        normalized_path = (
            normalized_path[2:]
        )

    normalized_path = (
        normalized_path
        .lstrip("/")
        .rstrip("/")
    )

    if not normalized_path:
        raise ValueError(
            "リモートパスが空です。"
        )

    path_parts = (
        normalized_path
        .split("/")
    )

    if ".." in path_parts:
        raise ValueError(
            "リモートパスに親ディレクトリ参照は"
            "使用できません: "
            f"{remote_path}"
        )

    return normalized_path


# ==================================================
# ZIP対象ファイル取得
# ==================================================

def get_upload_files() -> list[Path]:
    """
    outputディレクトリから
    アップロード対象ファイルを取得する。
    """
    allowed_extensions = {
        extension.lower()
        for extension in UPLOAD_EXTENSIONS
    }

    upload_files: list[Path] = []

    for file_path in OUTPUT_DIR.rglob("*"):
        if not file_path.is_file():
            continue

        if (
            file_path.suffix.lower()
            not in allowed_extensions
        ):
            continue

        upload_files.append(
            file_path
        )

    upload_files.sort(
        key=lambda path: (
            path
            .relative_to(OUTPUT_DIR)
            .as_posix()
        )
    )

    if not upload_files:
        raise RuntimeError(
            "アップロード対象ファイルが"
            "見つかりません。\n"
            f"検索先: {OUTPUT_DIR}\n"
            f"対象拡張子: {UPLOAD_EXTENSIONS}"
        )

    return upload_files


# ==================================================
# ZIP作成
# ==================================================

def create_upload_zip(
    upload_files: list[Path],
) -> int:
    """
    output配下の対象ファイルをZIP化する。

    ZIP内ではoutput配下の
    ディレクトリ構造をそのまま維持する。

    戻り値:
        ZIPファイルサイズ
    """
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    total_files = len(
        upload_files
    )

    print(
        "=" * 70
    )
    print(
        "[ZIP作成開始]"
    )
    print(
        f"対象ディレクトリ: {OUTPUT_DIR}"
    )
    print(
        f"対象ファイル数: {total_files:,}件"
    )
    print(
        f"ZIP出力先: {ZIP_PATH}"
    )
    print(
        "=" * 70
    )

    with zipfile.ZipFile(
        file=ZIP_PATH,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=(
            UPLOAD_ZIP_COMPRESSION_LEVEL
        ),
        allowZip64=True,
    ) as zip_file:
        for index, file_path in enumerate(
            upload_files,
            start=1,
        ):
            relative_path = (
                file_path
                .relative_to(OUTPUT_DIR)
            )

            archive_name = (
                relative_path
                .as_posix()
            )

            # WebPは既に圧縮済みなので無圧縮で格納する
            compress_type = (
                zipfile.ZIP_STORED
                if file_path.suffix.lower() == ".webp"
                else zipfile.ZIP_DEFLATED
            )

            zip_file.write(
                filename=file_path,
                arcname=archive_name,
                compress_type=compress_type,
            )

            if (
                index % 1000 == 0
                or index == total_files
            ):
                print(
                    "[ZIP作成中] "
                    f"{index:,} / "
                    f"{total_files:,}件"
                )

    zip_size = (
        ZIP_PATH
        .stat()
        .st_size
    )

    print(
        "[ZIP圧縮完了] "
        f"{ZIP_PATH}"
    )

    print(
        "[ZIPサイズ] "
        f"{zip_size / 1024 / 1024:,.2f} MB"
    )

    return zip_size

# ==================================================
# 秘密鍵読み込み
# ==================================================

def load_private_key() -> paramiko.PKey:
    """
    SSH秘密鍵を読み込む。

    RSA、Ed25519、ECDSAを順番に試す。
    """
    key_classes = (
        paramiko.RSAKey,
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
    )

    load_errors: list[str] = []

    for key_class in key_classes:
        try:
            return (
                key_class
                .from_private_key_file(
                    filename=str(
                        SSH_PRIVATE_KEY_PATH
                    ),
                    password=(
                        SSH_PRIVATE_KEY_PASSWORD
                    ),
                )
            )

        except Exception as error:
            load_errors.append(
                f"{key_class.__name__}: "
                f"{error}"
            )

    raise paramiko.SSHException(
        "SSH秘密鍵を読み込めませんでした。\n"
        + "\n".join(load_errors)
    )


# ==================================================
# SSHコマンド実行
# ==================================================

def run_remote_command(
    ssh: paramiko.SSHClient,
    command: str,
    description: str,
) -> str:
    """
    SSHコマンドを実行して
    終了コードを確認する。
    """
    print(
        f"[SSH処理開始] {description}"
    )

    stdin = None
    stdout = None
    stderr = None

    try:
        stdin, stdout, stderr = (
            ssh.exec_command(
                command,
            )
        )

        exit_status = (
            stdout.channel
            .recv_exit_status()
        )

        stdout_text = (
            stdout
            .read()
            .decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )

        stderr_text = (
            stderr
            .read()
            .decode(
                "utf-8",
                errors="replace",
            )
            .strip()
        )

        if stdout_text:
            print(
                "[SSH標準出力]"
            )
            print(
                stdout_text
            )

        if stderr_text:
            print(
                "[SSH標準エラー]"
            )
            print(
                stderr_text
            )

        if exit_status != 0:
            raise RuntimeError(
                "リモートコマンドの実行に"
                "失敗しました。\n"
                f"処理: {description}\n"
                f"終了コード: {exit_status}\n"
                f"標準エラー: {stderr_text}"
            )

        print(
            f"[SSH処理完了] {description}"
        )

        return stdout_text

    finally:
        for stream in (
            stdin,
            stdout,
            stderr,
        ):
            if stream is None:
                continue

            try:
                stream.close()
            except Exception:
                pass

        if stdout is not None:
            try:
                stdout.channel.close()
            except Exception:
                pass


# ==================================================
# SFTPアップロード
# ==================================================

def upload_zip_file(
    ssh: paramiko.SSHClient,
    remote_zip_path: str,
) -> None:
    """
    ZIPファイルをSFTPでアップロードする。

    転送後はローカルとリモートの
    ファイルサイズを比較する。
    """
    local_size = (
        ZIP_PATH
        .stat()
        .st_size
    )

    last_displayed_percent = -1

    def progress_callback(
        transferred: int,
        total: int,
    ) -> None:
        nonlocal last_displayed_percent

        if total <= 0:
            return

        percent = int(
            transferred
            * 100
            / total
        )

        display_percent = (
            percent // 10
        ) * 10

        if (
            display_percent
            == last_displayed_percent
        ):
            return

        last_displayed_percent = (
            display_percent
        )

        print(
            "[アップロード中] "
            f"{percent:3d}% "
            f"("
            f"{transferred / 1024 / 1024:,.2f}"
            f" / "
            f"{total / 1024 / 1024:,.2f}"
            f" MB)"
        )

    print(
        "[ZIPアップロード開始] "
        f"{remote_zip_path}"
    )

    with ssh.open_sftp() as sftp:
        sftp.put(
            localpath=str(
                ZIP_PATH
            ),
            remotepath=remote_zip_path,
            callback=progress_callback,
            confirm=True,
        )

        remote_stat = (
            sftp.stat(
                remote_zip_path
            )
        )

    if remote_stat.st_size != local_size:
        raise RuntimeError(
            "アップロード後の"
            "ファイルサイズが一致しません。\n"
            f"ローカル: {local_size:,} bytes\n"
            f"リモート: {remote_stat.st_size:,} bytes"
        )

    print(
        "[ZIPアップロード完了] "
        f"{remote_zip_path}"
    )


# ==================================================
# デプロイ処理
# ==================================================

def deploy_output() -> None:
    """
    outputディレクトリをZIP化し、
    SFTPでアップロードして、
    公開ディレクトリへ展開する。
    """
    start_time = (
        time.perf_counter()
    )

    validate_settings()

    remote_public_dir = (
        normalize_remote_path(
            REMOTE_PUBLIC_DIR
        )
    )

    remote_zip_path = (
        posixpath.join(
            remote_public_dir,
            ZIP_FILE_NAME,
        )
    )

    upload_files = (
        get_upload_files()
    )

    zip_size = (
        create_upload_zip(
            upload_files
        )
    )

    print(
        "=" * 70
    )
    print(
        "[アップロード設定]"
    )
    print(
        f"プロジェクト: {PROJECT_DIR}"
    )
    print(
        f"SSH接続先: "
        f"{SSH_USER}@{SSH_HOST}:{SSH_PORT}"
    )
    print(
        f"公開先: ~/{remote_public_dir}"
    )
    print(
        f"対象ファイル数: "
        f"{len(upload_files):,}件"
    )
    print(
        "=" * 70
    )

    private_key = (
        load_private_key()
    )

    ssh = (
        paramiko.SSHClient()
    )

    # 初回接続時のホスト鍵を自動登録する。
    ssh.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    try:
        ssh.connect(
            hostname=SSH_HOST,
            port=SSH_PORT,
            username=SSH_USER,
            pkey=private_key,
            timeout=30,
            banner_timeout=30,
            auth_timeout=30,
            look_for_keys=False,
            allow_agent=False,
        )

        print(
            "[SSH接続完了]"
        )

        quoted_remote_public_dir = (
            shlex.quote(
                remote_public_dir
            )
        )

        # 公開ディレクトリを作成
        create_directory_command = (
            "mkdir -p "
            f"~/{quoted_remote_public_dir}"
        )

        run_remote_command(
            ssh=ssh,
            command=create_directory_command,
            description=(
                "公開ディレクトリ作成"
            ),
        )

        # ZIPファイルをアップロード
        upload_zip_file(
            ssh=ssh,
            remote_zip_path=remote_zip_path,
        )

        quoted_zip_file_name = (
            shlex.quote(
                ZIP_FILE_NAME
            )
        )

        # ZIP展開
        #
        # set -e:
        # 途中でコマンドが失敗した場合に停止する。
        #
        # unzip -o:
        # 既存ファイルを確認なしで上書きする。
        #
        # rm:
        # 展開成功後にサーバー側ZIPを削除する。
        deploy_command = f"""
set -e
cd ~/{quoted_remote_public_dir}
unzip -oq {quoted_zip_file_name} -d .
rm -f {quoted_zip_file_name}
"""

        run_remote_command(
            ssh=ssh,
            command=deploy_command,
            description=(
                "ZIP展開と"
                "サーバー側ZIP削除"
            ),
        )

    finally:
        try:
            ssh.close()

            print(
                "[SSH接続終了]"
            )

        except Exception as error:
            print(
                "[警告] SSH終了時エラー: "
                f"{error}"
            )

    if DELETE_LOCAL_ZIP_AFTER_UPLOAD:
        try:
            ZIP_PATH.unlink()

            print(
                "[ローカルZIP削除] "
                f"{ZIP_PATH}"
            )

        except FileNotFoundError:
            pass

        except Exception as error:
            print(
                "[警告] ローカルZIPを"
                "削除できませんでした: "
                f"{error}"
            )

    elapsed_time = (
        time.perf_counter()
        - start_time
    )

    print(
        "=" * 70
    )
    print(
        "[アップロード完了]"
    )
    print(
        f"公開先: ~/{remote_public_dir}"
    )
    print(
        f"対象ファイル数: "
        f"{len(upload_files):,}件"
    )
    print(
        f"ZIPサイズ: "
        f"{zip_size / 1024 / 1024:,.2f} MB"
    )
    print(
        f"処理時間: "
        f"{elapsed_time:,.1f}秒"
    )
    print(
        "=" * 70
    )


# ==================================================
# 実行
# ==================================================

if __name__ == "__main__":
    try:
        deploy_output()

    except KeyboardInterrupt:
        print(
            "\n[中断] "
            "ユーザーにより処理が"
            "中断されました。"
        )

        raise

    except Exception as error:
        print(
            "\n[アップロード失敗]"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise


# In[ ]:




