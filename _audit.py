# -*- coding: utf-8 -*-
"""名鑑の基準適合性の監査（読み取り専用・producers.json には書き込まない）

基準:
  入鑑 = (登録者1万人以上 or ランクイン曲に500万再生以上あり) かつ ボカロ要素の検証合格
検査:
  A) 現在の名鑑の内訳（基準別）
  B) 基準違反エントリ（登録者1万未満かつbigHitなし）
  C) ランキング登場チャンネルのうち、基準を満たすのに名鑑にいない「漏れ」
"""
import sys, io, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\Users\USER\Claudeの遊び場\ボカロデータベース")
import update_data as u

u.TODAY = datetime.date.today().isoformat()
pd = json.loads((u.DATA_DIR / "producers.json").read_text(encoding="utf-8"))
vd = json.loads((u.DATA_DIR / "videos.json").read_text(encoding="utf-8"))
producers = {p["channelId"]: p for p in pd["producers"]}

# --- A) 内訳 ---
n = len(producers)
b10k = sum(1 for p in producers.values() if (p.get("subscribers") or 0) >= 10000)
b50k = sum(1 for p in producers.values() if (p.get("subscribers") or 0) >= 50000)
bighit = [p for p in producers.values() if (p.get("subscribers") or 0) < 10000]
print(f"[A] 名鑑 {n}件 / 登録者1万以上 {b10k} / 5万以上 {b50k} / 1万未満(bigHit枠) {len(bighit)}")

# --- 500万再生チャンネルの集合（ランキングから） ---
big_by_ch = {}
ranked_ch = {}
for k in ("weekly", "monthly", "yearly", "alltime"):
    for v in vd.get(k, []):
        cid = v.get("channelId")
        if not cid:
            continue
        ranked_ch.setdefault(cid, {"name": v.get("channelName"), "max": 0})
        ranked_ch[cid]["max"] = max(ranked_ch[cid]["max"], v.get("views") or 0)
        if (v.get("views") or 0) >= u.BIG_HIT_VIEWS:
            big_by_ch[cid] = max(big_by_ch.get(cid, 0), v["views"])

# --- B) 基準違反（1万未満なのにbigHit曲もない） ---
print("\n[B] 基準違反の可能性:")
viol = 0
for p in bighit:
    cid = p["channelId"]
    if cid not in big_by_ch and not p.get("bigHit"):
        print(f"  {p['name']} 登録者{p.get('subscribers')} bigHitなし")
        viol += 1
if viol == 0:
    print("  なし")

# --- C) ランキング登場なのに名鑑にいないチャンネル ---
missing = {cid: info for cid, info in ranked_ch.items()
           if cid not in producers and cid not in u.NON_PRODUCER_IDS}
print(f"\n[C] ランキング登場かつ名鑑未登録: {len(missing)}件 → 登録者数をAPIで確認")
det = u.api_channels(list(missing.keys())) or {}
leaks = []
for cid, info in missing.items():
    d = det.get(cid, {})
    subs = d.get("subscribers") or 0
    name = d.get("name") or info["name"]
    qualified = subs >= u.MIN_SUBSCRIBERS or cid in big_by_ch
    if qualified and not (name or "").endswith("- Topic"):
        leaks.append({"channelId": cid, "name": name, "subscribers": subs,
                      "maxViews": info["max"], "bigHit": cid in big_by_ch})
leaks.sort(key=lambda x: x["subscribers"], reverse=True)
print(f"    基準を満たす漏れ: {len(leaks)}件")
for x in leaks[:40]:
    tag = " [500万再生]" if x["bigHit"] else ""
    print(f"  漏れ: {x['name']} 登録者{x['subscribers']} 最大{x['maxViews']}回{tag}")
(u.DATA_DIR / "audit_leaks.json").write_text(
    json.dumps(leaks, ensure_ascii=False, indent=1), encoding="utf-8")
print("\n→ data/audit_leaks.json に保存（あとで一括追加可能）")
print(f"APIクォータ: {u.API_UNITS}ユニット")
