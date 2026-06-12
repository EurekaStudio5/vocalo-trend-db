/* ===== ボカロトレンドDB アプリ ===== */
"use strict";

let RANKINGS = { weekly: [], monthly: [], yearly: [], alltime: [] };
let PERIOD = "weekly";
let PRODUCERS = [];
let PRODUCER_IDS = new Set(); // 名鑑に載っているPのチャンネルID（P名クリック→詳細パネル用）

const PERIOD_LABEL = { weekly: "週間", monthly: "月間", yearly: "年間", alltime: "全期間" };
const currentVideos = () => RANKINGS[PERIOD] || [];
const yearlyVideos = () => RANKINGS.yearly.length ? RANKINGS.yearly : RANKINGS.monthly;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* ---------- ユーティリティ ---------- */
function fmtNum(n) {
  if (n == null) return "—";
  if (LANG === "en") {
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return n.toLocaleString("en-US");
  }
  const oku = LANG === "zh" ? "亿" : LANG === "ko" ? "억" : "億";
  const man = LANG === "ko" ? "만" : "万";
  if (n >= 100000000) return (n / 100000000).toFixed(1).replace(/\.0$/, "") + oku;
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + man;
  return n.toLocaleString("ja-JP");
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- タブ切替 ---------- */
let analysisRendered = false;
let prankingRendered = false;
let producersRendered = false;
$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    window.scrollTo({ top: 0 });
    // 非表示状態で描画するとチャートのサイズが0になるため、初回表示時に描画する
    if (btn.dataset.tab === "analysis" && !analysisRendered && yearlyVideos().length) {
      analysisRendered = true;
      renderAnalysis();
    }
    if (btn.dataset.tab === "pranking" && !prankingRendered && PRODUCERS.length) {
      prankingRendered = true;
      if (window.renderPRanking) window.renderPRanking();
    }
    // 名鑑も初回表示時に描画（起動時に410枚のカードDOMを作らない）
    if (btn.dataset.tab === "producers" && !producersRendered && PRODUCERS.length) {
      producersRendered = true;
      renderProducers();
    }
  });
});

/* ---------- 期間切替 ---------- */
$$(".period-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".period-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    PERIOD = btn.dataset.period;
    $("#rankingTitle").innerHTML = `<span class="hl">${esc(t("rank." + PERIOD))}</span>`;
    renderRanking();
  });
});

/* ---------- 動画埋め込み（クリックで再生） ---------- */
function attachPlayHandlers(root) {
  root.querySelectorAll(".rank-thumb").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.dataset.videoId;
      if (!/^[\w-]{8,16}$/.test(id)) return; // YouTube動画ID形式のみ埋め込み許可
      el.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0"
        title="YouTube video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowfullscreen></iframe>`;
    }, { once: true });
  });
}

/* ---------- ランキング描画 ---------- */
function scoreBadgeHTML(v) {
  if (v.score == null) return "";
  const p = v.scoreParts || {};
  const tip = [
    `VocaScore ${v.score} (${v.scoreGrade})`,
    p.like != null ? `${t("s.like")} ${p.like}/40（${t("s.likeRatio")} ${p.likeRatio}%）` : t("s.miss.like"),
    p.reach != null ? `${t("s.reach")} ${p.reach}/30` : t("s.miss.reach"),
    p.momentum != null ? `${t("s.momentum")} ${p.momentum}/30` : `${t("s.momentum")} —`,
    t("s.note"),
  ].join("\n");
  return `<div class="score-badge grade-${esc(v.scoreGrade)}" title="${esc(tip)}">
    <span class="score-label">VocaScore</span>
    <span class="score-num">${v.score}</span>
    <span class="score-grade">${esc(v.scoreGrade)}</span>
  </div>`;
}

function videoItemHTML(v, rank) {
  const rankCls = rank <= 3 ? ` r${rank}` : "";
  // 名鑑に載っているPなら名前クリックで詳細パネル、未登録ならYouTubeリンク
  const chLink = PRODUCER_IDS.has(v.channelId)
    ? `<button class="channel-link channel-open" data-channel="${esc(v.channelId)}">👤 ${esc(v.channelName)}</button>`
    : `<a class="channel-link" href="https://www.youtube.com/channel/${esc(v.channelId)}" target="_blank" rel="noopener noreferrer">👤 ${esc(v.channelName)}</a>`;
  // 上位2件はファーストビューのLCP要素なので優先読み込み
  const imgAttr = rank <= 2 ? 'fetchpriority="high"' : 'loading="lazy"';
  return `<li class="rank-item">
    <div class="rank-num${rankCls}">${rank}</div>
    <button class="rank-thumb" data-video-id="${esc(v.videoId)}" aria-label="再生">
      <img src="${esc(v.thumbnail)}" alt="" ${imgAttr}>
      <span class="play-overlay">▶</span>
      ${v.length ? `<span class="video-length">${esc(v.length)}</span>` : ""}
    </button>
    <div class="rank-info">
      <div class="rank-title"><a href="https://www.youtube.com/watch?v=${esc(v.videoId)}" target="_blank" rel="noopener noreferrer">${esc(v.title)}</a></div>
      <div class="rank-meta">
        <span class="views">▶ ${fmtNum(v.views)}${tUnit("回")}</span>
        <span class="vpd">🔥 ${fmtNum(v.viewsPerDay)}${tUnit("回/日")}</span>
        <span>${LANG === "ja" ? esc(v.publishedText) : esc(relTime(v.daysAgo))}</span>
        ${chLink}
        <a class="share-x" target="_blank" rel="noopener noreferrer" title="X (Twitter)"
           href="https://twitter.com/intent/tweet?text=${encodeURIComponent(`${rankLabel(rank)} ${v.title} #ボカロトレンドDB`)}&url=${encodeURIComponent(`https://www.youtube.com/watch?v=${v.videoId}`)}">𝕏</a>
      </div>
      <span class="vocal-badge">🎤 ${esc(tVocal(v.vocal))}</span>
    </div>
    ${scoreBadgeHTML(v)}
  </li>`;
}

/* P名クリック→詳細パネル、スコアバッジタップ→内訳ポップ */
function attachItemHandlers(root) {
  root.querySelectorAll(".channel-open").forEach((b) => {
    b.addEventListener("click", () =>
      window.openProducerPanel && window.openProducerPanel(b.dataset.channel));
  });
  root.querySelectorAll(".score-badge").forEach((b) => {
    b.addEventListener("click", (e) => {
      e.stopPropagation();
      const old = document.querySelector(".score-pop");
      const mine = old && old.dataset.for === (b.dataset.pop ||= String(Math.random()));
      if (old) old.remove();
      if (mine) return;
      const pop = document.createElement("div");
      pop.className = "score-pop";
      pop.dataset.for = b.dataset.pop;
      pop.textContent = b.title;
      b.parentElement.appendChild(pop);
    });
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".score-badge")) document.querySelector(".score-pop")?.remove();
});

function renderRanking() {
  const vocal = $("#vocalFilter").value;
  const sort = $("#sortMode").value;
  const q = $("#searchBox").value.trim().toLowerCase();

  let list = currentVideos().slice();
  if (vocal) list = list.filter((v) => v.vocal === vocal);
  if (q) list = list.filter((v) =>
    v.title.toLowerCase().includes(q) || v.channelName.toLowerCase().includes(q));

  if (sort === "views") list.sort((a, b) => (b.views || 0) - (a.views || 0));
  else if (sort === "score") list.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
  else if (sort === "viewsPerDay") list.sort((a, b) => (b.viewsPerDay || 0) - (a.viewsPerDay || 0));
  else if (sort === "newest") list.sort((a, b) => (a.daysAgo ?? 9999) - (b.daysAgo ?? 9999));

  const el = $("#rankingList");
  if (!list.length) {
    el.innerHTML = `<div class="empty-msg">${esc(t("empty.videos"))}</div>`;
    return;
  }
  el.innerHTML = list.slice(0, 100).map((v, i) => videoItemHTML(v, i + 1)).join("");
  attachPlayHandlers(el);
  attachItemHandlers(el);
}

/* ---------- トレンド分析 ---------- */
const chartDefaults = {
  color: "#6f6885",
  borderColor: "rgba(43,36,64,.12)",
};

function makeChart(canvasId, type, labels, data, label, color) {
  // Chart.js は defer 読み込みのため、初回利用時にデフォルトを設定する
  if (!makeChart._init && window.Chart) {
    Chart.defaults.font.family = '"Zen Maru Gothic", sans-serif';
    Chart.defaults.font.weight = 700;
    makeChart._init = true;
  }
  const cv = $(canvasId);
  // ラベル数に応じて高さを確保し、ラベルの自動間引きで文字が消えないようにする
  cv.parentNode.style.height = Math.max(200, labels.length * 26 + 60) + "px";
  new Chart(cv, {
    type,
    data: {
      labels,
      datasets: [{
        label,
        data,
        backgroundColor: color + "55",
        borderColor: color,
        borderWidth: 1.5,
      }],
    },
    options: {
      indexAxis: type === "bar" ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: type === "doughnut" ? {} : {
        x: {
          ticks: { color: chartDefaults.color, callback: (v) => fmtNum(v) },
          grid: { color: chartDefaults.borderColor },
        },
        y: {
          ticks: { color: chartDefaults.color, autoSkip: false },
          grid: { display: false },
        },
      },
    },
  });
}

function lengthBucket(lenStr) {
  if (!lenStr) return null;
  const parts = lenStr.split(":").map(Number);
  const secs = parts.reduce((a, p) => a * 60 + p, 0);
  if (secs < 90) return "〜1:30";
  if (secs < 150) return "1:30〜2:30";
  if (secs < 210) return "2:30〜3:30";
  if (secs < 270) return "3:30〜4:30";
  return "4:30〜";
}

const STOPWORDS = new Set([
  "feat", "ft", "official", "video", "music", "mv", "オリジナル", "オリジナル曲",
  "初音ミク", "重音テト", "可不", "gumi", "鏡音リン", "鏡音レン", "巡音ルカ",
  "vocaloid", "ボカロ", "ボーカロイド", "synthesizerv", "cevio", "miku", "hatsune",
  "テト", "ミク", "kafu", "teto", "flower", "ia",
]);

function topWords(videos, n) {
  const counts = {};
  videos.forEach((v) => {
    // 記号で分割してワード抽出
    v.title.split(/[\s\/\\|【】\[\]()（）「」『』‐\-―〜~・,.，。!！?？:：;；"'`#＃×☆★]+/)
      .map((w) => w.trim().toLowerCase())
      .filter((w) => w.length >= 2 && w.length <= 12 && !STOPWORDS.has(w) && !/^[\d.]+$/.test(w))
      .forEach((w) => { counts[w] = (counts[w] || 0) + 1; });
  });
  return Object.entries(counts)
    .filter(([, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

function renderAnalysis() {
  const VIDEOS = yearlyVideos(); // 分析対象は年間ランキング
  const subsBy = {};
  PRODUCERS.forEach((p) => { subsBy[p.channelId] = p.subscribers || 0; });

  // --- 共通集計 ---
  const totalViews = VIDEOS.reduce((a, v) => a + (v.views || 0), 0);

  const vocalViews = {};
  VIDEOS.forEach((v) => {
    (vocalViews[v.vocal] ||= { sum: 0, n: 0 });
    vocalViews[v.vocal].sum += v.views || 0;
    vocalViews[v.vocal].n++;
  });
  const avgViewsByVocal = Object.entries(vocalViews)
    .filter(([, o]) => o.n >= 3)
    .map(([k, o]) => [k, Math.round(o.sum / o.n)])
    .sort((a, b) => b[1] - a[1]);
  const bestVocal = avgViewsByVocal[0];

  const lengths = {};
  VIDEOS.forEach((v) => {
    const b = lengthBucket(v.length);
    if (b) lengths[b] = (lengths[b] || 0) + 1;
  });
  const bestLength = Object.entries(lengths).sort((a, b) => b[1] - a[1])[0];

  // 曜日×時間帯ヒートマップ（投稿日時が取れている曲ベース）
  const dated = VIDEOS
    .map((v) => v.publishDate ? { d: new Date(v.publishDate), v } : null)
    .filter((x) => x && !isNaN(x.d));
  const DOW = t("dow");
  const HOURS = [[0, 6], [6, 12], [12, 15], [15, 18], [18, 21], [21, 24]];
  const heat = DOW.map(() => HOURS.map(() => ({ sum: 0, n: 0 })));
  dated.forEach(({ d, v }) => {
    const r = (d.getDay() + 6) % 7;
    const c = HOURS.findIndex(([lo, hi]) => d.getHours() >= lo && d.getHours() < hi);
    if (c >= 0) { heat[r][c].sum += v.views || 0; heat[r][c].n++; }
  });
  let best = null;
  heat.forEach((row, ri) => row.forEach((cell, ci) => {
    if (cell.n >= 3) {
      const avg = cell.sum / cell.n;
      if (!best || avg > best.avg) best = { ri, ci, avg, n: cell.n };
    }
  }));
  const slotLabel = best
    ? `${DOW[best.ri]}${LANG === "ja" ? "曜" : ""} ${tf("hour.fmt", { a: HOURS[best.ci][0], b: HOURS[best.ci][1] })}`
    : "—";

  // 高評価率ベンチマーク
  const ratios = VIDEOS.map((v) => v.scoreParts?.likeRatio)
    .filter((x) => x != null).sort((a, b) => a - b);
  const pctl = (p) => ratios.length
    ? ratios[Math.min(ratios.length - 1, Math.floor(ratios.length * p))] : null;
  const likeMed = pctl(0.5), likeP90 = pctl(0.9);

  // 下剋上率（登録者数が分かるチャンネルの曲のみ）
  const known = VIDEOS.filter((v) => subsBy[v.channelId]);
  const upset = known.length
    ? Math.round(known.filter((v) => subsBy[v.channelId] < 50000).length / known.length * 100)
    : null;

  // ボーカル別シェアの四半期推移 ＆ 急上昇ボーカル
  const qOf = (v) => v.daysAgo == null ? null : Math.min(3, Math.floor(v.daysAgo / 91.3));
  const counts = {};
  VIDEOS.forEach((v) => { counts[v.vocal] = (counts[v.vocal] || 0) + 1; });
  const topVocalNames = Object.entries(counts).sort((a, b) => b[1] - a[1])
    .slice(0, 5).map(([k]) => k);
  const qTotals = [0, 0, 0, 0];
  const qVocal = {};
  VIDEOS.forEach((v) => {
    const q = qOf(v);
    if (q == null) return;
    qTotals[q]++;
    const key = topVocalNames.includes(v.vocal) ? v.vocal : "__other";
    (qVocal[key] ||= [0, 0, 0, 0])[q]++;
  });
  const share = (key, q) => qTotals[q] ? (qVocal[key]?.[q] || 0) / qTotals[q] * 100 : 0;
  let rising = null;
  topVocalNames.forEach((name) => {
    if (name === "その他") return; // 雑多枠は急上昇の対象にしない
    if ((qVocal[name]?.[0] || 0) < 2) return;
    const delta = share(name, 0) - share(name, 1);
    if (!rising || delta > rising.delta) rising = { name, delta };
  });
  if (rising && rising.delta < 0.5) rising = null; // 明確な上昇がないときは出さない

  // --- インサイトカード ---
  $("#insights").innerHTML = `
    <div class="insight-card">
      <div class="label">${esc(t("i.totalViews"))}</div>
      <div class="value">${fmtNum(totalViews)}${tUnit("回")}</div>
      <div class="sub">${esc(tf("i.totalViews.sub", { n: VIDEOS.length }))}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.bestSlot"))}</div>
      <div class="value">${esc(slotLabel)}</div>
      <div class="sub">${best ? esc(tf("i.bestSlot.sub", { n: fmtNum(Math.round(best.avg)) })) : esc(t("i.nodata"))}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.upset"))}</div>
      <div class="value">${upset != null ? upset + "%" : "—"}</div>
      <div class="sub">${esc(t("i.upset.sub"))}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.likeBench"))}</div>
      <div class="value">${likeMed != null ? likeMed.toFixed(1) + "%" : "—"}</div>
      <div class="sub">${likeP90 != null ? esc(tf("i.likeBench.sub", { p: likeP90.toFixed(1) })) : ""}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.risingVocal"))}</div>
      <div class="value">${rising ? esc(tVocal(rising.name)) : "—"}</div>
      <div class="sub">${rising ? esc(tf("i.risingVocal.sub", { n: rising.delta.toFixed(1) })) : esc(t("i.nodata"))}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.bestVocal"))}</div>
      <div class="value">${esc(tVocal(bestVocal?.[0] ?? "—"))}</div>
      <div class="sub">${esc(tf("i.bestVocal.sub", { n: fmtNum(bestVocal?.[1]) }))}</div>
    </div>
    <div class="insight-card">
      <div class="label">${esc(t("i.bestLen"))}</div>
      <div class="value">${esc(bestLength?.[0] ?? "—")}</div>
      <div class="sub">${esc(t("i.bestLen.sub"))}</div>
    </div>`;

  // --- ① 曜日×時間帯ヒートマップ ---
  const maxAvg = Math.max(1, ...heat.flat().filter((c) => c.n >= 2).map((c) => c.sum / c.n));
  let hm = `<div class="hm-row hm-head"><span></span>${HOURS.map(([a, b]) =>
    `<span>${a}-${b}</span>`).join("")}</div>`;
  heat.forEach((row, ri) => {
    hm += `<div class="hm-row"><span class="hm-lab">${esc(DOW[ri])}</span>`;
    row.forEach((cell) => {
      if (cell.n >= 2) {
        const avg = cell.sum / cell.n;
        const alpha = (0.08 + (avg / maxAvg) * 0.85).toFixed(2);
        hm += `<div class="hm-cell" style="background:rgba(0,184,169,${alpha})" title="${fmtNum(Math.round(avg))}${tUnit("回")} / ${cell.n}${tUnit("曲")}">${fmtNum(Math.round(avg))}</div>`;
      } else {
        hm += `<div class="hm-cell hm-empty">${esc(t("heat.few"))}</div>`;
      }
    });
    hm += `</div>`;
  });
  $("#heatmapBox").innerHTML = hm;

  // --- ② ボーカル別シェアの推移（四半期・新しい順を右へ） ---
  const EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const mName = (m) => LANG === "en" ? EN_MONTHS[m] : tf("month.fmt", { m: m + 1 });
  const curMonth = new Date().getMonth();
  const qSep = LANG === "en" ? "–" : "〜";
  const qLabels = [3, 2, 1, 0].map((q) => {
    const em = ((curMonth - 3 * q) % 12 + 12) % 12;
    const sm = (em - 2 + 12) % 12;
    return `${mName(sm)}${qSep}${mName(em)}`;
  });
  const SHARE_COLORS = ["#00b8a9", "#ff6fa5", "#e5b800", "#7c6ff0", "#378add", "#b4b2a9"];
  const shareKeys = [...topVocalNames, "__other"];
  customChart("#chartVocalShare", 280, {
    type: "bar",
    data: {
      labels: qLabels,
      datasets: shareKeys.map((key, i) => ({
        label: key === "__other" ? tVocal("その他") : tVocal(key),
        data: [3, 2, 1, 0].map((q) => Math.round(share(key, q) * 10) / 10),
        backgroundColor: SHARE_COLORS[i] + "cc",
      })),
    },
    options: {
      plugins: { legend: { display: true, position: "bottom", labels: { color: chartDefaults.color, boxWidth: 12 } } },
      scales: {
        x: { stacked: true, ticks: { color: chartDefaults.color }, grid: { display: false } },
        y: { stacked: true, max: 100, ticks: { color: chartDefaults.color, callback: (v) => v + "%" }, grid: { color: chartDefaults.borderColor } },
      },
    },
  });

  // --- ③ チャンネル規模別ランクイン曲数 ---
  const BANDS = [[0, 1e4], [1e4, 5e4], [5e4, 2e5], [2e5, 1e6], [1e6, Infinity]];
  const bandLabels = [
    `〜${fmtNum(1e4)}`, `${fmtNum(1e4)}〜${fmtNum(5e4)}`, `${fmtNum(5e4)}〜${fmtNum(2e5)}`,
    `${fmtNum(2e5)}〜${fmtNum(1e6)}`, `${fmtNum(1e6)}+`,
  ];
  const bandCounts = BANDS.map(([lo, hi]) =>
    known.filter((v) => subsBy[v.channelId] >= lo && subsBy[v.channelId] < hi).length);
  makeChart("#chartChSize", "bar", bandLabels, bandCounts, t("c.songs"), "#ff6fa5");

  // --- ④ 曲の長さ×再生数（散布図・対数軸） ---
  const pts = VIDEOS
    .filter((v) => v.length && v.views)
    .map((v) => {
      const parts = v.length.split(":").map(Number);
      const secs = parts.reduce((a, p) => a * 60 + p, 0);
      return { x: Math.round(secs / 6) / 10, y: v.views };
    })
    .filter((p) => p.x >= 0.5 && p.x <= 12);
  customChart("#chartLenScatter", 260, {
    type: "scatter",
    data: { datasets: [{ data: pts, backgroundColor: "#00b8a9aa", pointRadius: 4 }] },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: t("c.minutes"), color: chartDefaults.color },
             ticks: { color: chartDefaults.color }, grid: { color: chartDefaults.borderColor } },
        y: { type: "logarithmic", ticks: { color: chartDefaults.color, callback: (v) => fmtNum(v) },
             grid: { color: chartDefaults.borderColor } },
      },
    },
  });

  // --- ⑤ タイトル文字数別 平均再生数 ---
  const TB = [[0, 10], [11, 20], [21, 35], [36, 999]];
  const tbLabels = TB.map(([a, b]) => b === 999 ? `${a}${tUnit("文字")}+` : `${a}〜${b}${tUnit("文字")}`);
  const tbData = TB.map(([a, b]) => {
    const g = VIDEOS.filter((v) => v.title.length >= a && v.title.length <= b);
    return g.length >= 3 ? Math.round(g.reduce((s, v) => s + (v.views || 0), 0) / g.length) : 0;
  });
  makeChart("#chartTitleLen", "bar", tbLabels, tbData, t("c.avgViews"), "#e5b800");

  // --- ⑥ 高評価率の分布 ---
  const histLabels = [];
  const histData = [];
  for (let i = 0; i < 10; i++) {
    histLabels.push(`${i}-${i + 1}%`);
    histData.push(ratios.filter((r) => r >= i && r < i + 1).length);
  }
  histLabels.push("10%+");
  histData.push(ratios.filter((r) => r >= 10).length);
  makeChart("#chartLikeHist", "bar", histLabels, histData, t("c.songs"), "#7c6ff0");

  // --- ⑦⑧ ボーカル別 平均再生数 / 平均VocaScore ---
  makeChart("#chartVocalViews", "bar", avgViewsByVocal.map((x) => tVocal(x[0])),
    avgViewsByVocal.map((x) => x[1]), t("c.avgViews"), "#ff6fa5");
  const vsAgg = {};
  VIDEOS.forEach((v) => {
    if (v.score == null) return;
    (vsAgg[v.vocal] ||= []).push(v.score);
  });
  const vocalScores = Object.entries(vsAgg)
    .filter(([, a]) => a.length >= 3)
    .map(([k, a]) => [k, a.reduce((x, y) => x + y, 0) / a.length])
    .sort((a, b) => b[1] - a[1]);
  makeChart("#chartVocalScore", "bar", vocalScores.map((x) => tVocal(x[0])),
    vocalScores.map((x) => Math.round(x[1] * 10) / 10), t("c.avgScore"), "#7c6ff0");

  // --- ⑨ 月別ランクイン曲数 ---
  const monthCounts = Array(12).fill(0);
  VIDEOS.forEach((v) => {
    if (v.daysAgo == null) return;
    const dt = new Date(Date.now() - v.daysAgo * 86400000);
    monthCounts[dt.getMonth()]++;
  });
  const monthLabels = [], monthData = [];
  for (let k = 11; k >= 0; k--) {
    const m = ((curMonth - k) % 12 + 12) % 12;
    monthLabels.push(mName(m));
    monthData.push(monthCounts[m]);
  }
  makeChart("#chartMonth", "bar", monthLabels, monthData, t("c.songs"), "#e5b800");

  // --- ⑩ タイトル頻出ワード ---
  const words = topWords(VIDEOS, 15);
  makeChart("#chartWords", "bar", words.map((x) => x[0]), words.map((x) => x[1]), t("c.count"), "#7c6ff0");
}

/* 縦軸・積み上げ・散布図用の汎用チャートヘルパー */
function customChart(canvasId, height, config) {
  if (!makeChart._init && window.Chart) {
    Chart.defaults.font.family = '"Zen Maru Gothic", sans-serif';
    Chart.defaults.font.weight = 700;
    makeChart._init = true;
  }
  const cv = $(canvasId);
  cv.parentNode.style.height = height + "px";
  config.options = Object.assign({ responsive: true, maintainAspectRatio: false },
    config.options);
  new Chart(cv, config);
}

/* ---------- ボカロP名鑑 ---------- */
function renderProducers() {
  const sort = $("#producerSort").value;
  const q = $("#producerSearch").value.trim().toLowerCase();
  const trendingOnly = $("#trendingOnly").checked;

  let list = PRODUCERS.slice();
  if (q) list = list.filter((p) => (p.name || "").toLowerCase().includes(q));
  if (trendingOnly) list = list.filter((p) => p.weeklyVideos > 0);

  if (sort === "subscribers") list.sort((a, b) => (b.subscribers || 0) - (a.subscribers || 0));
  else if (sort === "weeklyViews") list.sort((a, b) => (b.weeklyViews || 0) - (a.weeklyViews || 0));
  else list.sort((a, b) => (a.name || "").localeCompare(b.name || "", "ja"));

  const el = $("#producerGrid");
  if (!list.length) {
    el.innerHTML = `<div class="empty-msg">${esc(t("pr.empty"))}</div>`;
    return;
  }
  el.innerHTML = list.map((p) => `
    <div class="producer-card" data-channel="${esc(p.channelId)}">
      <div class="producer-head">
        <img class="producer-avatar" src="${esc(p.thumbnail || "")}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">
        <div>
          <div class="producer-name"><button class="p-name-btn" data-channel="${esc(p.channelId)}">${esc(p.name)}</button></div>
          <div class="producer-subs">${esc(tf("u.subs", { n: fmtNum(p.subscribers) }))}</div>
        </div>
      </div>
      ${p.description ? `<div class="producer-desc">${esc(p.description)}</div>` : ""}
      <div class="producer-stats">
        ${p.weeklyVideos > 0 ? `<span class="stat-chip hot">${esc(tf("pr.chip.ranked", { n: p.weeklyVideos }))}</span>` : ""}
        ${p.weeklyViews > 0 ? `<span class="stat-chip">${esc(tf("pr.chip.views", { n: fmtNum(p.weeklyViews) }))}</span>` : ""}
        ${p.handle ? `<span class="stat-chip">${esc(p.handle)}</span>` : ""}
      </div>
    </div>`).join("");
  // カードのどこをクリックしても詳細パネルを開く（名前ボタンのクリックも内包される）
  el.querySelectorAll(".producer-card").forEach((card) => {
    card.addEventListener("click", () =>
      window.openProducerPanel && window.openProducerPanel(card.dataset.channel));
  });
}

/* ---------- 初期化 ---------- */
async function init() {
  try {
    // 毎日更新されるデータが古いキャッシュで配信されないよう日付でバスティング
    const bust = new Date().toISOString().slice(0, 13);
    const [videosRes, producersRes] = await Promise.all([
      fetch("data/videos.json?d=" + bust),
      fetch("data/producers.json?d=" + bust),
    ]);
    if (!videosRes.ok || !producersRes.ok) throw new Error("data not found");
    const videosData = await videosRes.json();
    const producersData = await producersRes.json();
    RANKINGS = {
      weekly: videosData.weekly || videosData.videos || [],
      monthly: videosData.monthly || [],
      yearly: videosData.yearly || [],
      alltime: videosData.alltime || [],
    };
    PRODUCERS = producersData.producers || [];
    PRODUCER_IDS = new Set(PRODUCERS.map((p) => p.channelId));

    const d = new Date(videosData.updated);
    $("#updatedAt").textContent =
      `${t("updated")}: ${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    $("#rankingTitle").innerHTML = `<span class="hl">${esc(t("rank." + PERIOD))}</span>`;

    // ティッカー（今週のTOP10を流す）
    const top10 = RANKINGS.weekly.slice(0, 10);
    if (top10.length) {
      const items = top10.map((v, i) =>
        `<span><span class="tk-rank">${esc(rankLabel(i + 1))}</span> ${esc(v.title.slice(0, 40))} <span class="tk-views">▶${fmtNum(v.views)}</span></span>`
      ).join("");
      // シームレスループのため2回繰り返す（CSSで-50%移動）
      $("#tickerTrack").innerHTML = items + items;
    }

    // ボーカルフィルタの選択肢を生成（全期間から・一般的な人気順で表示）
    const VOCAL_ORDER = [
      "初音ミク", "重音テト", "GUMI", "鏡音リン・レン", "可不", "flower",
      "巡音ルカ", "IA", "音街ウナ", "歌愛ユキ", "星界", "裏命", "知声",
    ];
    const all = [...RANKINGS.weekly, ...RANKINGS.monthly, ...RANKINGS.yearly, ...RANKINGS.alltime];
    const order = (v) => {
      if (v === "その他") return 999;           // その他は常に最後
      const i = VOCAL_ORDER.indexOf(v);
      return i === -1 ? 500 : i;                // 未知のボーカルは既知の後ろ
    };
    const vocals = [...new Set(all.map((v) => v.vocal))].sort((a, b) => order(a) - order(b));
    $("#vocalFilter").innerHTML =
      `<option value="">${esc(t("filter.allVocals"))}</option>` +
      vocals.map((v) => `<option value="${esc(v)}">${esc(tVocal(v))}</option>`).join("");

    renderRanking();
  } catch (e) {
    console.error(e);
    $("#updatedAt").textContent = "—";
    const isDev = ["localhost", "127.0.0.1", ""].includes(location.hostname);
    $("#rankingList").innerHTML = isDev
      ? `<div class="empty-msg">
        データがまだありません。<br>
        <code>python update_data.py</code> を実行してデータを取得してください。<br>
        （file:// で直接開いている場合は <code>サイトを起動.bat</code> から起動してください）
      </div>`
      : `<div class="empty-msg">${esc(t("error.load"))}<br><br>
        <button class="btn-dice" onclick="location.reload()">${esc(t("error.reload"))}</button>
      </div>`;
  }
}

// 検索欄はデバウンス＋IME変換中スキップ（1キーごとの100件再描画を防ぐ）
function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}
function bindSearch(id, render) {
  const el = document.getElementById(id);
  const run = debounce(render, 200);
  el.addEventListener("input", (e) => { if (!e.isComposing) run(); });
  el.addEventListener("compositionend", render);
}
["vocalFilter", "sortMode"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderRanking));
bindSearch("searchBox", renderRanking);
["producerSort", "trendingOnly"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderProducers));
bindSearch("producerSearch", renderProducers);

init();
