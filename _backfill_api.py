# -*- coding: utf-8 -*-
"""YouTube Data API で全ボカロPのデータを一括再構築
（20件ごとに保存・今日取得済みはスキップ＝中断しても再実行で続きから）"""
import sys, json, time, datetime
sys.path.insert(0, r"C:\Users\USER\Claudeの遊び場\ボカロデータベース")
import update_data as u

assert u.YT_API_KEY, "APIキーがありません"
u.TODAY = datetime.date.today().isoformat()
u.CHANNELS_DIR.mkdir(exist_ok=True)
pf = u.DATA_DIR / "producers.json"
pd = json.loads(pf.read_text(encoding="utf-8"))
producers = pd["producers"]


def save():
    pd["producers"] = sorted(producers,
                             key=lambda x: x.get("subscribers") or 0, reverse=True)
    pd["updated"] = datetime.datetime.now().isoformat()
    pf.write_text(json.dumps(pd, ensure_ascii=False, indent=1), encoding="utf-8")


# 1) 基本情報をバッチで一括更新（登録者数・開設日・累計再生・正確な値）
info = u.api_channels([p["channelId"] for p in producers]) or {}
for p in producers:
    det = info.get(p["channelId"])
    if det:
        p.update({k: v for k, v in det.items() if v})
        p["lastUpdated"] = u.TODAY
u.log(f"基本情報一括更新: {len(info)}件")
save()

# 2) 全曲リスト + 直近動画（全曲データから導出するので追加リクエスト不要）
done = 0
for i, p in enumerate(producers):
    cid = p["channelId"]
    f = u.CHANNELS_DIR / f"{cid}.json"
    already = False
    if f.exists():
        try:
            already = json.loads(f.read_text(encoding="utf-8")).get("fullFetched") == u.TODAY
        except json.JSONDecodeError:
            pass
    if already and p.get("recentFetched") == u.TODAY:
        continue
    u.log(f"[{i + 1}/{len(producers)}] {p['name']}")
    vids = u.fetch_all_channel_videos(cid)
    if vids:
        n = u.save_channel_videos(p, vids)
        rec = sorted([v for v in vids if v.get("d") is not None],
                     key=lambda x: x["d"])[:30]
        p["recent"] = [{k: v for k, v in r.items() if k != "publishedAt"}
                       for r in rec]
        p["recentFetched"] = u.TODAY
        u.log(f"  {len(vids)}本中{n}本掲載")
    done += 1
    if done % 20 == 0:
        save()
    time.sleep(0.15)
save()
u.log(f"API一括バックフィル完了（クォータ使用量: {u.API_UNITS}ユニット / 無料枠10,000）")
