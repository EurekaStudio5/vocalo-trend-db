# -*- coding: utf-8 -*-
"""
ボカロトレンドデータベース データ収集スクリプト
YouTubeの公開検索結果ページ (ytInitialData) からデータを取得する。APIキー不要。
毎日1回タスクスケジューラから実行される想定。

出力:
  data/videos.json     週間ランキング動画
  data/producers.json  ボカロPデータベース（登録者1万人以上）
  data/meta.json       更新日時など
  data/history/        日次スナップショット（伸び率分析用）
"""
import bisect
import json
import math
import os
import re
import sys
import time
import random
import datetime
from pathlib import Path

import requests

# Windowsコンソール(cp932)でも絵文字入りタイトルを出力できるようにする
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
CHANNELS_DIR = DATA_DIR / "channels"   # チャンネルごとの全ボカロ楽曲リスト

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}
# 英語圏ボカロ検索用（英語UIで検索すると英語圏の結果が出やすくなる）
HEADERS_EN = {**HEADERS, "Accept-Language": "en-US,en;q=0.9"}

# YouTube Data API v3（api_key.txt があれば統計系をAPIで取得するハイブリッド構成。
# 検索系はクォータ消費が大きい(100unit/回)ためスクレイピングを継続）
API_KEY_FILE = BASE_DIR / "api_key.txt"
# 環境変数を優先（GitHub Actions等のクラウド実行ではSecretsから渡す）
YT_API_KEY = (os.environ.get("YT_API_KEY", "").strip()
              or (API_KEY_FILE.read_text(encoding="utf-8").strip()
                  if API_KEY_FILE.exists() else None)
              or None)
YT_API = "https://www.googleapis.com/youtube/v3"


# APIクォータ使用量カウンタ（list系は1リクエスト=1ユニット。無料枠は1日10,000）
API_UNITS = 0


def _safe_err(e):
    """エラーメッセージからAPIキーを除去（URL入り例外がログに残るのを防ぐ）"""
    s = str(e)
    return s.replace(YT_API_KEY, "***") if YT_API_KEY else s


def api_get(endpoint, **params):
    """YouTube Data API 呼び出し（キー未設定/エラー時は None → スクレイピングにフォールバック）"""
    global API_UNITS
    if not YT_API_KEY:
        return None
    API_UNITS += 1
    params["key"] = YT_API_KEY
    try:
        r = requests.get(f"{YT_API}/{endpoint}", params=params, timeout=20)
        if r.status_code != 200:
            log(f"  API {endpoint} HTTP {r.status_code}: {_safe_err(r.text[:120])}")
            return None
        return r.json()
    except requests.RequestException as e:
        log(f"  APIエラー: {_safe_err(e)}")
        return None


# 公開データに連絡先メール等が混入しないように除去する
EMAIL_RE = re.compile(r"[\w.+-]+\s*[@＠]\s*[\w-]+\s*[.．]\s*[\w.．-]+")


def scrub_pii(text):
    return EMAIL_RE.sub("", text or "")


def parse_iso_duration(s):
    """'PT3M45S' → 秒"""
    if not s:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return None
    d, h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def _chunks(lst, n=50):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def api_videos(video_ids):
    """videos.list を50件ずつバッチ → 動画情報のリスト（曲データのコンパクト形式）"""
    out = []
    now = datetime.datetime.now(datetime.timezone.utc)
    for chunk in _chunks(list(video_ids)):
        j = api_get("videos", part="snippet,statistics,contentDetails",
                    id=",".join(chunk), maxResults=50)
        if not j:
            return None if not out else out
        for it in j.get("items", []):
            sn = it.get("snippet", {})
            st = it.get("statistics", {})
            pub = sn.get("publishedAt")
            days = None
            if pub:
                try:
                    dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    days = max((now - dt).total_seconds() / 86400, 0.05)
                except ValueError:
                    pass
            title = sn.get("title", "")
            desc = sn.get("description", "") or ""
            out.append({
                "id": it["id"],
                "t": title[:60],
                "v": int(st["viewCount"]) if st.get("viewCount") else None,
                "likes": int(st["likeCount"]) if st.get("likeCount") else None,
                "d": round(days, 2) if days is not None else None,
                "len": parse_iso_duration(it.get("contentDetails", {}).get("duration")),
                "publishedAt": pub,
                # ボカロ曲判定はタイトル+概要欄で行う（タイトルにボーカル名がないPに対応）
                "voca": is_vocalo_title(title) or is_vocalo_title(desc[:800]),
                # カバー（歌ってみた）判定。歌い手動画の混入防止
                "cov": is_cover_video(title, desc[:800]),
            })
        time.sleep(0.1)
    return out


def api_channels(channel_ids):
    """channels.list を50件ずつバッチ → {channelId: 詳細}"""
    out = {}
    for chunk in _chunks(list(channel_ids)):
        j = api_get("channels", part="snippet,statistics",
                    id=",".join(chunk), maxResults=50)
        if not j:
            return None if not out else out
        for it in j.get("items", []):
            sn = it.get("snippet", {})
            st = it.get("statistics", {})
            info = {
                "channelId": it["id"],
                "name": sn.get("title", ""),
                "description": scrub_pii(sn.get("description"))[:200],
                "thumbnail": (sn.get("thumbnails", {}).get("high")
                              or sn.get("thumbnails", {}).get("default") or {}).get("url", ""),
            }
            if sn.get("customUrl"):
                info["handle"] = sn["customUrl"]
            if sn.get("publishedAt"):
                info["joined"] = sn["publishedAt"][:10]
            if st.get("subscriberCount"):
                info["subscribers"] = int(st["subscriberCount"])
            if st.get("viewCount"):
                info["totalViews"] = int(st["viewCount"])
            if st.get("videoCount"):
                info["totalVideos"] = int(st["videoCount"])
            out[it["id"]] = info
        time.sleep(0.1)
    return out


def api_channel_upload_ids(channel_id, max_videos=600):
    """アップロード動画のID一覧（新しい順）"""
    uploads = "UU" + channel_id[2:]
    ids, token = [], None
    while len(ids) < max_videos:
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if token:
            params["pageToken"] = token
        j = api_get("playlistItems", **params)
        if not j:
            break
        ids += [it["contentDetails"]["videoId"] for it in j.get("items", [])]
        token = j.get("nextPageToken")
        if not token:
            break
        time.sleep(0.1)
    return ids

# 検索フィルタ (sp パラメータ): 期間 + 視聴回数順/関連度順 + 動画
SP_BY_VIEWS = {
    "weekly": "CAMSBAgDEAE=",   # 今週
    "monthly": "CAMSBAgEEAE=",  # 今月
    "yearly": "CAMSBAgFEAE=",   # 今年
    "alltime": "CAMSAhAB",      # 全期間（期間指定なし・視聴回数順）
}
SP_RELEVANCE = {
    "weekly": "EgQIAxAB",
    "monthly": "EgQIBBAB",
    "yearly": "EgQIBRAB",
    "alltime": "EgIQAQ==",
}
SP_CHANNEL_ONLY = "EgIQAg=="        # チャンネルのみ

# 期間ごとの投稿経過日数の上限（検索フィルタのゆらぎ吸収用、None=無制限）
MAX_DAYS = {"weekly": 7.5, "monthly": 32, "yearly": 370, "alltime": None}

# 動画統計（高評価数等）を取得するランキング上位件数
STATS_TOP_N = 60
# 統計キャッシュの有効日数
STATS_MAX_AGE = {"weekly": 1, "monthly": 3, "yearly": 7, "alltime": 14}

# 1回の実行あたりの取得上限（毎日の更新時間を一定に保つためのローテーション）
SEED_CHECKS_PER_RUN = 25       # シードのチャンネル検索
DISCOVERY_PER_RUN = 5          # チャンネル発見クエリ
FULL_FETCH_PER_RUN = 25        # 全動画リストの取得チャンネル数
FULL_REFRESH_DAYS = 14         # 全動画リストの再取得間隔

# 週間ランキング用の検索クエリ
RANKING_QUERIES = [
    "ボカロ オリジナル曲",
    "VOCALOID オリジナル",
    "初音ミク オリジナル曲",
    "重音テト オリジナル曲",
    "可不 オリジナル曲",
    "ボカロ MV",
    "GUMI オリジナル曲",
    "ボーカロイド 新曲",
]

# 海外ボカロ用の英語検索クエリ（英語UIで検索し、英語圏の曲を取りこぼさない）
RANKING_QUERIES_EN = [
    "vocaloid original song",
    "synthesizer v original song",
    "vocaloid song english",
    "utau original song",
]

# ボカロP発見用シードリスト（有名P・敬称略）
PRODUCER_SEEDS = [
    "DECO*27", "ピノキオピー", "syudou", "Chinozo", "ナユタン星人",
    "ツミキ", "煮ル果実", "いよわ", "柊マグネタイト", "原口沙輔",
    "サツキ MUSIC", "マサラダ", "雄之助", "wotaku", "かいりきベア",
    "てにをは", "じん", "40mP", "キノシタ", "Orangestar",
    "稲葉曇", "ユリイ・カノン", "一二三 ボカロ", "卯花ロク", "Aqu3ra",
    "すりぃ", "蜂屋ななし", "ぬゆり", "balloon 須田景凪", "Eve",
    "ポリスピカデリー", "r-906", "みきとP", "れるりり", "ナナホシ管弦楽団",
    "john TOOBOE", "大漠波新", "Misumi", "鬱P", "cosMo@暴走P",
    "傘村トータ", "はるまきごはん", "ジグ", "シャノン ボカロ", "夏代孝明",
    "TaKU.K", "黒うさP", "doriko", "DIVELA", "ひとしずく",
    # --- 拡充分（登録者5万以上の網羅を目指す） ---
    "ハチ MV", "kemu", "Neru", "MARETU", "sasakure.UK",
    "ねこぼーろ", "ナノウ", "OSTER project", "ジミーサムP", "HoneyWorks",
    "とあ", "ナブナ n-buna", "Ayase", "ツユ ぷす", "guiano",
    "A4。", "Junky ボカロ", "Mitchie M", "梨本うい", "フロクロ",
    "ゆこぴ", "ねじ式 ボカロ", "buzzG", "ぐちり", "Kanaria",
    "きくお", "パトリチェフ", "GYARI", "Omoi", "じーざすP",
    "レフティーモンスターP", "halyosy", "Heavenz", "keeno", "ATOLS",
    "Twinfield", "なきそ", "弌誠", "オワタP", "家の裏でマンボウが死んでるP",
    "やいり", "livetune kz", "八王子P", "Giga ボカロ", "Mwk",
    "EZFG", "蝶々P", "TOKOTOKO 西沢さんP", "メドミア", "ど〜ぱみん",
    "ルワン", "Sohbana", "アメリカ民謡研究会", "椎乃味醂", "缶缶",
    "いるかアイス", "すこっぷ", "大沼パセリ", "香椎モイミ", "南ノ南",
    "ろくろ ボカロ", "月詠み", "カンザキイオリ", "マチゲリータ", "ラマーズP",
    # --- 海外ボカロP ---
    "GHOST and Pals", "Creep-P", "KIRA vocaloid", "Vane vocaloid",
    "Steampianist", "Crusher-P", "Circus-P",
]
# 注意: 短い名前のシードは同名別チャンネルにマッチしやすい（例:「ジグ」→ゲーム実況ch）。
# 誤マッチは NON_PRODUCER_IDS とボカロ要素ゼロ判定で自動排除される。

# チャンネル発見用クエリ（チャンネル検索で一括発見し、ボカロ要素判定で絞る）
# ※データソースはYouTubeのみ（外部DBの利用は禁止）
CHANNEL_DISCOVERY_QUERIES = [
    "ボカロP", "ボカロ オリジナル曲", "VOCALOID producer", "ボーカロイド",
    "初音ミク オリジナル", "重音テト オリジナル", "ボカロ 作曲",
    "vocaloid original", "CeVIO オリジナル", "SynthV オリジナル",
    "初音ミク MV", "重音テト MV", "可不 オリジナル", "GUMI オリジナル",
    "鏡音リン オリジナル", "flower オリジナル", "ミクオリジナル曲",
    "ボカロ MV 公式", "vocaloid mv", "歌愛ユキ オリジナル",
    "vocaloid producer original", "synthesizer v producer",
]

# 海外ボーカル名（英語圏のSynthV/UTAU等。各キーワードリストに合流させる）
OVERSEAS_VOCAL_KEYWORDS = [
    "solaria", "asterian", "eleanor forte", "yi xi", "ninezero", "hayden",
    "saros", "gumi english", "miku english", "adachi rei", "kasane teto sv",
]

# ボカロ判定キーワード（タイトル/チャンネル名向け）
VOCALOID_KEYWORDS = [
    "ボカロ", "ボーカロイド", "vocaloid", "初音ミク", "ミク", "miku",
    "鏡音リン", "鏡音レン", "リン", "レン", "巡音ルカ", "ルカ", "meiko", "kaito",
    "gumi", "グミ", "flower", "フラワ", "可不", "kafu", "星界", "裏命",
    "重音テト", "テト", "teto", "歌愛ユキ", "ゆかり", "結月", "synthesizer v",
    "synthv", "cevio", "セヴィオ", "知声", "ちせ", "夢ノ結唱", "音街ウナ",
    "v flower", "ずんだもん", "羽累", "ポエロイド", "utau", "feat.", "【ia】", " ia ",
] + OVERSEAS_VOCAL_KEYWORDS

MIN_SUBSCRIBERS = 10000
# 登録者数に関わらず名鑑入りするヒット曲の再生数基準
BIG_HIT_VIEWS = 5_000_000

# ボカロP名鑑から除外するチャンネル（公式ゲーム・レーベル等、個人Pでないもの）
NON_PRODUCER_IDS = {
    "UCdMGYXL38w6htx6Yf9YJa-w",  # プロジェクトセカイ公式
    "UCki-diEpX8eLHvSAn9C0Eyg",  # ジグのフォートナイト先輩（同名別人のゲーム実況ch）
    "UCl21Yzb3EPyfsQvimsik5pw",  # イオ（ゆっくり解説ch）
    "UCjeYRfW1hjv9fRZYxFFaqEQ",  # LocalVoid（ランキング動画ch）
    "UClnkaZ4_bW2vCD7wlL-mwqA",  # 挫折させないボカロ講師かがみん（講座ch）
    "UCJwGWV914kBlV4dKRn7AEFA",  # 初音ミク（クリプトン公式ch）
    "UCvpredjG93ifbCP1Y77JyFA",  # YOASOBI（ユニット公式ch・ボカロPはAyase個人）
    "UCln9P4Qm3-EAY4aiEPmRwEA",  # Ado（歌手・ボカロ曲は歌唱参加のみ）
    "UCZ3h7IyAMbrVgvmxTdj-rpA",  # よみぃ（ピアニスト・演奏動画）
    "UCq36dja_0U4SgB3wYVtr_Zw",  # Lizz Robinett（英語カバー歌手）
    "UCa9_8C9ebEphjva-P7OV7bA",  # Lollia（英語カバー歌手）
    "UCOjkVJQcjtWnpf0-1ft4brA",  # ゆっくりむちゃたぬき（解説ch）
    "UCI0-z9tmpOx1bU6Weh6q0AQ",  # reddevils500a（転載ch）
    "UCCFzL2ZhgofuDS70FpG2SlA",  # Teto Kasane-Chan（ファンch）
    "UCsLD_RZwHthlD4XkXDOSPQg",  # HOKEN Mumu（UTAUカバーch）
    "UCpxMn9mgN7kiHfLBcYzSZdw",  # Dreamtonics（SynthV開発会社）
    "UCljykc7QBcVAxsa3J1DyN4w",  # singtur（転載疑い）
    "UCYYMBQzRY6DKBj_3qMfRXdg",  # 鈴華ゆう子（和楽器バンド・歌手）
    "UCU8DLJPzm3m3WkuMzXzJtmA",  # CoffeeCat12（カバー歌手）
    "UCgrYP3m2ygzrlNv0vGtUjqw",  # Samuton9574（カバー歌手）
    "UCshJXP---IW-EMvi8Iy7WIg",  # Lepic（カバー歌手）
    "UCfw1ozW-vUsNsgGuxV0VzYg",  # だんちょうてい（カバー歌手）
    "UCedZ1Nz4ZcBy6fb2YVyB0CQ",  # ke-san β（MMDアニメーター）
    "UCYNk3hp6TYIudnvHn1bI1OQ",  # Mario GaGabriel（アニメーター）
    "UCCFEfpN2ny-_BbAJchzZ7mA",  # Its_Sherboi（アニメーター）
    "UCxPQie_LaDV5hOv6tlr9KOw",  # 夢ノ結唱（公式ボイスバンクch）
    "UCOTR1tcOAhjgi6YukrPpZxg",  # まふまふちゃんねる（歌い手）
    "UCYEt19P3rd3n3MsjyOOna5A",  # Miree（スペイン語カバー歌手）
    "UCB6pJFaFByws3dQj4AdLdyA",  # Reol Official（歌手）
    "UCFQWd5VxJGAOoWH8F9j81hA",  # rev（UTAUカバー職人・オリジナル曲なし）
}

# ボカロ曲タイトル判定用キーワード（チャンネル内の非ボカロ動画の識別用。
# 汎用語の "feat." 等は含めない）
VOCALO_TITLE_KEYWORDS = [
    "初音ミク", "ミク", "miku", "hatsune", "重音テト", "テト", "teto",
    "可不", "kafu", "gumi", "グミ", "鏡音", "リン・レン", "リンレン",
    "巡音", "ルカ", "luka", "flower", "フラワー", "音街ウナ", "歌愛ユキ",
    "結月ゆかり", "星界", "裏命", "知声", "狐子", "羽累", "夢ノ結唱",
    "ボカロ", "ボーカロイド", "vocaloid", "synthesizer v", "synthv",
    "cevio", "utau", "ずんだもん", "ボカコレ", " ia ", "【ia】",
] + OVERSEAS_VOCAL_KEYWORDS


def is_vocalo_title(title):
    t = (title or "").lower()
    return any(k in t for k in VOCALO_TITLE_KEYWORDS)


# カバー（歌ってみた）検出。歌い手の動画がランキング・名鑑に混ざるのを防ぐ
COVER_TITLE_RE = re.compile(r"\bcover(ed)?\b", re.IGNORECASE)
COVER_TITLE_KEYWORDS = ["歌ってみた", "うたってみた", "カバー", "歌わせていただ"]
COVER_DESC_KEYWORDS = ["本家", "原曲", "歌ってみた", "covered by", "vocal cover",
                       "歌わせていただ", "original song by", "original:"]


def is_cover_title(title):
    t = (title or "").lower()
    return bool(COVER_TITLE_RE.search(t)) or any(k in t for k in COVER_TITLE_KEYWORDS)


def is_cover_video(title, desc):
    """タイトルまたは概要欄からカバー動画かを判定。

    タイトルにボーカル名がある動画は本人名義の公式（オリジナル曲）が大半なので、
    概要欄の「原曲」等は理由にしない（例:「テトリス / 重音テトSV」は概要欄に
    原曲コロブチカのクレジットがあるがオリジナル曲）。"""
    if is_cover_title(title):
        return True
    if is_vocal_song_title(title):
        return False
    d = (desc or "").lower()
    return any(k in d for k in COVER_DESC_KEYWORDS)


# ボーカル名そのもの（「ボカロ」等の汎用語を除く）。
# ボカロP検証用: 講座・解説チャンネルは汎用語しか含まないため、これで弾く
VOCAL_NAME_KEYWORDS = [
    "初音ミク", "ミク", "miku", "hatsune", "重音テト", "テト", "teto",
    "可不", "kafu", "gumi", "グミ", "鏡音", "リン・レン", "リンレン",
    "巡音", "ルカ", "luka", "flower", "フラワー", "音街ウナ", "歌愛ユキ",
    "結月ゆかり", "星界", "裏命", "知声", "狐子", "羽累", "夢ノ結唱",
    "ずんだもん", " ia ", "【ia】",
] + OVERSEAS_VOCAL_KEYWORDS


def is_vocal_song_title(title):
    t = (title or "").lower()
    return any(k in t for k in VOCAL_NAME_KEYWORDS)

# 除外キーワード（歌枠・カラオケ配信・メドレー等はオリジナル曲ではない）
EXCLUDE_KEYWORDS = [
    "歌枠", "カラオケ", "karaoke", "歌ってみた", "メドレー", "medley",
    "作業用", "ランキング推移", "再生回数", "比較", "マイクラ", "ゲーム実況",
    "切り抜き", "リアクション", "reaction", "耐久", "まとめ", "総集編",
    "covered by", "cover)", "cover】", "cover /", "english ver", "english cover",
    "russian ver", "spanish ver",
]


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def write_json_atomic(path, obj, indent=1):
    """一時ファイル経由で書き込み、途中クラッシュによるJSON破損を防ぐ"""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                   encoding="utf-8")
    os.replace(tmp, path)


# 実行が最後まで成功したときにだけ書くべき状態ファイル（main末尾で書き込み）
DEFERRED_STATE = {}


def fetch_html(url, params=None, headers=None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers or HEADERS, timeout=20)
            if r.status_code == 200:
                return r.text
            log(f"  HTTP {r.status_code}: {url}")
        except requests.RequestException as e:
            log(f"  リクエスト失敗 ({attempt+1}/3): {e}")
        time.sleep(2 + attempt * 2)
    return None


def extract_yt_initial_data(html):
    """HTMLから ytInitialData の JSON を抽出する"""
    m = re.search(r"var ytInitialData\s*=\s*(\{.+?\});</script>", html, re.DOTALL)
    if not m:
        m = re.search(r'window\["ytInitialData"\]\s*=\s*(\{.+?\});', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk_find(obj, key):
    """ネストされた dict/list から指定キーのオブジェクトを文書順で収集"""
    found = []

    def rec(cur):
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == key:
                    found.append(v)
                if isinstance(v, (dict, list)):
                    rec(v)
        elif isinstance(cur, list):
            for x in cur:
                if isinstance(x, (dict, list)):
                    rec(x)

    rec(obj)
    return found


def parse_jp_number(text):
    """'285万' '1.2万' '3,401' '1.1億' '1.2M' '530K' → int（日英対応）"""
    if not text:
        return None
    text = text.replace(",", "").replace(" ", "").strip()
    m = re.search(r"([\d.]+)(億|万|[KkMmBb])?", text)
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "").upper()
    mult = {"億": 1e8, "万": 1e4, "K": 1e3, "M": 1e6, "B": 1e9}.get(unit, 1)
    return int(num * mult)


def parse_view_count(vr):
    """videoRenderer から視聴回数を取得"""
    vct = vr.get("viewCountText", {})
    text = vct.get("simpleText") or "".join(
        r.get("text", "") for r in vct.get("runs", [])
    )
    if not text:
        svc = vr.get("shortViewCountText", {})
        text = svc.get("simpleText", "")
    return parse_jp_number(text)


def parse_published_days_ago(text):
    """'3 日前' '1 週間前' '10 時間前' '3 days ago' → 経過日数(float)（日英対応）"""
    if not text:
        return None
    text = text.replace(" ", "")
    m = re.search(r"([\d.]+)(秒|分|時間|日|週間|か月|年)前", text)
    if m:
        n = float(m.group(1))
        factor = {"秒": 1 / 86400, "分": 1 / 1440, "時間": 1 / 24,
                  "日": 1, "週間": 7, "か月": 30, "年": 365}[m.group(2)]
        return n * factor
    m = re.search(r"([\d.]+)(second|minute|hour|day|week|month|year)s?ago",
                  text, re.IGNORECASE)
    if m:
        n = float(m.group(1))
        factor = {"second": 1 / 86400, "minute": 1 / 1440, "hour": 1 / 24,
                  "day": 1, "week": 7, "month": 30, "year": 365}[m.group(2).lower()]
        return n * factor
    return None


def is_vocaloid_related(title, channel_name=""):
    t = (title + " " + channel_name).lower()
    return any(kw in t for kw in VOCALOID_KEYWORDS)


def parse_video_renderer(vr):
    try:
        video_id = vr["videoId"]
        title = "".join(r["text"] for r in vr["title"]["runs"])
        owner = vr.get("ownerText", {}).get("runs", [{}])[0]
        channel_name = owner.get("text", "")
        channel_id = (
            owner.get("navigationEndpoint", {})
            .get("browseEndpoint", {})
            .get("browseId", "")
        )
        views = parse_view_count(vr)
        published_text = vr.get("publishedTimeText", {}).get("simpleText", "")
        days_ago = parse_published_days_ago(published_text)
        length = vr.get("lengthText", {}).get("simpleText", "")
        return {
            "videoId": video_id,
            "title": title,
            "channelName": channel_name,
            "channelId": channel_id,
            "views": views,
            "publishedText": published_text,
            "daysAgo": days_ago,
            "length": length,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        }
    except (KeyError, IndexError):
        return None


def search_videos(query, sp, en=False):
    html = fetch_html(
        "https://www.youtube.com/results",
        params={"search_query": query, "sp": sp},
        headers=HEADERS_EN if en else None,
    )
    if not html:
        return []
    data = extract_yt_initial_data(html)
    if not data:
        log(f"  ytInitialData 抽出失敗: {query}")
        return []
    videos = []
    for vr in walk_find(data, "videoRenderer"):
        v = parse_video_renderer(vr)
        if v:
            videos.append(v)
    return videos


def normalize_name(s):
    return re.sub(r"[\s\*＊・/／\-ー@＠]", "", s.lower())


def search_channel(query):
    """チャンネル検索して名前が一致する最上位のチャンネルを返す"""
    html = fetch_html(
        "https://www.youtube.com/results",
        params={"search_query": query, "sp": SP_CHANNEL_ONLY},
    )
    if not html:
        return None
    data = extract_yt_initial_data(html)
    if not data:
        return None
    # クエリの主要部分（最初の語）で名前一致を検証する
    core = normalize_name(query.split()[0])
    candidates = []
    for cr in walk_find(data, "channelRenderer"):
        try:
            channel_id = cr["channelId"]
            name = cr["title"]["simpleText"]
            # subscriberCountText と videoCountText のどちらかに登録者数が入る
            subs = None
            for key in ("videoCountText", "subscriberCountText"):
                t = cr.get(key, {})
                text = t.get("simpleText") or "".join(
                    r.get("text", "") for r in t.get("runs", [])
                )
                if "登録者" in text:
                    subs = parse_jp_number(text.replace("チャンネル登録者数", ""))
                    break
            thumb = ""
            thumbs = cr.get("thumbnail", {}).get("thumbnails", [])
            if thumbs:
                thumb = thumbs[-1].get("url", "")
                if thumb.startswith("//"):
                    thumb = "https:" + thumb
            desc = ""
            snippet = cr.get("descriptionSnippet", {})
            desc = "".join(r.get("text", "") for r in snippet.get("runs", []))
            candidates.append({
                "channelId": channel_id,
                "name": name,
                "subscribers": subs,
                "thumbnail": thumb,
                "description": scrub_pii(desc)[:200],
            })
        except (KeyError, IndexError):
            continue
    # 名前がクエリと一致する候補を優先（上位10件から）
    for c in candidates[:10]:
        n = normalize_name(c["name"])
        if core and (core in n or n in core):
            return c
    return candidates[0] if candidates else None


def fetch_channel_details(channel_id):
    """チャンネルの登録者数等を取得（API優先・スクレイピングフォールバック）"""
    if YT_API_KEY:
        info = api_channels([channel_id])
        if info and channel_id in info:
            return info[channel_id]
    html = fetch_html(f"https://www.youtube.com/channel/{channel_id}")
    if not html:
        return None
    result = {"channelId": channel_id}
    m = re.search(r"チャンネル登録者数\s*([\d.,万億]+)\s*人", html)
    if m:
        result["subscribers"] = parse_jp_number(m.group(1))
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if m:
        result["name"] = m.group(1)
    m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if m:
        result["thumbnail"] = m.group(1)
    m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    if m:
        result["description"] = scrub_pii(m.group(1))[:200]
    m = re.search(r'"canonicalBaseUrl":"/(@[^"]+)"', html)
    if m:
        result["handle"] = m.group(1)
    return result


def parse_lockup(lv):
    """新レイアウトの lockupViewModel から動画情報を抽出"""
    try:
        video_id = lv.get("contentId")
        meta = lv.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = meta.get("title", {}).get("content", "")
        if not video_id or not title:
            return None
        views = days = None
        for row in walk_find(meta, "metadataParts"):
            for part in row:
                text = part.get("text", {}).get("content", "")
                if "回視聴" in text and views is None:
                    views = parse_jp_number(text)
                elif text.endswith("前") and days is None:
                    days = parse_published_days_ago(text)
        secs = None
        img = lv.get("contentImage", {})
        for t in walk_find(img, "text"):
            val = t if isinstance(t, str) else t.get("content", "") if isinstance(t, dict) else ""
            if re.fullmatch(r"\d+:\d{2}(:\d{2})?", val):
                parts = val.split(":")
                secs = sum(int(p) * 60 ** i for i, p in enumerate(reversed(parts)))
                break
        return {"id": video_id, "t": title[:60], "v": views,
                "d": round(days, 2) if days is not None else None, "len": secs}
    except (KeyError, TypeError, AttributeError):
        return None


def search_channels_all(query):
    """チャンネル検索の結果全件を返す（発見用）"""
    html = fetch_html(
        "https://www.youtube.com/results",
        params={"search_query": query, "sp": SP_CHANNEL_ONLY},
    )
    if not html:
        return []
    data = extract_yt_initial_data(html)
    if not data:
        return []
    out = []
    for cr in walk_find(data, "channelRenderer"):
        try:
            subs = None
            for key in ("videoCountText", "subscriberCountText"):
                t = cr.get(key, {})
                text = t.get("simpleText") or "".join(
                    r.get("text", "") for r in t.get("runs", [])
                )
                if "登録者" in text:
                    subs = parse_jp_number(text.replace("チャンネル登録者数", ""))
                    break
            thumb = ""
            thumbs = cr.get("thumbnail", {}).get("thumbnails", [])
            if thumbs:
                thumb = thumbs[-1].get("url", "")
                if thumb.startswith("//"):
                    thumb = "https:" + thumb
            snippet = cr.get("descriptionSnippet", {})
            desc = "".join(r.get("text", "") for r in snippet.get("runs", []))
            out.append({
                "channelId": cr["channelId"],
                "name": cr["title"]["simpleText"],
                "subscribers": subs,
                "thumbnail": thumb,
                "description": scrub_pii(desc)[:200],
            })
        except (KeyError, IndexError):
            continue
    return out


def _innertube_config(html):
    key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    ver = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION":"([^"]+)"', html)
    return (key.group(1) if key else None,
            ver.group(1) if ver else "2.20250101.00.00")


def _continuation_token(obj):
    for c in walk_find(obj, "continuationCommand"):
        if isinstance(c, dict) and c.get("token"):
            return c["token"]
    return None


def fetch_all_channel_videos(channel_id, max_videos=500):
    """チャンネルの全動画を取得（API優先・スクレイピングフォールバック）"""
    if YT_API_KEY:
        ids = api_channel_upload_ids(channel_id, max_videos)
        if ids:
            vids = api_videos(ids)
            if vids:
                return vids
    html = fetch_html(f"https://www.youtube.com/channel/{channel_id}/videos")
    if not html:
        return None
    data = extract_yt_initial_data(html)
    if not data:
        return None
    out, seen = [], set()

    def collect(obj):
        for lv in walk_find(obj, "lockupViewModel"):
            v = parse_lockup(lv)
            if v and v["id"] not in seen:
                seen.add(v["id"])
                out.append(v)
        for vr in walk_find(obj, "videoRenderer"):
            v = parse_video_renderer(vr)
            if v and v["videoId"] not in seen:
                seen.add(v["videoId"])
                out.append({"id": v["videoId"], "t": v["title"][:60], "v": v["views"],
                            "d": round(v["daysAgo"], 2) if v["daysAgo"] is not None else None,
                            "len": None})

    collect(data)
    token = _continuation_token(data)
    api_key, client_ver = _innertube_config(html)
    pages = 0
    while token and api_key and len(out) < max_videos and pages < 20:
        try:
            r = requests.post(
                f"https://www.youtube.com/youtubei/v1/browse?key={api_key}",
                json={
                    "context": {"client": {
                        "clientName": "WEB", "clientVersion": client_ver,
                        "hl": "ja", "gl": "JP",
                    }},
                    "continuation": token,
                },
                headers=HEADERS, timeout=20,
            )
            if r.status_code != 200:
                break
            j = r.json()
        except (requests.RequestException, json.JSONDecodeError):
            break
        before = len(out)
        collect(j)
        token = _continuation_token(j) if len(out) > before else None
        pages += 1
        time.sleep(random.uniform(0.4, 0.8))
    return out or None


def fetch_channel_recent_videos(channel_id, limit=30):
    """チャンネルの直近の投稿一覧を取得（API優先・スクレイピングフォールバック）"""
    if YT_API_KEY:
        ids = api_channel_upload_ids(channel_id, limit)
        if ids:
            vids = api_videos(ids[:limit])
            if vids:
                # 配信データを軽くするため、フロントで使わない項目は落とす
                return [{k: v for k, v in x.items()
                         if k not in ("likes", "publishedAt")} for x in vids]
    html = fetch_html(f"https://www.youtube.com/channel/{channel_id}/videos")
    if not html:
        return None
    data = extract_yt_initial_data(html)
    if not data:
        return None
    out = []
    # 新レイアウト (lockupViewModel)
    for lv in walk_find(data, "lockupViewModel"):
        v = parse_lockup(lv)
        if v:
            out.append(v)
        if len(out) >= limit:
            break
    # 旧レイアウト (videoRenderer) フォールバック
    if not out:
        for vr in walk_find(data, "videoRenderer"):
            v = parse_video_renderer(vr)
            if not v:
                continue
            secs = None
            if v["length"]:
                try:
                    parts = v["length"].split(":")
                    secs = sum(int(p) * 60 ** i for i, p in enumerate(reversed(parts)))
                except ValueError:
                    pass
            out.append({
                "id": v["videoId"],
                "t": v["title"][:60],
                "v": v["views"],
                "d": round(v["daysAgo"], 2) if v["daysAgo"] is not None else None,
                "len": secs,
            })
            if len(out) >= limit:
                break
    return out or None


def fetch_channel_about(channel_id):
    """チャンネル概要ページから開設日・総再生数・動画本数を取得"""
    html = fetch_html(f"https://www.youtube.com/channel/{channel_id}/about")
    if not html:
        return {}
    # aboutChannelViewModel 周辺に限定して誤マッチ（無関係な動画の再生数等）を防ぐ
    regions = [html[i: i + 20000] for i in
               (m.start() for m in re.finditer(r'"aboutChannelViewModel"', html))]
    if not regions:
        regions = [html]
    info = {}
    patterns = {
        "joined": r'"(\d{4}/\d{2}/\d{2})\s*に登録"',
        "totalViews": r'"([\d,]+)\s*回視聴"',
        "totalVideos": r'"([\d,]+)\s*本の動画"',
    }
    for key, pat in patterns.items():
        found = [x for region in regions for x in re.findall(pat, region)]
        if not found:
            continue
        if key == "joined":
            info[key] = found[0].replace("/", "-")
        else:
            # 同領域内に動画単体の再生数が混ざることがあるため最大値を採用
            info[key] = max(int(x.replace(",", "")) for x in found)
    return info


def _date_age(datestr):
    if not datestr:
        return 9999
    try:
        return (datetime.date.fromisoformat(TODAY)
                - datetime.date.fromisoformat(datestr)).days
    except ValueError:
        return 9999


def merge_recent_into_channel_file(p):
    """直近動画(新曲)をチャンネル全曲ファイルへ反映（ネットワーク不要）"""
    f = CHANNELS_DIR / f"{p['channelId']}.json"
    if not f.exists():
        return
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    vids = {v["id"]: v for v in data.get("videos", []) if v.get("id")}
    changed = False
    for r in p.get("recent") or []:
        if not r.get("id"):
            continue
        if not (r.get("voca") or is_vocalo_title(r.get("t"))):
            continue
        cur = vids.get(r["id"])
        if cur is None or (r.get("v") is not None and r.get("v") != cur.get("v")):
            merged = {**(cur or {}), **r}
            merged.pop("publishedAt", None)
            vids[r["id"]] = merged
            changed = True
    if changed:
        data["videos"] = sorted(vids.values(), key=lambda x: x.get("v") or 0, reverse=True)
        data["updated"] = TODAY
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def save_channel_videos(p, videos):
    """チャンネルの楽曲リストを保存。

    掲載ルール: ボカロ曲判定（タイトル+概要欄）でフラグを立て、
      - 3割以上がボカロ曲 → 全アップロードを掲載（タイトルや概要に
        ボーカル名を書かない流儀のP[きくお等]でも全曲が出る）
      - ボカロ曲がごく少数（本人歌唱中心の混在チャンネル[TOOBOE等]）
        → ボカロ曲のみ掲載
      - 判定できる曲が1本もない → 名鑑入り済みのPなので全曲掲載（0曲を防ぐ）
    実測: MARETU 92% / ジグ 78% / きくお 43% / TOOBOE 2%
    """
    flagged = [v for v in videos
               if (v.get("voca") or is_vocalo_title(v.get("t")))
               and not (v.get("cov") or is_cover_title(v.get("t")))]
    ratio = len(flagged) / len(videos) if videos else 0
    keep = videos if (ratio >= 0.3 or not flagged) else flagged
    keep = [{k: v for k, v in vid.items()
             if k not in ("publishedAt", "likes")} for vid in keep]
    f = CHANNELS_DIR / f"{p['channelId']}.json"
    f.write_text(json.dumps({
        "name": p.get("name"),
        "updated": TODAY,
        "fullFetched": TODAY,
        "totalFetched": len(videos),
        "videos": sorted(keep, key=lambda x: x.get("v") or 0, reverse=True),
    }, ensure_ascii=False), encoding="utf-8")
    return len(keep)


def enrich_producers(producers, max_recent=100, max_detail=30, max_full=FULL_FETCH_PER_RUN):
    """各ボカロPのデータをローテーションで更新する。
    ① 基本情報（登録者数等）: 4日ごと、1回 max_detail 件
    ③ 直近動画（新曲検知）: 3日ごと、1回 max_recent 件 → 全曲ファイルにもマージ
       概要情報（開設日・累計再生）: 7日ごと
    全曲リスト: 未取得 or 14日経過のチャンネルを優先して1回 max_full 件
    """
    CHANNELS_DIR.mkdir(exist_ok=True)

    # ① 基本情報リフレッシュ（古い順）
    log("=== ボカロP 基本情報更新 ===")
    budget = max_detail
    for p in sorted(producers, key=lambda x: _date_age(x.get("lastUpdated")), reverse=True):
        if budget <= 0:
            break
        if _date_age(p.get("lastUpdated")) < 4:
            continue
        log(f"基本情報更新: {p['name']}")
        det = fetch_channel_details(p["channelId"])
        budget -= 1
        time.sleep(random.uniform(0.5, 1.0))
        if det and det.get("subscribers"):
            p.update({k: v for k, v in det.items() if v})
            p["lastUpdated"] = TODAY

    # ③ 直近動画 + 概要（未取得Pを最優先）
    log("=== ボカロP 直近動画/概要 収集 ===")
    budget = max_recent
    for p in sorted(producers, key=lambda x: _date_age(x.get("recentFetched")), reverse=True):
        if budget <= 0:
            log("  取得上限に到達（残りは明日以降の更新で取得）")
            break
        if _date_age(p.get("recentFetched")) < 3:
            continue
        log(f"直近動画取得: {p['name']}")
        recent = fetch_channel_recent_videos(p["channelId"])
        budget -= 1
        time.sleep(random.uniform(0.5, 1.0))
        if recent:
            p["recent"] = recent
            p["recentFetched"] = TODAY
            merge_recent_into_channel_file(p)
        # APIがあれば概要情報(開設日・累計再生)は基本情報取得に含まれるため不要
        if not YT_API_KEY and _date_age(p.get("aboutFetched")) >= 7:
            about = fetch_channel_about(p["channelId"])
            budget -= 1
            time.sleep(random.uniform(0.5, 1.0))
            if about:
                p.update(about)
                p["aboutFetched"] = TODAY

    # 全ボカロ楽曲リスト（未取得 → 古い順）
    log("=== チャンネル全曲リスト収集 ===")

    def full_age(p):
        f = CHANNELS_DIR / f"{p['channelId']}.json"
        if not f.exists():
            return 9999
        try:
            return _date_age(json.loads(f.read_text(encoding="utf-8")).get("fullFetched"))
        except json.JSONDecodeError:
            return 9999

    budget = max_full
    for p in sorted(producers, key=full_age, reverse=True):
        if budget <= 0:
            log("  取得上限に到達（残りは明日以降の更新で取得）")
            break
        if p.get("pending"):  # ボカロ要素未検証のチャンネルは全曲取得しない
            continue
        if full_age(p) < FULL_REFRESH_DAYS:
            continue
        log(f"全曲リスト取得: {p['name']}")
        videos = fetch_all_channel_videos(p["channelId"])
        budget -= 1
        time.sleep(random.uniform(0.5, 1.0))
        if videos:
            n = save_channel_videos(p, videos)
            log(f"  {len(videos)}本中ボカロ曲{n}本を保存")


def collect_ranking(period):
    log(f"=== {period} ランキング収集 ===")
    max_days = MAX_DAYS[period]
    seen = {}
    maybe = {}  # タイトルにボカロ語がない曲（概要欄をAPIで後追い判定する）
    queries = ([(q, False) for q in RANKING_QUERIES]
               + [(q, True) for q in RANKING_QUERIES_EN])
    for q, en in queries:
        log(f"検索: {q} ({period}{'/en' if en else ''})")
        for sp in (SP_BY_VIEWS[period], SP_RELEVANCE[period]):
            for v in search_videos(q, sp, en=en):
                if v["videoId"] in seen or v["videoId"] in maybe:
                    continue
                if v["views"] is None:
                    continue
                # 期間内のみ（全期間は日数制限なし）
                if (max_days is not None and v["daysAgo"] is not None
                        and v["daysAgo"] > max_days):
                    continue
                # ライブ配信アーカイブ（歌枠等）を除外
                if "配信" in v["publishedText"] or "Streamed" in v["publishedText"]:
                    continue
                title_lower = v["title"].lower()
                if any(kw in title_lower for kw in EXCLUDE_KEYWORDS):
                    continue
                if is_cover_title(v["title"]):  # 歌ってみた・カバー全般
                    continue
                # ライブ配信・超長尺(メドレー等)を除外: 12分超は除外
                if v["length"]:
                    parts = v["length"].split(":")
                    try:
                        secs = sum(int(p) * 60 ** i for i, p in enumerate(reversed(parts)))
                        if secs > 720 or secs < 30:
                            continue
                    except ValueError:
                        pass
                if is_vocaloid_related(v["title"], v["channelName"]):
                    seen[v["videoId"]] = v
                else:
                    maybe[v["videoId"]] = v
            time.sleep(random.uniform(0.8, 1.5))

    # タイトルだけでは判定できない曲を概要欄で救済
    # （「Kikuo - 愛して愛して愛して」のようにボーカル名をタイトルに
    #   書かない曲もランキングに入るようにする）
    if YT_API_KEY and maybe:
        info = api_videos(list(maybe.keys())) or []
        rescued = 0
        for x in info:
            # カバーは概要欄に「本家」等としてボカロ語が書かれるため必ず除外する
            if x.get("voca") and not x.get("cov") and x["id"] in maybe:
                v = maybe[x["id"]]
                if x.get("v"):
                    v["views"] = x["v"]
                seen[v["videoId"]] = v
                rescued += 1
        log(f"概要欄判定で追加: {rescued}件 (候補{len(maybe)}件)")

    videos = sorted(seen.values(), key=lambda x: x["views"] or 0, reverse=True)
    log(f"収集動画数: {len(videos)}")
    return videos[:100]


def collect_producers(ranking_videos, extra_videos=(), big_hit_channels=frozenset()):
    log("=== ボカロPデータ収集 ===")
    producers = {}

    # 既存データを引き継ぐ（再実行で蓄積される）
    prod_file = DATA_DIR / "producers.json"
    if prod_file.exists():
        try:
            old = json.loads(prod_file.read_text(encoding="utf-8"))
            for p in old.get("producers", []):
                if p["channelId"] not in NON_PRODUCER_IDS:
                    producers[p["channelId"]] = p
            log(f"既存データ引き継ぎ: {len(producers)}件")
        except (json.JSONDecodeError, KeyError):
            pass

    # 1) シードリストから検索（7日ローテーションで1回あたりの負荷を一定に保つ）
    seed_file = DATA_DIR / "seed_state.json"
    seed_state = {}
    if seed_file.exists():
        try:
            seed_state = json.loads(seed_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    def seed_age(s):
        try:
            return (datetime.date.fromisoformat(TODAY)
                    - datetime.date.fromisoformat(seed_state[s])).days
        except (KeyError, ValueError, TypeError):
            return 9999

    seed_targets = [s for s in sorted(PRODUCER_SEEDS, key=seed_age, reverse=True)
                    if seed_age(s) >= 7][:SEED_CHECKS_PER_RUN]
    for seed in seed_targets:
        log(f"チャンネル検索: {seed}")
        ch = search_channel(seed)
        time.sleep(random.uniform(0.8, 1.5))
        seed_state[seed] = TODAY
        if not ch or not ch.get("subscribers"):
            continue
        if ch["subscribers"] < MIN_SUBSCRIBERS:
            continue
        if ch["channelId"] in NON_PRODUCER_IDS:
            continue
        cid = ch["channelId"]
        prev = producers.get(cid, {})
        producers[cid] = {**prev, **ch, "lastUpdated": TODAY}

    # 1.5) チャンネル発見クエリ（ローテーション）: 検索結果の全チャンネルから
    #      登録者1万以上を候補登録。ボカロ要素は直近動画の取得後に検証される
    disc_idx = int(seed_state.get("__disc_idx", 0))
    for i in range(DISCOVERY_PER_RUN):
        q = CHANNEL_DISCOVERY_QUERIES[(disc_idx + i) % len(CHANNEL_DISCOVERY_QUERIES)]
        log(f"チャンネル発見検索: {q}")
        for ch in search_channels_all(q):
            if not ch.get("subscribers") or ch["subscribers"] < MIN_SUBSCRIBERS:
                continue
            if ch["channelId"] in NON_PRODUCER_IDS or ch["channelId"] in producers:
                continue
            # ボカロ要素の検証が済むまで pending 扱い（検証失敗なら保存されない）
            producers[ch["channelId"]] = {**ch, "lastUpdated": TODAY, "pending": True}
        time.sleep(random.uniform(0.8, 1.5))
    seed_state["__disc_idx"] = (disc_idx + DISCOVERY_PER_RUN) % len(CHANNEL_DISCOVERY_QUERIES)
    # ここでは書かない: 後段でクラッシュすると「チェック済みなのに結果未保存」になるため
    # main() が producers.json の保存に成功した後に書き込む
    DEFERRED_STATE[str(seed_file)] = seed_state


    # 2) ランキングに登場したチャンネルを追加（週間優先、月間/年間は上限付き）
    ranked_channels = {}
    for v in list(ranking_videos) + list(extra_videos):
        cid = v.get("channelId")
        if cid and cid not in ranked_channels:
            ranked_channels[cid] = v["channelName"]

    fetched = 0
    # 500万再生チャンネル（登録者数不問で名鑑入り対象）を優先的に処理する
    ordered = sorted(ranked_channels.items(),
                     key=lambda kv: kv[0] not in big_hit_channels)
    for cid, cname in ordered:
        if cid in NON_PRODUCER_IDS:
            continue
        if cid in producers and producers[cid].get("lastUpdated") == TODAY:
            continue
        if fetched >= 80:  # 1回の実行での新規取得上限（日々の更新で蓄積される）
            break
        log(f"チャンネル詳細取得: {cname}")
        det = fetch_channel_details(cid)
        fetched += 1
        time.sleep(random.uniform(0.8, 1.5))
        if not det or not det.get("subscribers"):
            continue
        # 500万再生超のヒット曲を持つPは登録者数に関わらず名鑑入り
        if det["subscribers"] < MIN_SUBSCRIBERS and cid not in big_hit_channels:
            continue
        if (det.get("name") or "").endswith("- Topic"):
            continue  # 自動生成のトピックチャンネルは除外
        prev = producers.get(cid, {})
        producers[cid] = {**prev, **det, "lastUpdated": TODAY, "trending": True}
        if cid in big_hit_channels:
            producers[cid]["bigHit"] = True

    # 週間ランキング動画数をカウント
    for p in producers.values():
        p["weeklyVideos"] = sum(
            1 for v in ranking_videos if v.get("channelId") == p["channelId"]
        )
        p["weeklyViews"] = sum(
            v["views"] or 0
            for v in ranking_videos
            if v.get("channelId") == p["channelId"]
        )

    result = sorted(
        producers.values(), key=lambda x: x.get("subscribers") or 0, reverse=True
    )
    log(f"ボカロP登録数: {len(result)}")
    return result


def fetch_video_stats(video_id):
    """動画ページから高評価数・正確な再生数・投稿日時を取得"""
    html = fetch_html(f"https://www.youtube.com/watch?v={video_id}")
    if not html:
        return None
    stats = {}
    m = re.search(r'"likeCount":\s*"?([\d,]+)"?', html)
    if m:
        stats["likes"] = int(m.group(1).replace(",", ""))
    m = re.search(r'"viewCount":"(\d+)"', html)
    if m:
        stats["exactViews"] = int(m.group(1))
    m = re.search(r'"publishDate":"([^"]+)"', html)
    if m:
        stats["publishDate"] = m.group(1)
    return stats or None


def load_stats_cache():
    f = DATA_DIR / "stats_cache.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def enrich_with_stats(videos, period, cache):
    """ランキング上位の動画に高評価数等の詳細統計を付与する"""
    max_age = STATS_MAX_AGE[period]
    today = datetime.date.fromisoformat(TODAY)
    targets = sorted(videos, key=lambda v: v["views"] or 0, reverse=True)[:STATS_TOP_N]
    for v in targets:
        vid = v["videoId"]
        c = cache.get(vid)
        if c and (today - datetime.date.fromisoformat(c["fetched"])).days < max_age:
            stats = c
        else:
            stats = fetch_video_stats(vid)
            time.sleep(random.uniform(0.5, 1.0))
            if not stats:
                continue
            stats["fetched"] = TODAY
            cache[vid] = stats
        if stats.get("likes") is not None:
            v["likes"] = stats["likes"]
        if stats.get("exactViews"):
            v["views"] = stats["exactViews"]
        if stats.get("publishDate"):
            v["publishDate"] = stats["publishDate"]
            try:
                pub = datetime.datetime.fromisoformat(stats["publishDate"])
                delta = datetime.datetime.now(pub.tzinfo) - pub
                v["daysAgo"] = max(delta.total_seconds() / 86400, 0.05)
            except ValueError:
                pass


def clamp01(x):
    return max(0.0, min(1.0, x))


def _fit_line(xs, ys):
    """最小二乗の直線フィット → (傾き, 切片)"""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


def _percentile(sorted_vals, x):
    """昇順リスト内での x のパーセンタイル (0..1)"""
    if not sorted_vals:
        return None
    return bisect.bisect_right(sorted_vals, x) / len(sorted_vals)


def build_score_models(all_videos, subs_map):
    """VocaScore の採点基準を全ランクイン曲から学習する。

    固定のしきい値ではなく「同条件の曲の期待値との差(残差)」で採点するための
    傾向線と残差分布を作る。
      好感度: 高評価率は再生数が多いほど自然に下がる(ライト層に届くため)
              → log(高評価率) ~ log(再生数) の傾向線を引き、その上下で評価
      拡散力: 再生数は登録者が多いほど大きくて当たり前
              → log(再生数) ~ log(登録者数) の傾向線との差で評価
              (大手も小規模も「自分の規模の期待値」と比べるので公平)
      勢い:   投稿経過時間でならした再生数 log(views / days^0.65) の分布
    """
    uniq = {v["videoId"]: v for v in all_videos}.values()
    models = {}

    # --- 好感度: log10(likeRatio) ~ log10(views) ---
    pts = [(math.log10(v["views"]), math.log10(v["likes"] / v["views"]))
           for v in uniq
           if v.get("likes") and (v.get("views") or 0) > 100]
    if len(pts) >= 20:
        slope, icpt = _fit_line([p[0] for p in pts], [p[1] for p in pts])
        slope = max(-0.6, min(0.0, slope))  # 「再生数増→高評価率は下がる」方向のみ
        res = sorted(y - (icpt + slope * x) for x, y in pts)
        models["like"] = {"slope": slope, "icpt": icpt, "res": res}

    # --- 拡散力: log10(views) ~ log10(subs) ---
    pts2 = [(math.log10(max(subs_map[v["channelId"]], 500)), math.log10(v["views"]))
            for v in uniq
            if subs_map.get(v.get("channelId")) and (v.get("views") or 0) > 100]
    if len(pts2) >= 20:
        slope2, icpt2 = _fit_line([p[0] for p in pts2], [p[1] for p in pts2])
        # ランクイン曲コーパス内の実際の傾きをそのまま使うことで
        # 「同規模のランクイン曲の期待値」との比較になり、規模間で公平になる
        slope2 = max(0.1, min(2.0, slope2))
        res2 = sorted(y - (icpt2 + slope2 * x) for x, y in pts2)
        models["reach"] = {"slope": slope2, "icpt": icpt2, "res": res2}

    # --- 勢い: log10(views / days^0.65) の分布 ---
    ms = sorted(
        math.log10((v["views"] or 1) / (max(v["daysAgo"] or 30, 0.5) ** 0.65))
        for v in uniq if (v.get("views") or 0) > 100
    )
    if len(ms) >= 20:
        models["momentum"] = {"vals": ms}
    return models


def compute_score(v, subs_map, models):
    """VocaScore: チャンネル規模・投稿日時の影響を補正した曲単体の評価 (0-100)

    各要素は全ランクイン曲内のパーセンタイル(相対評価)で点数化する。
      好感度 (40): 同じ再生数帯の期待値と比べた高評価率の高さ
      拡散力 (30): 同じ登録者規模の期待値と比べた再生数の高さ
      勢い   (30): 経過時間でならした再生数の高さ
    取得できなかった要素は除外し、残りを100点満点に換算する。
    """
    earned, weight = 0.0, 0.0
    parts = {}

    views = v.get("views") or 0
    likes = v.get("likes")
    m = models.get("like")
    if m and likes and views > 100:
        ratio = likes / views
        resid = math.log10(ratio) - (m["icpt"] + m["slope"] * math.log10(views))
        s = _percentile(m["res"], resid)
        parts["like"] = round(s * 40, 1)
        parts["likeRatio"] = round(ratio * 100, 2)
        earned += s * 40
        weight += 40

    subs = subs_map.get(v.get("channelId"))
    m = models.get("reach")
    if m and subs and views > 100:
        resid = math.log10(views) - (m["icpt"] + m["slope"] * math.log10(max(subs, 500)))
        s = _percentile(m["res"], resid)
        parts["reach"] = round(s * 30, 1)
        earned += s * 30
        weight += 30

    m = models.get("momentum")
    if m and views > 100:
        mv = math.log10(views / (max(v.get("daysAgo") or 30, 0.5) ** 0.65))
        s = _percentile(m["vals"], mv)
        parts["momentum"] = round(s * 30, 1)
        earned += s * 30
        weight += 30

    if weight == 0:
        return None
    score = round(earned / weight * 100)
    grade = "S" if score >= 80 else "A" if score >= 65 else \
            "B" if score >= 50 else "C" if score >= 35 else "D"
    v["score"] = score
    v["scoreGrade"] = grade
    v["scoreParts"] = parts
    return score


def detect_vocal(title):
    """タイトルから使用ボーカルを推定"""
    t = title.lower()
    checks = [
        ("初音ミク", ["初音ミク", "miku", "ミク"]),
        ("重音テト", ["重音テト", "teto", "テト"]),
        ("可不", ["可不", "kafu"]),
        ("鏡音リン・レン", ["鏡音", "リン", "レン", "rin", "len"]),
        ("GUMI", ["gumi", "グミ"]),
        ("flower", ["flower", "フラワ"]),
        ("巡音ルカ", ["巡音", "ルカ", "luka"]),
        ("歌愛ユキ", ["歌愛ユキ"]),
        ("IA", [" ia ", "【ia】"]),
        ("星界", ["星界"]),
        ("裏命", ["裏命"]),
        ("知声", ["知声"]),
        ("音街ウナ", ["音街ウナ", "una"]),
        ("SOLARIA", ["solaria"]),
        ("ASTERIAN", ["asterian"]),
        ("Eleanor Forte", ["eleanor forte"]),
        ("Yi Xi", ["yi xi"]),
    ]
    for name, kws in checks:
        if any(k in t for k in kws):
            return name
    return "その他"


def main():
    """多重起動ガード付きの入口（実体は _main）"""
    DATA_DIR.mkdir(exist_ok=True)
    lock = DATA_DIR / ".update_lock"
    if lock.exists():
        try:
            age_h = (time.time() - lock.stat().st_mtime) / 3600
        except OSError:
            age_h = 99
        if age_h < 2:
            log("別の更新が実行中のため終了します（多重起動ガード）")
            return
        log("古いロックファイルを無視して続行します")
    lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        _main()
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def _main():
    global TODAY
    TODAY = datetime.date.today().isoformat()
    DATA_DIR.mkdir(exist_ok=True)
    HISTORY_DIR.mkdir(exist_ok=True)

    rankings = {}
    for period in ("weekly", "monthly", "yearly", "alltime"):
        rankings[period] = collect_ranking(period)

    if not rankings["weekly"] and not rankings["monthly"]:
        log("!! 動画が1件も取得できませんでした。サイトデータは更新しません。")
        sys.exit(1)

    # 動画詳細統計（高評価数・正確な再生数/投稿日時）を付与
    if YT_API_KEY:
        # API: 全ランクイン曲の正確な統計を一括取得（50件=1リクエスト）
        log("=== 動画統計取得 (YouTube Data API) ===")
        all_ids = {v["videoId"] for vs in rankings.values() for v in vs}
        info = {x["id"]: x for x in (api_videos(all_ids) or [])}
        for vs in rankings.values():
            for v in vs:
                x = info.get(v["videoId"])
                if not x:
                    continue
                if x.get("v"):
                    v["views"] = x["v"]
                if x.get("likes") is not None:
                    v["likes"] = x["likes"]
                if x.get("publishedAt"):
                    v["publishDate"] = x["publishedAt"]
                    v["daysAgo"] = x["d"]
                if x.get("len"):
                    v["length"] = f"{x['len'] // 60}:{x['len'] % 60:02d}"
        # 概要欄ベースのカバー判定でランキングから歌ってみたを一掃
        for k in rankings:
            before = len(rankings[k])
            rankings[k] = [v for v in rankings[k]
                           if not (info.get(v["videoId"]) or {}).get("cov")]
            if before != len(rankings[k]):
                log(f"  {k}: カバー動画を{before - len(rankings[k])}件除外")
    else:
        cache = load_stats_cache()
        for period, videos in rankings.items():
            log(f"=== {period} 動画統計取得 ===")
            enrich_with_stats(videos, period, cache)
        (DATA_DIR / "stats_cache.json").write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8"
        )

    for videos in rankings.values():
        for v in videos:
            v["vocal"] = detect_vocal(v["title"])
            if v["daysAgo"] and v["daysAgo"] > 0:
                v["viewsPerDay"] = int((v["views"] or 0) / max(v["daysAgo"], 0.5))
            else:
                v["viewsPerDay"] = v["views"] or 0
        videos.sort(key=lambda x: x["views"] or 0, reverse=True)

    # 500万再生超の曲を持つチャンネルは登録者数不問で名鑑入りの対象
    big_hits = {v["channelId"] for vs in rankings.values() for v in vs
                if (v.get("views") or 0) >= BIG_HIT_VIEWS and v.get("channelId")}
    extra = (rankings["monthly"][:30] + rankings["yearly"][:30]
             + rankings["alltime"][:30]
             + [v for vs in rankings.values() for v in vs
                if (v.get("views") or 0) >= BIG_HIT_VIEWS])
    producers = collect_producers(rankings["weekly"], extra, big_hits)
    enrich_producers(producers)

    # ボカロPの検証（同名別人・歌い手・ゲームch等の誤混入対策）
    # 直近動画のボカロ曲が2本未満 or 歌ってみたが主体のチャンネルは、
    # ランキング登場・概要文のボカロ語がない限り名鑑から外す
    ranked_ch = {v.get("channelId") for vs in rankings.values() for v in vs}

    def channel_file_stats(cid):
        """全曲ファイルから (ボカロ曲数, 最大再生数)。全投稿履歴ベースの検証材料。
        直近30本だけだと、過去にボカロ曲を上げて現在は別活動のP
        （wowaka/ヒトリエ等）を誤排除するため、履歴全体で判定する"""
        f = CHANNELS_DIR / f"{cid}.json"
        if not f.exists():
            return 0, 0
        try:
            vids = json.loads(f.read_text(encoding="utf-8")).get("videos", [])
            voca = [v for v in vids
                    if (v.get("voca") or is_vocalo_title(v.get("t")))
                    and not (v.get("cov") or is_cover_title(v.get("t")))]
            mx = max(((v.get("v") or 0) for v in voca), default=0)
            return len(voca), mx
        except json.JSONDecodeError:
            return 0, 0

    kept = []
    for p in producers:
        cid = p["channelId"]
        rec = p.get("recent") or []
        file_voca, file_max = channel_file_stats(cid)

        # --- ① ボカロ要素の検証 ---
        if not rec and not file_voca:
            # データ未取得: 発見クエリ由来(pending)は検証完了まで保存しない
            if p.get("pending"):
                log(f"検証待ちのため保留: {p['name']}")
                continue
            kept.append(p)
            continue
        # カバーはボカロ曲としてカウントしない（歌い手の誤認防止）
        voca_n = sum(
            1 for r in rec
            if (r.get("voca") or is_vocal_song_title(r.get("t")))
            and not (r.get("cov") or is_cover_title(r.get("t")))
        )
        utaite_n = sum(1 for r in rec
                       if r.get("cov") or is_cover_title(r.get("t")))
        ok = (
            (voca_n >= 2 and voca_n > utaite_n)
            or (voca_n >= 1 and len(rec) <= 5)
            # ランクイン中でも、直近が歌ってみた主体なら歌い手とみなして通さない
            or (cid in ranked_ch and voca_n >= 1 and voca_n >= utaite_n)
            or is_vocalo_title(p.get("description", ""))
            or file_voca >= 3  # 全履歴にボカロ曲が3本以上あれば歴史的Pとして維持
        )
        if not ok:
            log(f"ボカロ要素なしのため除外: {p['name']}")
            continue

        # --- ② 規模基準: 登録者1万以上 or ボカロ曲500万再生以上 ---
        subs = p.get("subscribers") or 0
        if subs < MIN_SUBSCRIBERS:
            if cid in big_hits or file_max >= BIG_HIT_VIEWS:
                p["bigHit"] = True
            else:
                log(f"規模基準未満のため除外: {p['name']} (登録者{subs})")
                continue

        p.pop("pending", None)  # 検証済み
        kept.append(p)
    producers = kept

    # VocaScore 算出（全ランクイン曲から採点基準を学習 → 相対評価）
    subs_map = {p["channelId"]: p.get("subscribers") for p in producers}
    all_videos = [v for vs in rankings.values() for v in vs]
    models = build_score_models(all_videos, subs_map)
    for videos in rankings.values():
        for v in videos:
            compute_score(v, subs_map, models)

    now = datetime.datetime.now()
    # 公開データはインデントなしで保存（配信サイズ削減・スマホの初回ロード対策）
    write_json_atomic(DATA_DIR / "videos.json", {
        "updated": now.isoformat(),
        "weekly": rankings["weekly"],
        "monthly": rankings["monthly"],
        "yearly": rankings["yearly"],
        "alltime": rankings["alltime"],
    }, indent=None)
    write_json_atomic(DATA_DIR / "producers.json",
                      {"updated": now.isoformat(), "producers": producers},
                      indent=None)
    total_videos = sum(len(v) for v in rankings.values())
    write_json_atomic(DATA_DIR / "meta.json", {
        "updated": now.isoformat(),
        "videoCount": total_videos,
        "producerCount": len(producers),
    })
    # 出力の保存に成功してから状態ファイルを確定する
    for path, state in DEFERRED_STATE.items():
        write_json_atomic(Path(path), state, indent=None)
    # 日次スナップショット（伸び率比較用・週間のみ）
    snap = {
        "date": TODAY,
        "videos": [
            {"videoId": v["videoId"], "views": v["views"], "score": v.get("score")}
            for v in rankings["weekly"]
        ],
        "producers": [
            {"channelId": p["channelId"], "subscribers": p.get("subscribers")}
            for p in producers
        ],
    }
    (HISTORY_DIR / f"{TODAY}.json").write_text(
        json.dumps(snap, ensure_ascii=False), encoding="utf-8"
    )
    log(f"完了: 週間{len(rankings['weekly'])} / 月間{len(rankings['monthly'])} / "
        f"年間{len(rankings['yearly'])} / 全期間{len(rankings['alltime'])} / "
        f"ボカロP {len(producers)}件")
    if YT_API_KEY:
        log(f"APIクォータ使用量: {API_UNITS}ユニット / 無料枠10,000（{API_UNITS / 100:.1f}%）")


if __name__ == "__main__":
    main()
