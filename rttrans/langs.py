"""Language tables.

Whisper detects ISO-639-1-ish codes; NLLB uses FLORES-200 codes.
LANGS maps whisper code -> (english name, japanese name, nllb code or None).
"""
from __future__ import annotations

# whisper_code: (name_en, name_ja, nllb_code)
LANGS: dict[str, tuple[str, str, str | None]] = {
    "en":  ("English",    "英語",         "eng_Latn"),
    "ja":  ("Japanese",   "日本語",       "jpn_Jpan"),
    "zh":  ("Chinese",    "中国語",       "zho_Hans"),
    "ko":  ("Korean",     "韓国語",       "kor_Hang"),
    "de":  ("German",     "ドイツ語",     "deu_Latn"),
    "fr":  ("French",     "フランス語",   "fra_Latn"),
    "es":  ("Spanish",    "スペイン語",   "spa_Latn"),
    "pt":  ("Portuguese", "ポルトガル語", "por_Latn"),
    "it":  ("Italian",    "イタリア語",   "ita_Latn"),
    "ru":  ("Russian",    "ロシア語",     "rus_Cyrl"),
    "nl":  ("Dutch",      "オランダ語",   "nld_Latn"),
    "pl":  ("Polish",     "ポーランド語", "pol_Latn"),
    "tr":  ("Turkish",    "トルコ語",     "tur_Latn"),
    "ar":  ("Arabic",     "アラビア語",   "arb_Arab"),
    "hi":  ("Hindi",      "ヒンディー語", "hin_Deva"),
    "th":  ("Thai",       "タイ語",       "tha_Thai"),
    "vi":  ("Vietnamese", "ベトナム語",   "vie_Latn"),
    "id":  ("Indonesian", "インドネシア語", "ind_Latn"),
    "ms":  ("Malay",      "マレー語",     "zsm_Latn"),
    "sv":  ("Swedish",    "スウェーデン語", "swe_Latn"),
    "da":  ("Danish",     "デンマーク語", "dan_Latn"),
    "no":  ("Norwegian",  "ノルウェー語", "nob_Latn"),
    "nb":  ("Norwegian Bokmal", "ノルウェー語", "nob_Latn"),
    "nn":  ("Norwegian Nynorsk", "ノルウェー語", "nno_Nyno"),
    "fi":  ("Finnish",    "フィンランド語", "fin_Latn"),
    "cs":  ("Czech",      "チェコ語",     "ces_Latn"),
    "sk":  ("Slovak",     "スロバキア語", "slk_Latn"),
    "sl":  ("Slovenian",  "スロベニア語", "slv_Latn"),
    "hr":  ("Croatian",   "クロアチア語", "hrv_Latn"),
    "sr":  ("Serbian",    "セルビア語",   "srp_Cyrl"),
    "bs":  ("Bosnian",    "ボスニア語",   "bos_Latn"),
    "mk":  ("Macedonian", "マケドニア語", "mkd_Cyrl"),
    "bg":  ("Bulgarian",  "ブルガリア語", "bul_Cyrl"),
    "uk":  ("Ukrainian",  "ウクライナ語", "ukr_Cyrl"),
    "be":  ("Belarusian", "ベラルーシ語", "bel_Cyrl"),
    "ro":  ("Romanian",   "ルーマニア語", "ron_Latn"),
    "hu":  ("Hungarian",  "ハンガリー語", "hun_Latn"),
    "el":  ("Greek",      "ギリシャ語",   "ell_Grek"),
    "he":  ("Hebrew",     "ヘブライ語",   "heb_Hebr"),
    "yi":  ("Yiddish",    "イディッシュ語", "ydd_Hebr"),
    "et":  ("Estonian",   "エストニア語", "ekk_Latn"),
    "lv":  ("Latvian",    "ラトビア語",   "lvs_Latn"),
    "lt":  ("Lithuanian", "リトアニア語", "lit_Latn"),
    "ca":  ("Catalan",    "カタルーニャ語", "cat_Latn"),
    "eu":  ("Basque",     "バスク語",     "eus_Latn"),
    "gl":  ("Galician",   "ガリシア語",   "glg_Latn"),
    "cy":  ("Welsh",      "ウェールズ語", "cym_Latn"),
    "br":  ("Breton",     "ブルトン語",   "bre_Latn"),
    "oc":  ("Occitan",    "オック語",     "oci_Latn"),
    "is":  ("Icelandic",  "アイスランド語", "isl_Latn"),
    "fo":  ("Faroese",    "フェロー語",   "fao_Latn"),
    "mt":  ("Maltese",    "マルタ語",     "mlt_Latn"),
    "sq":  ("Albanian",   "アルバニア語", "als_Latn"),
    "ur":  ("Urdu",       "ウルドゥー語", "urd_Arab"),
    "bn":  ("Bengali",    "ベンガル語",   "ben_Beng"),
    "ta":  ("Tamil",      "タミル語",     "tam_Taml"),
    "te":  ("Telugu",     "テルグ語",     "tel_Telu"),
    "kn":  ("Kannada",    "カンナダ語",   "kan_Knda"),
    "ml":  ("Malayalam",  "マラヤーラム語", "mal_Mlym"),
    "mr":  ("Marathi",    "マラーティー語", "mar_Deva"),
    "gu":  ("Gujarati",   "グジャラート語", "guj_Gujr"),
    "pa":  ("Punjabi",    "パンジャーブ語", "pan_Guru"),
    "ne":  ("Nepali",     "ネパール語",   "npi_Deva"),
    "si":  ("Sinhala",    "シンハラ語",   "sin_Sinh"),
    "as":  ("Assamese",   "アッサム語",   "asm_Beng"),
    "sd":  ("Sindhi",     "シンド語",     "snd_Arab"),
    "fa":  ("Persian",    "ペルシャ語",   "pes_Arab"),
    "ps":  ("Pashto",     "パシュトー語", "pbt_Arab"),
    "tg":  ("Tajik",      "タジク語",     "tgk_Cyrl"),
    "kk":  ("Kazakh",     "カザフ語",     "kaz_Cyrl"),
    "uz":  ("Uzbek",      "ウズベク語",   "uzn_Latn"),
    "tk":  ("Turkmen",    "トルクメン語", "tuk_Latn"),
    "mn":  ("Mongolian",  "モンゴル語",   "khk_Cyrl"),
    "my":  ("Burmese",    "ビルマ語",     "mya_Mymr"),
    "km":  ("Khmer",      "クメール語",   "khm_Khmr"),
    "lo":  ("Lao",        "ラオ語",       "lao_Laoo"),
    "ka":  ("Georgian",   "ジョージア語", "kat_Geor"),
    "hy":  ("Armenian",   "アルメニア語", "hye_Armn"),
    "sw":  ("Swahili",    "スワヒリ語",   "swh_Latn"),
    "yo":  ("Yoruba",     "ヨルバ語",     "yor_Latn"),
    "so":  ("Somali",     "ソマリ語",     "som_Latn"),
    "ha":  ("Hausa",      "ハウサ語",     "hau_Latn"),
    "sn":  ("Shona",      "ショナ語",     "sna_Latn"),
    "af":  ("Afrikaans",  "アフリカーンス語", "afr_Latn"),
    "am":  ("Amharic",    "アムハラ語",   "amh_Ethi"),
    "tl":  ("Tagalog",    "タガログ語",   "tgl_Latn"),
    "jw":  ("Javanese",   "ジャワ語",     "jav_Latn"),
    "su":  ("Sundanese",  "スンダ語",     "sun_Latn"),
    "yue": ("Cantonese",  "広東語",       "yue_Hant"),
    "mi":  ("Maori",      "マオリ語",     "mri_Latn"),
    "la":  ("Latin",      "ラテン語",     "lat_Latn"),
    "sa":  ("Sanskrit",   "サンスクリット", "san_Deva"),
    "lb":  ("Luxembourgish", "ルクセンブルク語", "ltz_Latn"),
    "bo":  ("Tibetan",    "チベット語",   "bod_Tibt"),
    "mg":  ("Malagasy",   "マダガスカル語", "plt_Latn"),
    "ln":  ("Lingala",    "リンガラ語",   "lin_Latn"),
    "tt":  ("Tatar",      "タタール語",   "tat_Cyrl"),
    "ba":  ("Bashkir",    "バシキール語", "bak_Cyrl"),
    "haw": ("Hawaiian",   "ハワイ語",     "haw_Latn"),
    "ht":  ("Haitian Creole", "ハイチ語", "hat_Latn"),
}

# Whisper may emit these aliases; normalize to canonical keys above.
ALIASES = {"tl": "tl", "fil": "tl", "zh-cn": "zh", "zh-tw": "zh", "iw": "he", "in": "id"}

ACTION_IGNORE = "ignore"        # 無視
ACTION_SHOW = "show"            # 原文のみ表示
ACTION_TRANSLATE = "translate"  # 翻訳して表示
ACTIONS = (ACTION_IGNORE, ACTION_SHOW, ACTION_TRANSLATE)
ACTION_LABELS = {ACTION_IGNORE: "無視", ACTION_SHOW: "原文のみ", ACTION_TRANSLATE: "翻訳"}


def normalize(code: str | None) -> str:
    if not code:
        return "unknown"
    code = code.lower().strip()
    return ALIASES.get(code, code)


def lang_name(code: str) -> str:
    code = normalize(code)
    if code in LANGS:
        return LANGS[code][1]
    return code


def nllb_code(whisper_code: str) -> str | None:
    whisper_code = normalize(whisper_code)
    entry = LANGS.get(whisper_code)
    return entry[2] if entry else None


def whisper_to_nllb(code: str) -> str | None:
    return nllb_code(code)


def all_known_codes() -> list[str]:
    return sorted(LANGS.keys())
