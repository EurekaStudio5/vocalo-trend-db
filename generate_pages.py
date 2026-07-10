# -*- coding: utf-8 -*-
"""Generate static SEO landing pages for Vocalo Trend DB.

Outputs:
  p/{channelId}.html  -- one page per producer in data/producers.json
  p/index.html        -- producer directory
  s/{videoId}.html    -- one page per ranked song in data/videos.json
  s/index.html        -- ranked songs directory
  sitemap.xml         -- root + all generated pages

Run daily from update_task.bat AFTER update_data.py.
Stale pages (producers/songs dropped from data) are removed automatically.
"""
import json
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://eurekastudio5.github.io/vocalo-trend-db"
GA_ID = "G-LD83R6HN2W"
AMAZON_TAG = "vocaloidtrend-22"
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
URL_RE = re.compile(r"https?://\S+")

LIST_LABELS = [("weekly", "週間"), ("monthly", "月間"), ("yearly", "年間"), ("alltime", "全期間")]


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def fmt_num(n):
    """12345 -> 1.2万 / 123456789 -> 1.2億"""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    if n >= 1e8:
        v = n / 1e8
        return (f"{v:.1f}" if v < 10 else f"{v:.0f}") + "億"
    if n >= 1e4:
        v = n / 1e4
        return (f"{v:.1f}" if v < 10 else f"{v:.0f}") + "万"
    return f"{int(n):,}"


def truncate(s, limit):
    s = s or ""
    return s if len(s) <= limit else s[: limit - 1] + "…"


def clean_desc(s, limit=140):
    """Strip URLs/newlines from channel description for meta/body use."""
    s = URL_RE.sub("", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return truncate(s, limit)


STYLE = """
:root{--paper:#fff8ef;--card:#fff;--ink:#2b2440;--ink-soft:#6f6885;--teal:#00b8a9;--teal-soft:#d6f4f0;--pink:#ff6fa5;--yellow:#ffd93d;--shadow:4px 4px 0 var(--ink);--shadow-sm:3px 3px 0 var(--ink)}
*{margin:0;padding:0;box-sizing:border-box}
body{background-color:var(--paper);background-image:radial-gradient(rgba(43,36,64,.08) 1px,transparent 1px);background-size:22px 22px;color:var(--ink);font-family:"Zen Maru Gothic","Hiragino Maru Gothic ProN","Yu Gothic UI",sans-serif;line-height:1.7}
a{color:var(--ink)}
.hdr{position:sticky;top:0;background:var(--paper);border-bottom:3px solid var(--ink);padding:10px 16px;z-index:10}
.hdr a{font-weight:900;text-decoration:none;font-size:1.05rem}
.hdr .mk{color:var(--teal)}
main{max-width:820px;margin:0 auto;padding:20px 16px 48px}
.bc{font-size:.8rem;color:var(--ink-soft);margin-bottom:14px}
.bc a{color:var(--ink-soft)}
.card{background:var(--card);border:3px solid var(--ink);border-radius:16px;box-shadow:var(--shadow);padding:18px 20px;margin-bottom:20px}
h1{font-size:1.35rem;font-weight:900;line-height:1.4;margin-bottom:8px}
h2{font-size:1.05rem;font-weight:900;margin:22px 0 10px;border-left:6px solid var(--teal);padding-left:10px}
.meta-row{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.chip{display:inline-block;border:2px solid var(--ink);border-radius:999px;background:var(--teal-soft);padding:2px 12px;font-size:.82rem;font-weight:700;box-shadow:var(--shadow-sm)}
.chip.pk{background:#ffe3ef}
.chip.yl{background:#fff3c4}
.pf{display:flex;gap:16px;align-items:flex-start}
.pf img{width:88px;height:88px;border-radius:50%;border:3px solid var(--ink);box-shadow:var(--shadow-sm);flex:none}
.thumb{width:100%;max-width:480px;border:3px solid var(--ink);border-radius:12px;box-shadow:var(--shadow);display:block;margin:10px 0}
table{width:100%;border-collapse:collapse;font-size:.88rem}
th,td{border-bottom:2px solid #eee7da;padding:7px 6px;text-align:left;vertical-align:top}
th{border-bottom:3px solid var(--ink);font-size:.8rem}
td.num,th.num{text-align:right;white-space:nowrap}
.rank{font-weight:900;color:var(--teal)}
.btn{display:inline-block;border:3px solid var(--ink);border-radius:12px;background:var(--yellow);box-shadow:var(--shadow-sm);padding:6px 14px;font-weight:900;text-decoration:none;font-size:.9rem;margin:4px 8px 4px 0}
.btn.tl{background:var(--teal-soft)}
.note{font-size:.78rem;color:var(--ink-soft);margin-top:14px}
footer{border-top:3px solid var(--ink);padding:16px;text-align:center;font-size:.8rem;color:var(--ink-soft)}
@media(max-width:560px){.pf{flex-direction:column}.pf img{width:72px;height:72px}}
""".strip()


def page(title, desc, canonical, body, og_image=None, jsonld=None, og_type="article"):
    og_img_tag = f'<meta property="og:image" content="{esc(og_image)}">\n' if og_image else ""
    tw_card = "summary_large_image" if og_image and "ytimg" in (og_image or "") else "summary"
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>\n' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA_ID}');</script>
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{esc(canonical)}">
{og_img_tag}<meta name="twitter:card" content="{tw_card}">
{ld}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;700;900&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<div class="hdr"><a href="../index.html"><span class="mk">▶</span> ボカロトレンドDB</a></div>
<main>
{body}
</main>
<footer>▶ ボカロトレンドDB — データ出典: YouTube（公開情報） / 非公式ファンサイト / 毎日自動更新</footer>
</body>
</html>"""


def breadcrumb_ld(items):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(items)
        ],
    }


def load_channel_songs(cid):
    """Return producer's vocaloid original songs sorted by views desc."""
    f = ROOT / "data" / "channels" / f"{cid}.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []
    vids = data.get("videos") or []
    songs = [v for v in vids if v.get("voca") and not v.get("cov")]
    songs.sort(key=lambda v: v.get("v") or 0, reverse=True)
    return songs


def main():
    producers = json.loads((ROOT / "data" / "producers.json").read_text(encoding="utf-8"))["producers"]
    videos = json.loads((ROOT / "data" / "videos.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
    lastmod = (meta.get("updated") or "")[:10] or None

    p_dir = ROOT / "p"
    s_dir = ROOT / "s"
    p_dir.mkdir(exist_ok=True)
    s_dir.mkdir(exist_ok=True)

    producers = [p for p in producers if SAFE_ID.match(p.get("channelId") or "")]
    prod_by_id = {p["channelId"]: p for p in producers}

    # ---- collect ranked songs (union of the 4 lists, remember ranks) ----
    songs = {}
    for key, label in LIST_LABELS:
        for rank, v in enumerate(videos.get(key) or [], start=1):
            vid = v.get("videoId") or ""
            if not SAFE_ID.match(vid):
                continue
            rec = songs.setdefault(vid, {"data": v, "ranks": []})
            rec["ranks"].append((label, rank))
            # prefer record with score details
            if v.get("scoreParts") and not rec["data"].get("scoreParts"):
                rec["data"] = v

    # map channelId -> that producer's ranked songs (for cross-links)
    ranked_by_channel = {}
    for vid, rec in songs.items():
        ranked_by_channel.setdefault(rec["data"].get("channelId"), []).append(vid)

    written_p, written_s = set(), set()

    # ================= producer pages =================
    for p in producers:
        cid = p["channelId"]
        name = p.get("name") or "(不明)"
        subs = p.get("subscribers")
        url = f"{BASE}/p/{cid}.html"
        ch_songs = load_channel_songs(cid)
        if not ch_songs:  # fallback: recent uploads that are vocaloid originals
            ch_songs = sorted(
                [v for v in (p.get("recent") or []) if v.get("voca") and not v.get("cov")],
                key=lambda v: v.get("v") or 0, reverse=True)
        top = ch_songs[:10]
        n_songs = len(ch_songs)
        top_name = truncate(top[0].get("t", ""), 40) if top else ""

        desc_meta = f"{name}のボカロP情報。YouTube登録者{fmt_num(subs)}人。"
        if top_name:
            desc_meta += f"代表曲「{top_name}」（{fmt_num(top[0].get('v'))}回再生）"
        if n_songs:
            desc_meta += f"ほかボカロ曲{n_songs}曲の再生数データを掲載。"
        desc_meta += "毎日自動更新。"

        rows = []
        for i, v in enumerate(top, start=1):
            vid = v.get("id") or ""
            t = esc(truncate(v.get("t", ""), 70))
            link = f'<a href="../s/{vid}.html">{t}</a>' if vid in songs else \
                   (f'<a href="https://www.youtube.com/watch?v={esc(vid)}" target="_blank" rel="noopener noreferrer">{t}</a>' if SAFE_ID.match(vid) else t)
            rows.append(f'<tr><td class="rank">{i}</td><td>{link}</td><td class="num">{fmt_num(v.get("v"))}回</td></tr>')
        table = ("<table><tr><th>#</th><th>曲名</th><th class=\"num\">再生数</th></tr>" + "".join(rows) + "</table>") if rows else "<p>収録曲データは準備中です。</p>"

        ranked_links = ""
        r_vids = [x for x in ranked_by_channel.get(cid, []) if x not in {t.get("id") for t in top}]
        if r_vids:
            items = "".join(
                f'<li><a href="../s/{vid}.html">{esc(truncate(songs[vid]["data"].get("title", ""), 60))}</a></li>'
                for vid in r_vids[:5])
            ranked_links = f"<h2>ランキング登場曲</h2><ul>{items}</ul>"

        chips = [f'<span class="chip">登録者 {fmt_num(subs)}人</span>']
        if n_songs:
            chips.append(f'<span class="chip pk">収録ボカロ曲 {n_songs}曲</span>')
        if p.get("handle"):
            chips.append(f'<span class="chip yl">{esc(p["handle"])}</span>')

        thumb = p.get("thumbnail") or ""
        img_tag = f'<img src="{esc(thumb)}" alt="{esc(name)}" loading="lazy">' if thumb.startswith("https://") else ""
        about = clean_desc(p.get("description"), 200)
        about_html = f"<p>{esc(about)}</p>" if about else ""

        jsonld = [
            {
                "@context": "https://schema.org",
                "@type": "Person",
                "name": name,
                "url": url,
                "description": f"ボカロP。YouTube登録者{fmt_num(subs)}人。",
                "sameAs": [f"https://www.youtube.com/channel/{cid}"],
            },
            breadcrumb_ld([("ボカロトレンドDB", f"{BASE}/"), ("ボカロP名鑑", f"{BASE}/p/"), (name, url)]),
        ]

        body = f"""<nav class="bc"><a href="../index.html">ボカロトレンドDB</a> &gt; <a href="index.html">ボカロP名鑑</a> &gt; {esc(name)}</nav>
<div class="card">
  <div class="pf">{img_tag}<div>
  <h1>{esc(name)}</h1>
  <div class="meta-row">{''.join(chips)}</div>
  {about_html}
  </div></div>
</div>
<h2>人気ボカロ曲 TOP{len(top)}</h2>
<div class="card">{table}</div>
{ranked_links}
<p style="margin-top:18px">
<a class="btn tl" href="https://www.youtube.com/channel/{esc(cid)}" target="_blank" rel="noopener noreferrer">▶ YouTubeチャンネル</a>
<a class="btn" href="https://www.amazon.co.jp/s?k={esc(name)}%20CD&amp;tag={AMAZON_TAG}" target="_blank" rel="noopener noreferrer sponsored">💿 CDを探す</a>
<a class="btn tl" href="../index.html">📊 ランキングを見る</a>
</p>
<p class="note">再生数などのデータはYouTube公開情報を毎日自動収集したものです（{esc(lastmod or '')}更新）。ボカロ曲の判定はタイトル・概要欄による自動判定のため、判定誤りを含む場合があります。</p>"""

        title = f"{name}とは？登録者数・人気ボカロ曲ランキング | ボカロトレンドDB"
        (p_dir / f"{cid}.html").write_text(
            page(title, desc_meta, url, body, og_image=thumb if thumb.startswith("https://") else None, jsonld=jsonld),
            encoding="utf-8")
        written_p.add(f"{cid}.html")

    # ================= song pages =================
    for vid, rec in songs.items():
        v = rec["data"]
        title_raw = v.get("title") or "(無題)"
        cname = v.get("channelName") or ""
        cid = v.get("channelId") or ""
        url = f"{BASE}/s/{vid}.html"
        score = v.get("score")
        grade = v.get("scoreGrade") or ""
        vocal = v.get("vocal") or ""
        pub = (v.get("publishDate") or "")[:10]

        rank_chips = "".join(
            f'<span class="chip">{label} {rank}位</span>' for label, rank in rec["ranks"])

        parts = v.get("scoreParts") or {}
        score_rows = ""
        if parts:
            labels = {"like": "好感度", "likeRatio": "好感度(比率)", "momentum": "勢い", "spread": "拡散力"}
            score_rows = "".join(
                f"<tr><td>{esc(labels.get(k, k))}</td><td class='num'>{esc(p_)}</td></tr>"
                for k, p_ in parts.items())
            score_rows = f"<h2>VocaScore内訳</h2><div class='card'><table>{score_rows}</table><p class='note'>VocaScore = 好感度40 + 拡散力30 + 勢い30。全ランクイン曲の傾向から毎日学習して採点。</p></div>"

        prod_link = f'<a href="../p/{cid}.html">{esc(cname)}</a>' if cid in prod_by_id else esc(cname)

        others = ""
        sib = [x for x in ranked_by_channel.get(cid, []) if x != vid][:5]
        if sib:
            items = "".join(
                f'<li><a href="{x}.html">{esc(truncate(songs[x]["data"].get("title", ""), 60))}</a></li>' for x in sib)
            others = f"<h2>{esc(cname)}の他のランクイン曲</h2><ul>{items}</ul>"

        desc_meta = (f"{truncate(title_raw, 50)}（{cname}）の再生数{fmt_num(v.get('views'))}回・"
                     f"高評価{fmt_num(v.get('likes'))}"
                     + (f"・VocaScore {score}（{grade}）" if score is not None else "")
                     + (f"。{vocal}歌唱" if vocal else "")
                     + "。YouTubeボカロランキングを毎日自動更新。")

        jsonld = [
            {
                "@context": "https://schema.org",
                "@type": "VideoObject",
                "name": title_raw,
                "thumbnailUrl": v.get("thumbnail") or "",
                "uploadDate": pub or None,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "interactionStatistic": {
                    "@type": "InteractionCounter",
                    "interactionType": {"@type": "WatchAction"},
                    "userInteractionCount": v.get("views") or 0,
                },
            },
            breadcrumb_ld([("ボカロトレンドDB", f"{BASE}/"), ("ランキング曲", f"{BASE}/s/"), (truncate(title_raw, 40), url)]),
        ]
        jsonld[0] = {k: val for k, val in jsonld[0].items() if val is not None}

        stats = [
            f'<span class="chip">再生 {fmt_num(v.get("views"))}回</span>',
            f'<span class="chip pk">高評価 {fmt_num(v.get("likes"))}</span>',
        ]
        if score is not None:
            stats.append(f'<span class="chip yl">VocaScore {esc(score)} ({esc(grade)})</span>')
        if vocal:
            stats.append(f'<span class="chip">歌唱: {esc(vocal)}</span>')
        if pub:
            stats.append(f'<span class="chip">投稿日 {esc(pub)}</span>')

        thumb = v.get("thumbnail") or ""
        thumb_html = f'<img class="thumb" src="{esc(thumb)}" alt="{esc(truncate(title_raw, 60))}" loading="lazy">' if thumb.startswith("https://") else ""

        body = f"""<nav class="bc"><a href="../index.html">ボカロトレンドDB</a> &gt; <a href="index.html">ランキング曲</a> &gt; {esc(truncate(title_raw, 40))}</nav>
<div class="card">
  <h1>{esc(title_raw)}</h1>
  <p>by {prod_link}</p>
  <div class="meta-row">{rank_chips}</div>
  {thumb_html}
  <div class="meta-row">{''.join(stats)}</div>
</div>
{score_rows}
{others}
<p style="margin-top:18px">
<a class="btn tl" href="https://www.youtube.com/watch?v={esc(vid)}" target="_blank" rel="noopener noreferrer">▶ YouTubeで聴く</a>
<a class="btn tl" href="../index.html">📊 最新ランキングを見る</a>
</p>
<p class="note">データはYouTube公開情報を毎日自動収集（{esc(lastmod or '')}時点）。ランキング順位は収集時点のものです。</p>"""

        title = f"{truncate(title_raw, 45)} 再生数・VocaScore | ボカロトレンドDB"
        (s_dir / f"{vid}.html").write_text(
            page(title, desc_meta, url, body, og_image=thumb if thumb.startswith("https://") else None, jsonld=jsonld),
            encoding="utf-8")
        written_s.add(f"{vid}.html")

    # ================= directory pages =================
    plist = sorted(producers, key=lambda p: p.get("subscribers") or 0, reverse=True)
    rows = "".join(
        f'<tr><td class="rank">{i}</td><td><a href="{p["channelId"]}.html">{esc(p.get("name"))}</a></td>'
        f'<td class="num">{fmt_num(p.get("subscribers"))}人</td></tr>'
        for i, p in enumerate(plist, start=1))
    body = f"""<nav class="bc"><a href="../index.html">ボカロトレンドDB</a> &gt; ボカロP名鑑</nav>
<h1>ボカロP名鑑 — 全{len(plist)}名</h1>
<p>YouTube登録者1万人以上、またはボカロ曲500万再生以上のボカロPを毎日自動収集。名前をタップすると人気曲・登録者数などの詳細が見られます。</p>
<div class="card"><table><tr><th>#</th><th>ボカロP</th><th class="num">登録者</th></tr>{rows}</table></div>"""
    (p_dir / "index.html").write_text(
        page(f"ボカロP一覧 全{len(plist)}名（登録者数ランキング） | ボカロトレンドDB",
             f"ボカロP{len(plist)}名の登録者数・人気曲データベース。YouTube公開情報から毎日自動更新。",
             f"{BASE}/p/", body,
             jsonld=breadcrumb_ld([("ボカロトレンドDB", f"{BASE}/"), ("ボカロP名鑑", f"{BASE}/p/")])),
        encoding="utf-8")
    written_p.add("index.html")

    sections = ""
    for key, label in LIST_LABELS:
        lst = videos.get(key) or []
        rows = "".join(
            f'<tr><td class="rank">{i}</td><td><a href="{v["videoId"]}.html">{esc(truncate(v.get("title", ""), 60))}</a></td>'
            f'<td>{esc(v.get("channelName"))}</td><td class="num">{fmt_num(v.get("views"))}回</td></tr>'
            for i, v in enumerate(lst, start=1) if SAFE_ID.match(v.get("videoId") or ""))
        sections += f'<h2>{label}ランキング</h2><div class="card"><table><tr><th>#</th><th>曲名</th><th>ボカロP</th><th class="num">再生数</th></tr>{rows}</table></div>'
    body = f"""<nav class="bc"><a href="../index.html">ボカロトレンドDB</a> &gt; ランキング曲</nav>
<h1>ボカロ曲ランキング（週間・月間・年間・全期間）</h1>
<p>YouTubeのボカロオリジナル曲を再生数順に毎日自動集計。曲名をタップするとVocaScore・再生数の詳細が見られます。最新のインタラクティブ版は<a href="../index.html">トップページ</a>へ。</p>
{sections}"""
    (s_dir / "index.html").write_text(
        page("ボカロ曲ランキング 週間・月間・年間・全期間 | ボカロトレンドDB",
             "YouTubeボカロ曲の週間・月間・年間・全期間ランキング。再生数・VocaScoreを毎日自動更新。",
             f"{BASE}/s/", body,
             jsonld=breadcrumb_ld([("ボカロトレンドDB", f"{BASE}/"), ("ランキング曲", f"{BASE}/s/")])),
        encoding="utf-8")
    written_s.add("index.html")

    # ================= prune stale pages =================
    removed = 0
    for d, keep in ((p_dir, written_p), (s_dir, written_s)):
        for f in d.glob("*.html"):
            if f.name not in keep:
                f.unlink()
                removed += 1

    # ================= sitemap =================
    def entry(loc, freq, prio):
        lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        return f"<url><loc>{loc}</loc>{lm}<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"

    urls = [entry(f"{BASE}/", "daily", "1.0"),
            entry(f"{BASE}/p/", "daily", "0.8"),
            entry(f"{BASE}/s/", "daily", "0.8")]
    urls += [entry(f"{BASE}/p/{n[:-5]}.html", "weekly", "0.7") for n in sorted(written_p) if n != "index.html"]
    urls += [entry(f"{BASE}/s/{n[:-5]}.html", "weekly", "0.6") for n in sorted(written_s) if n != "index.html"]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "\n".join(urls) + "\n</urlset>\n")
    (ROOT / "sitemap.xml").write_text(sitemap, encoding="utf-8")

    print(f"[generate_pages] producers={len(written_p)-1} songs={len(written_s)-1} "
          f"removed_stale={removed} sitemap_urls={len(urls)}")


if __name__ == "__main__":
    sys.exit(main())
