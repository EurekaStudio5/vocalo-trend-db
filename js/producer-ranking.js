/* ===== ボカロPランキング =====
   PRODUCERS / RANKINGS (app.js のグローバル) からPごとの統計を組み立て、
   多数の軸でランキング表示する。チャンネル名クリックで詳細パネルを開く。 */
"use strict";

(() => {

/* Amazonアソシエイト トラッキングID（CD検索リンクに自動付与） */
const AMAZON_TAG = "vocaloidtrend-22";

/* ---------- 統計ヘルパー ---------- */
const mean = (a) => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
const median = (a) => {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const stddev = (a) => {
  if (a.length < 2) return null;
  const m = mean(a);
  return Math.sqrt(mean(a.map((x) => (x - m) ** 2)));
};
const cv = (a) => {
  const m = mean(a), s = stddev(a);
  return m && s != null ? s / m : null;
};

/* ---------- ボーカル判定（タイトルから・複数検出） ---------- */
const VOCAL_DEFS = [
  ["初音ミク", ["初音ミク", "miku", "ミク"]],
  ["重音テト", ["重音テト", "teto", "テト"]],
  ["可不", ["可不", "kafu"]],
  ["GUMI", ["gumi", "グミ"]],
  ["鏡音リン・レン", ["鏡音", "リン", "レン", "rin", "len"]],
  ["巡音ルカ", ["巡音", "ルカ", "luka"]],
  ["flower", ["feat.flower", "feat. flower", "ft.flower", "ft. flower", "/flower", "/ flower", "v flower", "flower】", "【flower", "フラワ"]],
  ["IA", [" ia ", "【ia】"]],
  ["音街ウナ", ["音街ウナ", "otomachi una"]],
  ["SOLARIA", ["solaria"]],
  ["ASTERIAN", ["asterian"]],
  ["Eleanor Forte", ["eleanor forte"]],
  ["Yi Xi", ["yi xi"]],
];
function detectVocals(title) {
  const t = title.toLowerCase();
  const found = [];
  for (const [name, kws] of VOCAL_DEFS) {
    if (kws.some((k) => t.includes(k))) found.push(name);
  }
  return found;
}

/* ボカロ曲判定: 同じチャンネルのゲーム動画・本人歌唱曲などを集計から除外する。
   タイトルにボーカル名やボカロ系キーワードがあるものだけをボカロ曲とみなす。 */
const VOCALO_TITLE_KEYWORDS = [
  "初音ミク", "ミク", "miku", "hatsune", "重音テト", "テト", "teto",
  "可不", "kafu", "gumi", "グミ", "鏡音", "リン・レン", "リンレン",
  "巡音", "ルカ", "luka", "feat.flower", "feat. flower", "ft.flower", "ft. flower", "/flower", "/ flower", "v flower", "flower】", "【flower", "フラワー", "音街ウナ", "歌愛ユキ",
  "結月ゆかり", "星界", "裏命", "知声", "狐子", "羽累", "夢ノ結唱",
  "ボカロ", "ボーカロイド", "vocaloid", "synthesizer v", "synthv",
  "cevio", "utau", "ずんだもん", "ボカコレ", "vocaloid原曲", "【ia】", " ia ",
  // 海外ボーカル
  "solaria", "asterian", "eleanor forte", "yi xi", "ninezero", "hayden",
  "saros", "gumi english", "miku english", "adachi rei",
];
function isVocaloTitle(title) {
  const t = (title || "").toLowerCase();
  return VOCALO_TITLE_KEYWORDS.some((k) => t.includes(k));
}

const charRate = (text, re) => {
  if (!text.length) return null;
  return (text.match(re) || []).length / text.length * 100;
};

/* ---------- Pごとの統計を構築 ---------- */
let STATS = null;        // channelId -> stats
let RANKED_BY_CH = null; // channelId -> {weekly, monthly, yearly}

function buildStats() {
  STATS = new Map();
  RANKED_BY_CH = {};
  for (const period of ["weekly", "monthly", "yearly"]) {
    (RANKINGS[period] || []).forEach((v, i) => {
      const c = (RANKED_BY_CH[v.channelId] ||= { weekly: [], monthly: [], yearly: [] });
      c[period].push({ ...v, rank: i + 1 });
    });
  }

  for (const p of PRODUCERS) {
    const s = { p };
    // ボカロ曲を集計対象にする。過半数がボカロ曲のチャンネルは全投稿を対象に
    // （タイトルにボーカル名を書かない流儀のPでも0曲にならない）。
    // ボカロ曲が少数派の混在チャンネルだけボカロ曲に絞る。
    const recAll = (p.recent || []).filter((r) => r.v != null);
    const flagged = recAll.filter((r) => r.voca || isVocaloTitle(r.t));
    const rec = (flagged.length === 0
      || flagged.length / Math.max(recAll.length, 1) >= 0.3) ? recAll : flagged;
    s.recN = rec.length;
    const vs = rec.map((r) => r.v);
    s.avgV = mean(vs); s.medV = median(vs);
    s.maxV = vs.length ? Math.max(...vs) : null;
    s.sumV = vs.length ? vs.reduce((a, b) => a + b, 0) : null;
    s.cv = vs.length >= 5 ? cv(vs) : null;
    s.burst = s.medV > 0 ? s.maxV / s.medV : null;
    s.hits1 = vs.length >= 5 ? vs.filter((v) => v >= 1e4).length / vs.length * 100 : null;
    s.hits10 = vs.length >= 5 ? vs.filter((v) => v >= 1e5).length / vs.length * 100 : null;

    // 投稿ペース
    const ds = rec.map((r) => r.d).filter((d) => d != null).sort((a, b) => a - b);
    if (ds.length >= 5) {
      const span = ds[ds.length - 1] - ds[0];
      s.perMonth = span > 3 ? (ds.length - 1) / span * 30 : null;
      const gaps = [];
      for (let i = 1; i < ds.length; i++) gaps.push(ds[i] - ds[i - 1]);
      s.gapAvg = mean(gaps);
      s.gapCV = gaps.length >= 4 ? cv(gaps) : null;
      s.lastUpload = ds[0];
    }
    if (vs.length >= 10) {
      const recent5 = mean(vs.slice(0, 5));
      const older = mean(vs.slice(5));
      s.growth = older > 0 ? recent5 / older * 100 : null;
    }
    s.recent3 = vs.length >= 3 ? mean(vs.slice(0, 3)) : null;

    // 尺
    const lens = rec.map((r) => r.len).filter((l) => l != null && l > 0);
    s.lenN = lens.length;
    s.avgLen = mean(lens);
    s.lenCV = lens.length >= 5 ? cv(lens) : null;
    if (lens.length >= 5) {
      s.just3 = lens.filter((l) => Math.abs(l - 180) <= 15).length / lens.length * 100;
      s.pop2 = lens.filter((l) => l >= 120 && l < 180).length / lens.length * 100;
      s.epic5 = lens.filter((l) => l >= 300).length / lens.length * 100;
      s.shortRate = lens.filter((l) => l <= 60).length / lens.length * 100;
    }
    s.watchHours = rec.length
      ? rec.reduce((a, r) => a + (r.v || 0) * (r.len || 0), 0) / 3600 : null;

    // 曲名の傾向
    const titles = rec.map((r) => r.t || "");
    if (titles.length >= 5) {
      const joined = titles.join("");
      s.titleLen = mean(titles.map((t) => t.length));
      s.hira = charRate(joined, /[ぁ-ん]/g);
      s.kata = charRate(joined, /[ァ-ヶー]/g);
      s.kanji = charRate(joined, /[一-龯]/g);
      s.latin = charRate(joined, /[a-zA-Za-zA-Z]/g);
      const rate = (fn) => titles.filter(fn).length / titles.length * 100;
      s.brackets = rate((t) => /[【】]/.test(t));
      s.engTitle = rate((t) => {
        const l = (t.match(/[a-zA-Z]/g) || []).length;
        return t.length > 0 && l / t.length > 0.7;
      });
      s.bokakore = rate((t) => t.includes("ボカコレ"));

      // 使用ボーカル
      const vocalLists = titles.map(detectVocals);
      const detected = vocalLists.filter((l) => l.length > 0);
      s.vocalN = detected.length;
      if (detected.length >= 3) {
        const counts = {};
        detected.forEach((l) => l.forEach((v) => { counts[v] = (counts[v] || 0) + 1; }));
        s.vocalRates = {};
        for (const [name] of VOCAL_DEFS) {
          s.vocalRates[name] = (counts[name] || 0) / detected.length * 100;
        }
        s.minorRate = (titles.length - detected.length) / titles.length * 100;
        s.harem = Object.keys(counts).length;
        s.devoted = Math.max(...Object.values(counts)) / detected.length * 100;
        s.duet = detected.filter((l) => l.length >= 2).length / detected.length * 100;
      }
    }

    // ランクイン実績
    const rk = RANKED_BY_CH[p.channelId] || { weekly: [], monthly: [], yearly: [] };
    s.wIn = rk.weekly.length; s.mIn = rk.monthly.length; s.yIn = rk.yearly.length;
    const allRanked = [...rk.weekly, ...rk.monthly, ...rk.yearly];
    const seen = new Set();
    s.rankedAll = allRanked.filter((v) => !seen.has(v.videoId) && seen.add(v.videoId));
    s.allIn = s.rankedAll.length;
    s.wBest = rk.weekly.length ? Math.min(...rk.weekly.map((v) => v.rank)) : null;
    s.mBest = rk.monthly.length ? Math.min(...rk.monthly.map((v) => v.rank)) : null;
    s.yBest = rk.yearly.length ? Math.min(...rk.yearly.map((v) => v.rank)) : null;
    s.crown = (s.wIn ? 1 : 0) + (s.mIn ? 1 : 0) + (s.yIn ? 1 : 0);
    s.yearSum = rk.yearly.length ? rk.yearly.reduce((a, v) => a + (v.views || 0), 0) : null;

    const scores = s.rankedAll.map((v) => v.score).filter((x) => x != null);
    s.avgScore = scores.length ? mean(scores) : null;
    s.maxScore = scores.length ? Math.max(...scores) : null;
    s.minScore = scores.length >= 3 ? Math.min(...scores) : null;
    const likeRatios = s.rankedAll.map((v) => v.scoreParts?.likeRatio).filter((x) => x != null);
    s.avgLikeRatio = likeRatios.length ? mean(likeRatios) : null;
    s.sleeper = (() => {
      const c = s.rankedAll.filter((v) => v.score != null && v.views < 5e4);
      return c.length ? Math.max(...c.map((v) => v.score)) : null;
    })();
    s.addict = s.rankedAll.length
      ? Math.max(...s.rankedAll.map((v) => v.viewsPerDay || 0)) : null;
    s.avgVPD = rk.yearly.length
      ? mean(rk.yearly.map((v) => v.viewsPerDay || 0)) : null;

    // 投稿時刻・曜日（publishDate があるランクイン曲ベース）
    const dated = s.rankedAll
      .map((v) => v.publishDate ? new Date(v.publishDate) : null)
      .filter((d) => d && !isNaN(d));
    if (dated.length >= 2) {
      const hr = (fn) => dated.filter(fn).length / dated.length * 100;
      s.lateNight = hr((d) => d.getHours() < 5);
      s.morning = hr((d) => d.getHours() >= 5 && d.getHours() < 10);
      s.golden = hr((d) => d.getHours() >= 18 && d.getHours() < 23);
      s.friday = hr((d) => d.getDay() === 5);
      s.weekend = hr((d) => d.getDay() === 0 || d.getDay() === 6);
    }

    // チャンネル情報
    const subs = p.subscribers || null;
    s.subs = subs;
    s.totalViews = p.totalViews || null;
    s.totalVideos = p.totalVideos || null;
    s.viewsPerVideo = s.totalViews && s.totalVideos ? s.totalViews / s.totalVideos : null;
    s.influence = subs && s.totalViews ? Math.sqrt(subs * s.totalViews) : null;
    s.subsRatio = subs && s.totalViews ? s.totalViews / subs : null;
    if (p.joined) {
      const years = (Date.now() - new Date(p.joined).getTime()) / 3.15576e10;
      if (years > 0.2) {
        s.chAge = years;
        s.subsPerYear = subs ? subs / years : null;
      }
    }
    s.weeklyViews = p.weeklyViews || null;
    s.weeklyMomentum = subs && p.weeklyViews ? p.weeklyViews / subs * 100 : null;
    s.algoChild = subs && s.maxV ? s.maxV / subs : null;
    s.fanDensity = subs && s.medV ? s.medV / subs * 100 : null;
    s.buzzRate = subs && vs.length >= 5
      ? vs.filter((v) => v > subs).length / vs.length * 100 : null;
    s.nameHasP = /[PpＰｐ](?![a-zA-Z])|ピー$/.test(p.name || "");
    s.ghost = s.lastUpload != null ? s.lastUpload : null;
    s.darkhorse = subs && subs < 5e4 && s.avgScore != null ? s.avgScore : null;
    s.repDep = s.maxV && s.sumV ? s.maxV / s.sumV * 100 : null;

    STATS.set(p.channelId, s);
  }

  // 総合偏差値（登録者・高評価率・成長率・地力のパーセンタイル平均）
  const keys = ["subs", "avgLikeRatio", "growth", "medV"];
  const sorted = {};
  for (const k of keys) {
    sorted[k] = [...STATS.values()].map((s) => s[k]).filter((x) => x != null).sort((a, b) => a - b);
  }
  const pct = (arr, x) => {
    if (!arr.length) return null;
    let lo = 0;
    while (lo < arr.length && arr[lo] <= x) lo++;
    return lo / arr.length;
  };
  for (const s of STATS.values()) {
    const ps = keys.map((k) => s[k] != null ? pct(sorted[k], s[k]) : null).filter((x) => x != null);
    s.deviation = ps.length >= 2 ? 50 + (mean(ps) - 0.5) * 40 : null;
  }
}

/* ---------- フォーマッタ ---------- */
const UNIT_DAYS = { ja: "日", en: " days", zh: "天", ko: "일" };
const UNIT_YEARS = { ja: "年", en: " yrs", zh: "年", ko: "년" };
const UNIT_HOURS = { ja: "時間", en: " hrs", zh: "小时", ko: "시간" };
const UNIT_TIMES = { ja: "倍", en: "×", zh: "倍", ko: "배" };
const fVar = (n) => ({ ja: `ブレ${n}%`, en: `±${n}%`, zh: `波动${n}%`, ko: `편차${n}%` }[LANG]);
const F = {
  num: (x) => fmtNum(Math.round(x)),
  cnt: (u) => (x) => `${fmtNum(Math.round(x))}${tUnit(u)}`,
  pct: (x) => `${x.toFixed(1)}%`,
  pct0: (x) => `${Math.round(x)}%`,
  score: (x) => `${x.toFixed(1)}${tUnit("点")}`,
  ratio: (x) => `${x >= 10 ? Math.round(x) : x.toFixed(1)}${UNIT_TIMES[LANG]}`,
  days: (x) => `${x.toFixed(1)}${UNIT_DAYS[LANG]}`,
  years: (x) => `${x.toFixed(1)}${UNIT_YEARS[LANG]}`,
  permonth: (x) => `${x.toFixed(1)}${tUnit("本/月")}`,
  mmss: (x) => `${Math.floor(x / 60)}:${String(Math.round(x % 60)).padStart(2, "0")}`,
  hours: (x) => `${fmtNum(Math.round(x))}${UNIT_HOURS[LANG]}`,
  rank: (x) => rankLabel(x),
  chars: (x) => `${x.toFixed(1)}${tUnit("文字")}`,
  dev: (x) => x.toFixed(1),
};

/* ---------- 軸定義 ----------
   { c: カテゴリ, n: 名前, d: 説明, v: s=>値, f: フォーマッタ, asc: 昇順なら true } */
const AXES = [
  // ===== 基本データ =====
  { c: "基本データ", n: "登録者数", d: "チャンネル登録者数。", v: (s) => s.subs, f: F.cnt("人") },
  { c: "基本データ", n: "チャンネル累計再生数", d: "チャンネル開設からの総再生数。", v: (s) => s.totalViews, f: F.cnt("回") },
  { c: "基本データ", n: "投稿動画本数", d: "チャンネルの動画本数。", v: (s) => s.totalVideos, f: F.cnt("本") },
  { c: "基本データ", n: "1本あたり平均再生数（累計）", d: "累計再生数÷動画本数。", v: (s) => s.viewsPerVideo, f: F.cnt("回") },
  { c: "基本データ", n: "週間ランクイン曲の合計再生数", d: "今週ランクインした曲の再生数合計。", v: (s) => s.weeklyViews, f: F.cnt("回") },
  { c: "基本データ", n: "年間ランクイン曲の合計再生数", d: "年間ランキングに入った曲の再生数合計。", v: (s) => s.yearSum, f: F.cnt("回") },
  { c: "基本データ", n: "総合影響力（登録者×累計再生）", d: "登録者数と累計再生数の幾何平均。チャンネル規模の総合値。", v: (s) => s.influence, f: F.num },
  { c: "基本データ", n: "累計再生数÷登録者数", d: "登録者1人あたり何回再生されているか。固定ファン外への届き方。", v: (s) => s.subsRatio, f: F.ratio },

  // ===== 実力・評価 =====
  { c: "実力・評価", n: "平均VocaScore（ランクイン曲）", d: "ランクイン曲のVocaScore平均。チャンネル規模に依存しない曲の評価。", v: (s) => s.avgScore, f: F.score },
  { c: "実力・評価", n: "最高VocaScore（ランクイン曲）", d: "ランクイン曲のうち最高のVocaScore。", v: (s) => s.maxScore, f: F.score },
  { c: "実力・評価", n: "平均高評価率（ランクイン曲）", d: "高評価数÷再生数の平均。聴いた人の満足度。", v: (s) => s.avgLikeRatio, f: F.pct },
  { c: "実力・評価", n: "最低VocaScore（ランクイン3曲以上）", d: "ランクイン曲の最低スコア。高いほど「どの曲も強い」。", v: (s) => s.minScore, f: F.score },
  { c: "実力・評価", n: "直近動画の平均再生数", d: "直近投稿（最大30本）の平均再生数。", v: (s) => s.avgV, f: F.cnt("回") },
  { c: "実力・評価", n: "直近動画の再生数中央値", d: "外れ値に影響されにくい「ふだんの再生数」。", v: (s) => s.medV, f: F.cnt("回") },
  { c: "実力・評価", n: "直近動画の最高再生数", d: "直近投稿でいちばん再生された動画。", v: (s) => s.maxV, f: F.cnt("回") },
  { c: "実力・評価", n: "再生数の安定度", d: "直近の再生数のばらつき（変動係数）が小さい順。", v: (s) => s.cv, f: (x) => fVar(Math.round(x * 100)), asc: true },
  { c: "実力・評価", n: "最大ヒット倍率（最高÷中央値）", d: "最大ヒットがふだんの何倍か。当たり外れの大きさ。", v: (s) => s.burst, f: F.ratio },
  { c: "実力・評価", n: "1万再生達成率（直近動画）", d: "直近投稿のうち1万再生を超えた割合。", v: (s) => s.hits1, f: F.pct0 },
  { c: "実力・評価", n: "10万再生達成率（直近動画）", d: "直近投稿のうち10万再生を超えた割合。", v: (s) => s.hits10, f: F.pct0 },
  { c: "実力・評価", n: "隠れ名曲スコア", d: "再生数5万未満の曲のうち最高のVocaScore。まだ埋もれている良曲。", v: (s) => s.sleeper, f: F.score },

  // ===== 勢い・効率 =====
  { c: "勢い・効率", n: "直近の成長率", d: "最新5本の平均再生数÷それ以前の平均。100%超えなら上昇中。", v: (s) => s.growth, f: F.pct0 },
  { c: "勢い・効率", n: "週間再生数÷登録者数", d: "今週のランクイン再生数を登録者数で割った値。規模比でいま伸びている人。", v: (s) => s.weeklyMomentum, f: F.pct },
  { c: "勢い・効率", n: "最高再生数÷登録者数", d: "直近の最大ヒットが登録者数の何倍か。チャンネル規模を超えた拡散。", v: (s) => s.algoChild, f: F.ratio },
  { c: "勢い・効率", n: "再生数中央値÷登録者数", d: "ふだんの再生数が登録者数の何%か。ファンの視聴率に近い指標。", v: (s) => s.fanDensity, f: F.pct },
  { c: "勢い・効率", n: "登録者数超え再生の達成率", d: "直近投稿のうち、再生数が登録者数を上回った動画の割合。", v: (s) => s.buzzRate, f: F.pct0 },
  { c: "勢い・効率", n: "最新3本の平均再生数", d: "直近3本の平均。現時点の勢い。", v: (s) => s.recent3, f: F.cnt("回") },
  { c: "勢い・効率", n: "登録者増加ペース（人/年）", d: "登録者数÷チャンネル運営年数。", v: (s) => s.subsPerYear, f: F.cnt("人/年") },
  { c: "勢い・効率", n: "年間ランクイン曲の平均日次再生数", d: "年間ランクイン曲の「1日あたり再生数」の平均。", v: (s) => s.avgVPD, f: F.cnt("回/日") },

  // ===== 投稿スタイル =====
  { c: "投稿スタイル", n: "投稿頻度（本/月）", d: "直近の投稿ペース。", v: (s) => s.perMonth, f: F.permonth },
  { c: "投稿スタイル", n: "平均投稿間隔（日）", d: "投稿と投稿のあいだの平均日数。長い順。", v: (s) => s.gapAvg, f: F.days },
  { c: "投稿スタイル", n: "投稿間隔の規則性", d: "投稿間隔のばらつきが小さい順。定期投稿型。", v: (s) => s.gapCV, f: (x) => fVar(Math.round(x * 100)), asc: true },
  { c: "投稿スタイル", n: "平均動画時間（長い順）", d: "直近動画の平均の長さ。", v: (s) => s.lenN >= 5 ? s.avgLen : null, f: F.mmss },
  { c: "投稿スタイル", n: "平均動画時間（短い順）", d: "直近動画の平均の長さが短い順。", v: (s) => s.lenN >= 5 ? s.avgLen : null, f: F.mmss, asc: true },
  { c: "投稿スタイル", n: "3分前後の曲の割合", d: "3分±15秒の動画の割合。", v: (s) => s.just3, f: F.pct0 },
  { c: "投稿スタイル", n: "2分台の曲の割合", d: "2分以上3分未満の動画の割合。近年のヒット曲に多い尺。", v: (s) => s.pop2, f: F.pct0 },
  { c: "投稿スタイル", n: "5分以上の曲の割合", d: "長尺曲の割合。", v: (s) => s.epic5, f: F.pct0 },
  { c: "投稿スタイル", n: "動画時間の統一度", d: "動画の長さのばらつきが小さい順。", v: (s) => s.lenCV, f: (x) => fVar(Math.round(x * 100)), asc: true },
  { c: "投稿スタイル", n: "60秒以下の動画の割合", d: "ショート動画の割合。", v: (s) => s.shortRate, f: F.pct0 },
  { c: "投稿スタイル", n: "深夜投稿率（0〜5時）", d: "ランクイン曲のうち深夜に投稿された割合。", v: (s) => s.lateNight, f: F.pct0 },
  { c: "投稿スタイル", n: "朝投稿率（5〜10時）", d: "ランクイン曲のうち朝に投稿された割合。", v: (s) => s.morning, f: F.pct0 },
  { c: "投稿スタイル", n: "夜投稿率（18〜23時）", d: "ランクイン曲のうち夜に投稿された割合。視聴者が多い時間帯。", v: (s) => s.golden, f: F.pct0 },
  { c: "投稿スタイル", n: "金曜日投稿率", d: "ランクイン曲のうち金曜投稿の割合。ボカロ曲は金曜夜投稿が定番。", v: (s) => s.friday, f: F.pct0 },
  { c: "投稿スタイル", n: "週末投稿率", d: "ランクイン曲のうち土日投稿の割合。", v: (s) => s.weekend, f: F.pct0 },
  { c: "投稿スタイル", n: "ボカコレ参加率", d: "直近の曲名に「ボカコレ」を含む割合。イベント参加の多さ。", v: (s) => s.bokakore > 0 ? s.bokakore : null, f: F.pct0 },

  // ===== 使用ボーカル =====
  ...VOCAL_DEFS.map(([vo]) => ({
    c: "使用ボーカル", n: `${vo}楽曲使用率`, d: `直近の曲名から判定した${vo}の使用率。`,
    v: (s) => s.vocalRates && s.vocalRates[vo] > 0 ? s.vocalRates[vo] : null,
    f: F.pct0,
  })),
  { c: "使用ボーカル", n: "マイナーボーカル使用率", d: "主要ボーカル以外（SynthV・CeVIOの新声など）の使用率。", v: (s) => s.vocalN >= 3 ? s.minorRate : null, f: F.pct0 },
  { c: "使用ボーカル", n: "使用ボーカルの種類数", d: "直近の曲で使ったボーカルの種類。", v: (s) => s.harem, f: F.cnt("種") },
  { c: "使用ボーカル", n: "最多使用ボーカルへの集中率", d: "いちばん使うボーカルが全体に占める割合。高いほど一筋。", v: (s) => s.devoted, f: F.pct0 },
  { c: "使用ボーカル", n: "複数ボーカル曲の割合", d: "2種類以上のボーカルが入った曲の割合。", v: (s) => s.duet > 0 ? s.duet : null, f: F.pct0 },

  // ===== 曲名の傾向 =====
  { c: "曲名の傾向", n: "曲名の平均文字数（長い順）", d: "直近の曲名の平均文字数。", v: (s) => s.titleLen, f: F.chars },
  { c: "曲名の傾向", n: "曲名の平均文字数（短い順）", d: "曲名が短い順。", v: (s) => s.titleLen, f: F.chars, asc: true },
  { c: "曲名の傾向", n: "曲名のひらがな率", d: "曲名に占めるひらがなの割合。", v: (s) => s.hira, f: F.pct0 },
  { c: "曲名の傾向", n: "曲名のカタカナ率", d: "曲名に占めるカタカナの割合。", v: (s) => s.kata, f: F.pct0 },
  { c: "曲名の傾向", n: "曲名の漢字率", d: "曲名に占める漢字の割合。", v: (s) => s.kanji, f: F.pct0 },
  { c: "曲名の傾向", n: "曲名の英字率", d: "曲名に占めるアルファベットの割合。", v: (s) => s.latin, f: F.pct0 },
  { c: "曲名の傾向", n: "英語タイトル曲の割合", d: "曲名のほぼ全体が英字の曲の割合。海外リスナー向けの傾向。", v: (s) => s.engTitle > 0 ? s.engTitle : null, f: F.pct0 },
  { c: "曲名の傾向", n: "曲名の【】使用率", d: "曲名に【】を含む割合。ニコニコ動画由来の表記スタイル。", v: (s) => s.brackets, f: F.pct0 },

  // ===== チャンネル情報 =====
  { c: "チャンネル情報", n: "チャンネル運営年数（古い順）", d: "チャンネル開設からの年数。", v: (s) => s.chAge, f: F.years },
  { c: "チャンネル情報", n: "チャンネル運営年数（新しい順）", d: "開設が新しい順。新世代のP。", v: (s) => s.chAge, f: F.years, asc: true },
  { c: "チャンネル情報", n: "「〜P」名義のPの登録者数", d: "名前に「P」が付くP名文化のチャンネルを登録者順で。", v: (s) => s.nameHasP ? s.subs : null, f: F.cnt("人") },
  { c: "チャンネル情報", n: "最終投稿からの経過日数", d: "最後の投稿からどれだけ経っているか。", v: (s) => s.ghost, f: F.days },

  // ===== ランクイン実績 =====
  { c: "ランクイン実績", n: "週間ランクイン曲数", d: "今週のランキングに入っている曲数。", v: (s) => s.wIn || null, f: F.cnt("曲") },
  { c: "ランクイン実績", n: "月間ランクイン曲数", d: "今月のランキングに入っている曲数。", v: (s) => s.mIn || null, f: F.cnt("曲") },
  { c: "ランクイン実績", n: "年間ランクイン曲数", d: "年間ランキングに入っている曲数。", v: (s) => s.yIn || null, f: F.cnt("曲") },
  { c: "ランクイン実績", n: "全期間ランクイン曲数", d: "週・月・年あわせたランクイン曲数（重複なし）。", v: (s) => s.allIn || null, f: F.cnt("曲") },
  { c: "ランクイン実績", n: "週間最高順位", d: "今週のランキングでの最高順位。", v: (s) => s.wBest, f: F.rank, asc: true },
  { c: "ランクイン実績", n: "月間最高順位", d: "今月のランキングでの最高順位。", v: (s) => s.mBest, f: F.rank, asc: true },
  { c: "ランクイン実績", n: "年間最高順位", d: "年間ランキングでの最高順位。", v: (s) => s.yBest, f: F.rank, asc: true },
  { c: "ランクイン実績", n: "ランクイン期間数（週・月・年）", d: "週間・月間・年間のうちいくつにランクインしているか。", v: (s) => s.crown || null, f: F.cnt("期間") },

  // ===== その他の分析 =====
  { c: "その他の分析", n: "総合偏差値", d: "登録者数・高評価率・成長率・再生数中央値のパーセンタイル平均から算出した総合指標。", v: (s) => s.deviation, f: F.dev },
  { c: "その他の分析", n: "直近動画の総視聴時間", d: "直近30本の再生数×動画の長さの合計（時間換算）。", v: (s) => s.watchHours, f: F.hours },
  { c: "その他の分析", n: "日次再生数の最高値", d: "ランクイン曲のうち「1日あたり再生数」が最大の曲の値。", v: (s) => s.addict, f: F.cnt("回/日") },
  { c: "その他の分析", n: "最大ヒット曲への再生集中度", d: "直近の総再生数のうち最大ヒット1曲が占める割合。", v: (s) => s.repDep, f: F.pct0 },
  { c: "その他の分析", n: "小規模チャンネルの実力上位", d: "登録者5万人未満のチャンネルを平均VocaScore順で。次にくるP候補。", v: (s) => s.darkhorse, f: F.score },
];

// 軸名・説明の翻訳を適用（AXES_T は i18n.js で定義、AXESと同順）
if (LANG !== "ja" && typeof AXES_T !== "undefined" && AXES_T[LANG]) {
  AXES.forEach((a, i) => {
    const tr = AXES_T[LANG][i];
    if (tr) { a.n = tr[0]; a.d = tr[1]; }
  });
}

const CATEGORIES = [...new Set(AXES.map((a) => a.c))];
const CAT_ICONS = {
  "基本データ": "📊", "実力・評価": "💪", "勢い・効率": "🚀", "投稿スタイル": "📅",
  "使用ボーカル": "🎤", "曲名の傾向": "✏️", "チャンネル情報": "📺",
  "ランクイン実績": "🏆", "その他の分析": "🔍",
};

/* ---------- チャンネル詳細パネル ---------- */
function ensurePanel() {
  if (document.getElementById("pPanel")) return;
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="p-panel-overlay" id="pPanelOverlay"></div>
    <aside class="p-panel" id="pPanel" aria-label="チャンネル詳細">
      <button class="p-panel-close" id="pPanelClose" aria-label="閉じる">✕</button>
      <div class="p-panel-body" id="pPanelBody"></div>
    </aside>`;
  document.body.append(...wrap.children);
  document.getElementById("pPanelOverlay").addEventListener("click", closePanel);
  document.getElementById("pPanelClose").addEventListener("click", closePanel);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });
}
function closePanel() {
  document.getElementById("pPanel")?.classList.remove("open");
  document.getElementById("pPanelOverlay")?.classList.remove("open");
}

function panelStat(label, value) {
  return value != null && value !== ""
    ? `<div class="pp-stat"><span class="pp-label">${label}</span><span class="pp-val">${value}</span></div>` : "";
}

window.openProducerPanel = async function (channelId) {
  ensurePanel();
  if (!STATS) buildStats();
  const s = STATS.get(channelId);
  const p = s ? s.p : PRODUCERS.find((x) => x.channelId === channelId);
  if (!p) return;

  // 先にパネルを開いて読み込み中表示
  const body = document.getElementById("pPanelBody");
  body.innerHTML = `<div class="empty-msg">${esc(t("loading"))}</div>`;
  document.getElementById("pPanel").classList.add("open");
  document.getElementById("pPanelOverlay").classList.add("open");

  // 全ランキング（全期間含む）からVocaScore辞書を作る
  const scoreById = {};
  for (const k of ["weekly", "monthly", "yearly", "alltime"]) {
    (RANKINGS[k] || []).forEach((v) => {
      if (v.score != null) scoreById[v.videoId] = { score: v.score, grade: v.scoreGrade };
    });
  }

  // このチャンネルの全ボカロ楽曲リスト（収集済みファイル → なければ手持ちデータ）
  let songs = null, isFull = false;
  try {
    const r = await fetch(`data/channels/${encodeURIComponent(channelId)}.json`);
    if (r.ok) {
      const j = await r.json();
      if (j.videos && j.videos.length) { songs = j.videos.slice(); isFull = true; }
    }
  } catch (e) { /* ファイル未生成なら手持ちデータで表示 */ }

  const byId = new Map((songs || []).map((v) => [v.id, v]));
  // ランクイン曲・直近動画で不足分を補完
  (s?.rankedAll || []).forEach((v) => {
    if (!byId.has(v.videoId)) {
      const o = { id: v.videoId, t: v.title, v: v.views };
      byId.set(v.videoId, o);
      (songs ||= []).push(o);
    }
  });
  const recPool = (p.recent || []).filter((r) => r.id);
  const recFlagged = recPool.filter((r) => r.voca || isVocaloTitle(r.t));
  const recUse = (recFlagged.length === 0
    || recFlagged.length / Math.max(recPool.length, 1) >= 0.3) ? recPool : recFlagged;
  recUse.forEach((r) => {
    if (!byId.has(r.id)) {
      byId.set(r.id, r);
      (songs ||= []).push(r);
    }
  });
  songs = (songs || []).sort((a, b) => (b.v || 0) - (a.v || 0));

  const joined = p.joined ? p.joined.replaceAll("-", "/") : null;
  body.innerHTML = `
    <div class="pp-head">
      <img class="pp-avatar" src="${esc(p.thumbnail || "")}" alt="" onerror="this.style.visibility='hidden'">
      <div>
        <div class="pp-name">${esc(p.name)}</div>
        ${p.handle ? `<div class="pp-handle">${esc(p.handle)}</div>` : ""}
        <a class="pp-yt" href="https://www.youtube.com/channel/${esc(p.channelId)}" target="_blank" rel="noopener noreferrer">${esc(t("pp.open"))}</a>
        <a class="pp-yt pp-cd" href="https://www.amazon.co.jp/s?k=${encodeURIComponent((p.name || "") + " CD")}&tag=${AMAZON_TAG}" target="_blank" rel="noopener noreferrer sponsored">💿 ${esc(t("pp.cd"))}</a>
      </div>
    </div>
    <div class="pp-stats">
      ${panelStat(t("pp.subs"), p.subscribers ? fmtNum(p.subscribers) + tUnit("人") : null)}
      ${panelStat(t("pp.totalViews"), p.totalViews ? fmtNum(p.totalViews) + tUnit("回") : null)}
      ${panelStat(t("pp.songs"), songs.length ? songs.length + tUnit("曲") : null)}
      ${panelStat(t("pp.joined"), joined)}
      ${panelStat(t("pp.freq"), s?.perMonth ? s.perMonth.toFixed(1) + tUnit("本/月") : null)}
      ${panelStat(t("pp.median"), s?.medV ? fmtNum(Math.round(s.medV)) + tUnit("回") : null)}
      ${panelStat(t("pp.avgScore"), s?.avgScore ? s.avgScore.toFixed(1) + tUnit("点") : null)}
      ${panelStat(t("pp.avgLike"), s?.avgLikeRatio ? s.avgLikeRatio.toFixed(1) + "%" : null)}
    </div>
    ${p.description ? `<p class="pp-desc">${esc(p.description)}</p>` : ""}
    <h4 class="pp-h4">${esc(tf("pp.h4", { n: songs.length }))}</h4>
    ${isFull ? "" : `<p class="pp-note">${esc(t("pp.note"))}</p>`}
    <ol class="pp-top5">
      ${songs.map((v, i) => {
        const sc = scoreById[v.id];
        return `
        <li>
          <span class="pp-rank">${i + 1}</span>
          <button class="rank-thumb pp-thumb" data-video-id="${esc(v.id)}" aria-label="再生">
            <img src="https://i.ytimg.com/vi/${esc(v.id)}/mqdefault.jpg" alt="" loading="lazy">
            <span class="play-overlay">▶</span>
          </button>
          <div class="pp-song">
            <a href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener noreferrer">${esc(v.t)}</a>
            <div class="pp-song-meta">▶ ${v.v != null ? fmtNum(v.v) + tUnit("回") : "—"}${sc ? ` ・ VocaScore ${sc.score} (${esc(sc.grade)})` : ""}</div>
          </div>
        </li>`;
      }).join("") || `<li>${esc(t("pp.nosongs"))}</li>`}
    </ol>`;
  attachPlayHandlers(body);
};

/* ---------- ランキング UI ---------- */
let currentCat = "すべて";
let currentAxis = 0;

function renderAxisOptions() {
  const sel = document.getElementById("axisSelect");
  sel.innerHTML = AXES
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => currentCat === "すべて" || a.c === currentCat)
    .map(({ a, i }) => `<option value="${i}" ${i === currentAxis ? "selected" : ""}>${CAT_ICONS[a.c]} ${esc(a.n)}</option>`)
    .join("");
}

function renderCats() {
  const el = document.getElementById("axisCats");
  el.innerHTML = ["すべて", ...CATEGORIES]
    .map((c) => `<button class="axis-cat ${c === currentCat ? "active" : ""}" data-cat="${esc(c)}">${c === "すべて" ? esc(t("p.all")) : (CAT_ICONS[c] + " " + esc(tCat(c)))}</button>`)
    .join("");
  el.querySelectorAll(".axis-cat").forEach((b) => {
    b.addEventListener("click", () => {
      currentCat = b.dataset.cat;
      const first = AXES.findIndex((a) => currentCat === "すべて" || a.c === currentCat);
      if (!(currentCat === "すべて" || AXES[currentAxis].c === currentCat)) currentAxis = first;
      renderCats(); renderAxisOptions(); renderList();
    });
  });
}

function renderList() {
  const axis = AXES[currentAxis];
  document.getElementById("axisDesc").innerHTML =
    `${CAT_ICONS[axis.c]} <strong>${esc(axis.n)}</strong> — ${esc(axis.d)}`;

  const rows = [];
  for (const s of STATS.values()) {
    const val = axis.v(s);
    if (val == null || Number.isNaN(val) || !isFinite(val)) continue;
    rows.push({ s, val });
  }
  rows.sort((a, b) => axis.asc ? a.val - b.val : b.val - a.val);

  const el = document.getElementById("pRankList");
  if (rows.length < 3) {
    el.innerHTML = `<div class="empty-msg">${esc(t("p.empty"))}</div>`;
    return;
  }
  el.innerHTML = rows.slice(0, 30).map(({ s, val }, i) => {
    const p = s.p;
    const rankCls = i < 3 ? ` r${i + 1}` : "";
    return `<li class="p-rank-item">
      <div class="rank-num${rankCls}">${i + 1}</div>
      <img class="p-avatar" src="${esc(p.thumbnail || "")}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
      <div>
        <div class="p-name"><button class="p-name-btn" data-channel="${esc(p.channelId)}">${esc(p.name)}</button></div>
        <div class="p-sub">${esc(tf("u.subs", { n: fmtNum(p.subscribers) }))}${p.handle ? " ・ " + esc(p.handle) : ""}</div>
      </div>
      <div class="p-value">${axis.f(val)}<small>${esc(axis.n)}</small></div>
    </li>`;
  }).join("");
  // 行のどこをクリックしても詳細パネルを開く
  el.querySelectorAll(".p-rank-item").forEach((row) => {
    const cid = row.querySelector(".p-name-btn")?.dataset.channel;
    if (cid) row.addEventListener("click", () => window.openProducerPanel(cid));
  });
}

window.renderPRanking = function () {
  if (!STATS) buildStats();
  renderCats();
  renderAxisOptions();
  renderList();

  document.getElementById("axisSelect").addEventListener("change", (e) => {
    currentAxis = Number(e.target.value);
    renderList();
  });
  document.getElementById("axisRandom").addEventListener("click", () => {
    const pool = AXES.map((a, i) => i)
      .filter((i) => currentCat === "すべて" || AXES[i].c === currentCat);
    currentAxis = pool[Math.floor(Math.random() * pool.length)];
    renderAxisOptions();
    renderList();
  });
};

})();
