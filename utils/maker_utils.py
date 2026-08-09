import hashlib
import re
import unicodedata

from typing import Any


# ==================================================
# メーカーslug設定
# ==================================================

MAKER_SLUG_MAP = {
    "オリンピア": "olympia",
    "オリンピアエステート": "olympia-estate",
    "オーイズミラボ": "oizumi-labo",
    "サンスリー": "sansei",
    "ピーセカンド": "p-second",
    "エンタテインメント": "entertainment",
    "オーイズミ": "oizumi",
    "ＳＡＮＹＯ": "sanyo",
    "パイオニア": "pioneer",
    "ハイライツ": "highlights",
    "テクノコーシン": "techno-koshin",
    "ＳＡＮＫＹＯ": "sankyo",
    "山佐": "yamasa",
    "メーシー": "macy",
    "山佐ネクスト": "yamasa-next",
    "ミズホ": "mizuho",
    "ユニバーサルブロス": "universal-bros",
    "コナミアミューズメント": "konami-amusement",
    "ゼクロスクリエイティブ": "zecross-creative",
    "エレコ": "eleco",
    "アルゼ": "aruze",
    "アリストクラート": "aristocrat",
    "エンターライズ": "enterise",
    "クロスアルファ": "cross-alpha",
    "サンセイＲ＆Ｄ": "sansei-rd",
    "タイヨーエレック": "taiyo-elec",
    "新日テクノロジー": "shin-nichi-technology",
    "大都技研": "daito",
    "岡崎産業": "okazaki",
    "ユニバーサル": "universal",
    "アークテクニコ": "arc-technico",
    "アデリオン": "adellion",
    "アムテックス": "amtex",
    "アイ電子": "ai-denshi",
    "アクロス": "across",
    "イレブン": "eleven",
    "ＥＸＣＩＴＥ": "excite",
    "ＳＮＫプレイモア": "snk-playmore",
    "エフ": "f",
    "エマ": "ema",
    "エーアイ": "ai",
    "オーゼキ": "ozeki",
    "オッケー.": "ok",
    "オズ": "oz",
    "オレンジ": "orange",
    "カルミナ": "carmina",
    "北電子": "kitac",
    "京楽": "kyoraku",
    "アビリット": "abilit",
    "ＫＰＥ": "kpe",
    "コルモ": "colmo",
    "サボハニ": "sabohani",
    "サミー": "sammy",
    "スター": "star",
    "スパイキー": "spiky",
    "清龍ジャパン": "seiryu-japan",
    "清龍ゲームジャパン": "seiryu-japan",    
    "セブンリーグ": "seven-league",
    "大一": "daiichi",
    "大東音響": "daito-onkyo",
    "タイヨー": "taiyo",
    "高砂": "takasago",
    "ＤＡＸＥＬ": "daxel",
    "ディ・ライト": "d-light",
    "トリビー": "trivy",
    "七匠": "nanasho",
    "ニイガタ電子": "niigata-denshi",
    "西陣": "nishijin",
    "ニューアーク": "new-ark",
    "ニューギン": "newgin",
    "ＮＥＴ": "net",
    "ネット": "net",
    "パオン・ディーピー": "paon-dp",
    "パラジェーピー": "para-jp",
    "パル工業": "pal-kogyo",
    "バルテック": "baltec",
    "ビスティ": "bisty",
    "ファースト": "first",
    "藤商事": "fuji",
    "平和": "heiwa",
    "ベルコ": "bellco",
    "ボーダー": "border",
    "マックスアライド": "max-allied",
    "マツヤ商会": "matsuya-shokai",
    "ヤーマ": "yama",
    "ロデオ": "rodeo",
    "ＪＩＮ": "jin",
    "ＪＰＳ": "jps",
    "ＪＦＪ": "jfj",
    "ＩＧＴ": "igt",
    "ブロス": "bros",
    "SANKYO": "sankyo",
    "銀座": "ginza",
    "ジェイビー": "jb",
    "パオンディービー": "paon-db",
    "ソフィア": "sophia",
    "ラスター": "luster",
    "TRIVY": "trivy",
    "三協電子": "sankyo-denshi",
    "三洋": "sanyo",
    "アイゲート": "igate",
    "アイドル": "idol",
    "エキサイト": "excite",
    "アリストクラートテクノロジーズ": "aristocrat",
    "ニイガタ電子精機": "niigata-denshi",
    "ビーム": "beam",
    "ユニバーサルエンターテインメント": "universal",
    "レオスター": "leostar",
    "三洋物産": "sanyo",
    "藤興": "fujiko",
    "遊人": "yujin",
    "A-gon": "a-gon",
    "D-light": "d-light",
    "EXCITE": "excite",
    "JFJ": "jfj",
    "SanThree": "sansei",
    "SANYO": "sanyo",    
    "サンセイ": "sansei",
    "マルホン": "maruhon",
    "奥村遊機": "okumura",
    "奥村": "okumura",
    "高尾": "takao",
    "大一商会": "daiichi",
    "竹屋": "takeya",
    "豊丸産業": "toyomaru",
    "豊丸": "toyomaru",
    "Daiichi": "daiichi",
    "Daiichie": "daiichi",
    "愛喜": "aiki",
}

# ==================================================
# メーカーslug作成
# ==================================================

def create_maker_slug(
    maker_name: Any,
) -> str:
    """
    メーカー名からURL用slugを生成する。

    MAKER_SLUG_MAPに登録されている場合は、
    登録済みslugを優先する。

    半角英数字へ変換できないメーカー名の場合は、
    一意性を保つためハッシュ値を使用する。
    """
    if maker_name is None:
        return ""

    maker_name_text = str(
        maker_name
    ).strip()

    if not maker_name_text:
        return ""

    mapped_slug = MAKER_SLUG_MAP.get(
        maker_name_text
    )

    if mapped_slug:
        return mapped_slug

    normalized_name = unicodedata.normalize(
        "NFKC",
        maker_name_text,
    )

    ascii_slug = normalized_name.lower()

    ascii_slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        ascii_slug,
    )

    ascii_slug = ascii_slug.strip(
        "-"
    )

    if ascii_slug:
        return ascii_slug

    maker_hash = hashlib.sha1(
        maker_name_text.encode(
            "utf-8"
        )
    ).hexdigest()[:10]

    return f"maker-{maker_hash}"


def ensure_unique_maker_slugs(
    makers: list[dict[str, Any]],
) -> None:
    """
    同一slugが複数メーカーへ
    割り当てられないようにする。
    """
    used_slugs: dict[str, str] = {}

    for maker in makers:
        maker_name = str(
            maker.get("name")
            or ""
        ).strip()

        base_slug = create_maker_slug(
            maker_name
        )

        if not base_slug:
            maker["slug"] = ""
            continue

        slug = base_slug

        if (
            slug in used_slugs
            and used_slugs[slug] != maker_name
        ):
            maker_hash = hashlib.sha1(
                maker_name.encode(
                    "utf-8"
                )
            ).hexdigest()[:6]

            slug = (
                f"{base_slug}-"
                f"{maker_hash}"
            )

        used_slugs[slug] = maker_name
        maker["slug"] = slug