# -*- coding: utf-8 -*-
"""
X(Twitter) 自動投稿bot
毎日の更新後に「今週のボカロランキングTOP3」を @vocaloid_film に投稿する。
OAuth 1.0a User Context で POST /2/tweets を叩く。

使い方:
  python x_post.py          実際に投稿
  python x_post.py --dry    投稿せず本文だけ表示
  python x_post.py --whoami 認証確認のみ（投稿しない）
"""
import json
import sys
import datetime
from pathlib import Path

from requests_oauthlib import OAuth1Session

BASE_DIR = Path(__file__).resolve().parent
SITE_URL = "https://eurekastudio5.github.io/vocalo-trend-db/"


def load_keys():
    keys = {}
    f = BASE_DIR / "x_keys.txt"
    if not f.exists():
        return None
    for line in f.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            keys[k.strip()] = v.strip()
    need = ("API_KEY", "API_KEY_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET")
    if not all(keys.get(k) for k in need):
        return None
    return keys


def session():
    k = load_keys()
    if not k:
        return None
    return OAuth1Session(
        k["API_KEY"], k["API_KEY_SECRET"],
        k["ACCESS_TOKEN"], k["ACCESS_TOKEN_SECRET"],
    )


def trim(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def compose():
    """週間TOP3の投稿文を組み立てる"""
    data = json.loads((BASE_DIR / "data" / "videos.json").read_text(encoding="utf-8"))
    weekly = data.get("weekly", [])[:3]
    if len(weekly) < 3:
        return None
    medals = ["🥇", "🥈", "🥉"]
    lines = ["📈今週のボカロ急上昇ランキング"]
    for i, v in enumerate(weekly):
        title = trim(v.get("title", ""), 38)
        lines.append(f"{medals[i]} {title}")
    lines.append("")
    lines.append("週間/月間/年間/全期間を毎日更新🎤")
    lines.append(SITE_URL)
    lines.append("#ボカロ #VOCALOID #初音ミク")
    text = "\n".join(lines)
    # 280字超なら曲名をさらに詰める
    while len(text) > 270 and any(len(l) > 20 for l in lines[1:4]):
        for i in range(1, 4):
            lines[i] = lines[i][:-2] + "…"
        text = "\n".join(lines)
    return text


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    s = session()
    if not s:
        print("x_keys.txt が無い/不完全のためスキップ")
        return

    if arg == "--whoami":
        r = s.get("https://api.twitter.com/2/users/me")
        print(r.status_code, r.text)
        return

    text = compose()
    if not text:
        print("ランキングデータ不足のため投稿しません")
        return
    print("=== 投稿本文 ===")
    print(text)
    print(f"=== {len(text)}文字 ===")
    if arg == "--dry":
        return

    r = s.post("https://api.twitter.com/2/tweets", json={"text": text})
    if r.status_code in (200, 201):
        tid = r.json().get("data", {}).get("id")
        print(f"投稿成功: https://twitter.com/vocaloid_film/status/{tid}")
    else:
        print(f"投稿失敗 {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    main()
