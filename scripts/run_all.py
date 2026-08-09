import subprocess
import sys
import time
from pathlib import Path


# ==================================================
# 設定
# ==================================================

# 各スクリプト実行後の待機秒数
SLEEP_SECONDS = 10


# ==================================================
# ディレクトリ設定
# ==================================================

# 配置場所:
#
# soubanavi/
# ├── scripts/
# │   ├── run_all.ipynb
# │   ├── run_all.py
# │   ├── scraping/
# │   ├── database/
# │   ├── generate/
# │   ├── upload/
# │   └── mail/
# └── utils/
#
# Jupyter Notebook:
#   Path.cwd() が soubanavi/scripts
#
# Pythonスクリプト:
#   Path(__file__).parent が soubanavi/scripts

try:
    SCRIPTS_DIR = (
        Path(__file__)
        .resolve()
        .parent
    )
except NameError:
    # Jupyter Notebookで実行する場合
    SCRIPTS_DIR = Path.cwd().resolve()


# soubanavi/scripts の1階層上
PROJECT_ROOT = SCRIPTS_DIR.parent


# ==================================================
# 実行対象
# ==================================================

# PROJECT_ROOT（soubanavi）からの相対パス
# 上から順番に実行する
SCRIPTS = [
    # --------------------------------------------------
    # スクレイピング
    # --------------------------------------------------
    Path("scripts/scraping/a-pachi-p.py"),
    Path("scripts/scraping/home-p.py"),
    Path("scripts/scraping/nakaiti-p.py"),
    Path("scripts/scraping/aslot-s.py"),
    Path("scripts/scraping/bank-s.py"),
    Path("scripts/scraping/home-s.py"),
    Path("scripts/scraping/nakaiti-s.py"),
    Path("scripts/scraping/wasshoi-s.py"),

    # --------------------------------------------------
    # データベース処理
    # --------------------------------------------------
    Path("scripts/database/sync_machine_master.py"),    
    Path("scripts/database/normalize-p.py"),
    Path("scripts/database/normalize-s.py"),
    Path("scripts/database/match-p.py"),
    Path("scripts/database/match-s.py"),
    Path("scripts/database/update_product_summary.py"),
    Path("scripts/database/update_price_history.py"),

    # --------------------------------------------------
    # HTML・各種ファイル生成
    # --------------------------------------------------
    Path("scripts/generate/machine_detail.py"),
    Path("scripts/generate/maker_pages.py"),
    Path("scripts/generate/recent_machines_pages.py"),
    Path("scripts/generate/price_range_pages.py"),
    Path("scripts/generate/price_down_today_pages.py"),
    Path("scripts/generate/ranking_index.py"),
    Path("scripts/generate/ranking_low_price_pages.py"),
    Path("scripts/generate/machine_index.py"),
    Path("scripts/generate/user_pages.py"),
    Path("scripts/generate/index.py"),
    Path("scripts/generate/sitemap.py"),

    # --------------------------------------------------
    # アップロード
    # --------------------------------------------------
    Path("scripts/upload/upload_output.py"),

    # --------------------------------------------------
    # メール送信
    # --------------------------------------------------
    Path("scripts/mail/mail.py"),
]


# ==================================================
# スクリプト実行
# ==================================================

def run_script(
    script_path: Path,
) -> tuple[bool, float, int | None]:
    """
    Pythonスクリプトを1件実行する。

    戻り値:
        成功したか
        処理時間
        終了コード
    """

    script_start_time = time.time()

    try:
        completed_process = subprocess.run(
            [
                sys.executable,
                str(script_path),
            ],
            check=True,

            # 各スクリプトのカレントディレクトリを
            # soubanavi直下に統一する
            cwd=str(PROJECT_ROOT),
        )

        elapsed_time = (
            time.time()
            - script_start_time
        )

        return (
            True,
            elapsed_time,
            completed_process.returncode,
        )

    except subprocess.CalledProcessError as error:
        elapsed_time = (
            time.time()
            - script_start_time
        )

        return (
            False,
            elapsed_time,
            error.returncode,
        )


# ==================================================
# 連続実行
# ==================================================

def run_scripts():
    """
    指定したPythonスクリプトを
    上から順番に実行する。

    エラーが発生しても、
    次のスクリプトを続けて実行する。
    """

    start_time = time.time()

    success_count = 0
    failed_count = 0
    missing_count = 0

    failed_scripts = []
    missing_scripts = []

    total_count = len(
        SCRIPTS
    )

    print("=" * 70)
    print("連続実行を開始します")
    print(f"scriptsディレクトリ: {SCRIPTS_DIR}")
    print(f"プロジェクトルート: {PROJECT_ROOT}")
    print(f"Python実行環境: {sys.executable}")
    print(f"実行対象: {total_count}ファイル")
    print(f"待機時間: {SLEEP_SECONDS}秒")
    print("=" * 70)

    for index, relative_path in enumerate(
        SCRIPTS,
        start=1,
    ):
        script_path = (
            PROJECT_ROOT
            / relative_path
        ).resolve()

        print()
        print("-" * 70)
        print(
            f"[{index}/{total_count}] "
            f"実行中: "
            f"{relative_path.as_posix()}"
        )
        print(
            f"実ファイル: {script_path}"
        )
        print("-" * 70)

        # --------------------------------------------------
        # ファイル存在確認
        # --------------------------------------------------

        if not script_path.is_file():
            print(
                "[ファイルなし] "
                f"{script_path}"
            )

            missing_count += 1

            missing_scripts.append(
                relative_path.as_posix()
            )

        else:
            try:
                (
                    is_success,
                    elapsed_time,
                    return_code,
                ) = run_script(
                    script_path
                )

                if is_success:
                    success_count += 1

                    print(
                        "[成功] "
                        f"{relative_path.as_posix()}"
                    )

                    print(
                        "処理時間: "
                        f"{elapsed_time:.2f}秒"
                    )

                else:
                    failed_count += 1

                    failed_scripts.append(
                        {
                            "script": (
                                relative_path
                                .as_posix()
                            ),
                            "return_code": (
                                return_code
                            ),
                        }
                    )

                    print(
                        "[実行エラー] "
                        f"{relative_path.as_posix()}"
                    )

                    print(
                        "終了コード: "
                        f"{return_code}"
                    )

                    print(
                        "処理時間: "
                        f"{elapsed_time:.2f}秒"
                    )

            except Exception as error:
                failed_count += 1

                failed_scripts.append(
                    {
                        "script": (
                            relative_path
                            .as_posix()
                        ),
                        "return_code": None,
                    }
                )

                print(
                    "[予期せぬエラー] "
                    f"{relative_path.as_posix()}"
                )

                print(
                    f"{type(error).__name__}: "
                    f"{error}"
                )

        # --------------------------------------------------
        # 待機
        # --------------------------------------------------

        if (
            index < total_count
            and SLEEP_SECONDS > 0
        ):
            print()
            print(
                f"[待機] "
                f"{SLEEP_SECONDS}秒"
            )

            time.sleep(
                SLEEP_SECONDS
            )

    # ==================================================
    # 実行結果
    # ==================================================

    total_elapsed_time = (
        time.time()
        - start_time
    )

    print()
    print("=" * 70)
    print("指定スクリプトの連続実行が完了しました")
    print("-" * 70)
    print(f"成功: {success_count}件")
    print(f"実行失敗: {failed_count}件")
    print(f"ファイルなし: {missing_count}件")
    print(f"合計: {total_count}件")
    print(
        "総処理時間: "
        f"{total_elapsed_time:.2f}秒"
    )

    # --------------------------------------------------
    # 実行失敗一覧
    # --------------------------------------------------

    if failed_scripts:
        print()
        print("[実行失敗一覧]")

        for failed_script in failed_scripts:
            script_name = (
                failed_script["script"]
            )

            return_code = (
                failed_script["return_code"]
            )

            if return_code is None:
                print(
                    f"  - {script_name}"
                )
            else:
                print(
                    f"  - {script_name} "
                    f"(終了コード: {return_code})"
                )

    # --------------------------------------------------
    # ファイルなし一覧
    # --------------------------------------------------

    if missing_scripts:
        print()
        print("[ファイルなし一覧]")

        for missing_script in missing_scripts:
            print(
                f"  - {missing_script}"
            )

    print("=" * 70)

    return {
        "success": success_count,
        "failed": failed_count,
        "missing": missing_count,
        "total": total_count,
        "elapsed_time": total_elapsed_time,
    }


# ==================================================
# エントリーポイント
# ==================================================

if __name__ == "__main__":
    try:
        result = run_scripts()

    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print(
            "ユーザー操作により"
            "連続実行を中断しました"
        )
        print("=" * 70)

        # Jupyterでカーネルまで終了しないように、
        # Notebook実行時はsys.exit()を使用しない
        if "__file__" in globals():
            sys.exit(130)