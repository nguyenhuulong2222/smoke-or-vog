/* Smoke or Vog? static demo. Reads only published JSON under ./data/. No API keys. */
"use strict";

const T = {
  en: {
    skip: "Skip to the step-by-step view",
    liveTitle: "What the satellite sees over Hawaiʻi right now",
    replaysTitle: "Replays",
    replaysLede: "Past events run through the same pipeline. They are demonstrations, not current alerts.",
    howTitle: "How it works",
    footWarn: "Satellite estimate, not an official warning. For official vog information see vog.ivhhn.org; for smoke see fire.airnow.gov.",
    credits: 'Data: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> (GOES-West GeoColor, MODIS), NOAA GOES-18 / NESDIS, NASA FIRMS, <a href="https://www.usgs.gov/observatories/hvo">USGS Hawaiian Volcano Observatory</a>, <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0), <a href="https://www.naturalearthdata.com/">Natural Earth</a>, and the <a href="https://kahuola.org">Kahu Ola</a> public API. Health guidance quoted from the Hawaiʻi Interagency Vog Dashboard (IVHHN / Hawaiʻi DOH) and U.S. EPA AirNow.',
    kahuola: 'Made in Hawaiʻi for the Meta Global AI Developer Hackathon. All code built Oct 31–Nov 4, 2026; the only pre-existing input is the <a href="https://kahuola.org">Kahu Ola</a> public API (same author), used read-only as a data source. Island hazard maps: <a href="https://kahuola.org">kahuola.org</a>.',
    v: { wildfire_smoke: "Likely wildfire smoke", vog_kilauea: "Likely vog from Kīlauea", vog_mauna_loa: "Likely vog from Mauna Loa",
         dust: "Likely dust", cloud: "Cloud", uncertain: "Haze seen, source not confirmed", no_plume: "No haze plume detected" },
    tooCloudy: "Too cloudy to see haze clearly",
    liveLabel: "Live", openLive: "Open live run", checkedAgo: (n) => n < 90 ? `last checked ${n} min ago` : `last checked ${Math.round(n / 60)} h ago`,
    clouds: { clear: "clear skies", partly: "partly cloudy", mostly: "mostly cloudy", overcast: "overcast" },
    seeSam: "See SAM in action → Kīlauea replay", seeAlerts: "See alerts in 5 languages → Kīlauea replay",
    noSparkPlume: "Muse Spark found no haze plume in this image, so there is nothing to box.",
    noSamLive: "No plume in this image, so SAM had nothing to segment.",
    confidence: "Confidence",
    scanned: "Satellite image",
    updated: "Checked",
    noLive: "No live scan has been published yet.",
    status: {
      night: "It is night in Hawaiʻi. True-color scans resume after sunrise; showing the last daylight scan.",
      unchanged: "No newer satellite frame yet; showing the latest scan.",
      budget_stop: "Live scanning is paused (demo budget reached). Showing the last scan.",
      error: "The latest scan failed. Showing the last good scan.",
      not_started: "",
      ok: "",
    },
    unconfirmed: "Not confirmed (below 70% or unreliable mask)",
    openSteps: "See how this was decided",
    steps: ["True-color image", "Aerosol signal", "Muse Spark boxes", "SAM masks", "Agent trace", "Verdict and evidence", "Alerts"],
    sAgent: "Muse Spark decides which tools to call and in what order, then classifies. Every evidence line must cite a tool result (E1, E2, …); a verdict that cites nothing is rejected and the fixed classifier is used instead.",
    agentCalls: (n, r) => `${n} tool calls in ${r} rounds`, round: "round", verified: "Every evidence line cites a tool result.", rejectedV: "Agent verdict rejected", fixedVs: "Fixed classifier on the same plumes", agentVs: "Agent",
    noAgent: "No plume in this image, so the agent had nothing to investigate.", agentFixed: "This run used the fixed classifier.", seeAgent: "See the agent at work → Kīlauea replay",
    guidance: "Official guidance (quoted)", guidanceNote: "Health guidance is quoted from official sources. The AI only selects lines; it does not write health advice.",
    verbatim: "verbatim", translationLabel: "translation of official guidance, machine-translated", reviewedLabel: "translation of official guidance, reviewed",
    newWorkTitle: "Built during the hackathon", newWork: "Everything in this project (code, pipeline, site, prompts, tests) was built Oct 31–Nov 4, 2026. Pre-existing external input: the Kahu Ola public API (/api/hazards/smoke-sat, /api/firms/hotspots), built earlier by the same author and used read-only as a data source.",
    replayBanner: "Replay of a past event. Not a current alert.",
    daily: "daily satellite pass",
    s1: "The GOES-West GeoColor (or MODIS) image on a fixed latitude/longitude grid. Everything else is measured on this grid.",
    s2: "NOAA's aerosol detection product (via Kahu Ola) flags hazy pixels. It cannot tell vog from smoke, and absence does not mean clean air.",
    s3: "Muse Spark looks at the image and draws a box around each haze or plume, plus one point inside it.",
    s4: "SAM 3.1 turns each box and point into a pixel mask. A second pass widens the box by 15% to catch faint tails, and is kept only if the mask stays coherent and does not spill onto land.",
    s5: "Muse Spark weighs the image with measured evidence: wind, distance to the volcanoes, satellite fire detections, and the official USGS volcano status at that time. The overall verdict is the most hazardous class confirmed at 70% or more; anything weaker is shown as not confirmed.",
    s6: "Muse Spark writes a short situation summary in five languages and selects official health guidance lines to quote. Muse Image paints a text-free background; the text is drawn by our code.",
    noAdp: "No aerosol detection available for this image.",
    noSam: "No plume to segment.",
    noAlert: "No alert issued. Alerts are written only when a hazard is confirmed at 70% or more.",
    scene: "Scene", cloud: "Cloud cover", plumes: "Plumes found", none: "none",
    promptUsed: "Prompt used", pass: "Pass 1 → pass 2", kept: "kept", concepts: "Text prompts (“smoke”, “haze”, “volcanic plume”) found nothing on satellite imagery, so boxes from Muse Spark are used.",
    plume: "Plume", evidence: "Evidence", caveats: "Caveats", wind: "Wind (10 m)", from: "from",
    vents: "Distance from plume's upwind end", fires: "Satellite fire clusters (not volcanic)", volcanic: "Summit glow excluded from fires",
    usgs: "USGS volcano status at image time", erupting: { yes: "erupting", no: "not erupting", episodic_pause: "paused between episodes", unknown: "status unclear" },
    notice: "HVO notice",
    languages: "Language", machine: "Machine-translated", review: "Needs community review", reviewed: "reviewed",
    source: "Source",
    how1: "Muse Spark (muse-spark-1.3)", how1d: "Vision to find plumes; an agent that calls our tools (wind, fires, USGS status, geometry) and cites every result; five-language summaries that quote official guidance.",
    how2: "SAM 3.1 (sam-3.1)", how2d: "Box and point prompts become pixel-accurate masks, in two passes.",
    how3: "Muse Image (muse-image-1.0)", how3d: "One text-free background per alert set. All text is rendered by our code.",
    costTitle: "Cost per run", costNote: "Pipeline cost from the API usage of each run. Alerts add about $0.03–0.05 when issued.",
    run: "Run", cost: "Cost", verdictCol: "Verdict",
    km: "km", kmh: "km/h",
  },
  vi: {
    skip: "Chuyển đến phần giải thích từng bước",
    liveTitle: "Vệ tinh đang thấy gì trên bầu trời Hawaiʻi",
    replaysTitle: "Xem lại",
    replaysLede: "Các sự kiện trong quá khứ được chạy lại qua cùng quy trình. Đây là minh họa, không phải cảnh báo hiện tại.",
    howTitle: "Cách hoạt động",
    footWarn: "Ước tính từ vệ tinh, không phải cảnh báo chính thức. Thông tin chính thức về vog: vog.ivhhn.org; về khói: fire.airnow.gov.",
    credits: 'Dữ liệu: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> (GOES-West GeoColor, MODIS), NOAA GOES-18 / NESDIS, NASA FIRMS, <a href="https://www.usgs.gov/observatories/hvo">Đài quan sát núi lửa Hawaiʻi (USGS)</a>, <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0), <a href="https://www.naturalearthdata.com/">Natural Earth</a> và API công khai của <a href="https://kahuola.org">Kahu Ola</a>. Hướng dẫn sức khỏe trích từ Hawaiʻi Interagency Vog Dashboard (IVHHN / Sở Y tế Hawaiʻi) và U.S. EPA AirNow.',
    kahuola: 'Thực hiện tại Hawaiʻi cho Meta Global AI Developer Hackathon. Toàn bộ mã được xây dựng từ 31/10 đến 4/11/2026; đầu vào có sẵn duy nhất là API công khai của <a href="https://kahuola.org">Kahu Ola</a> (cùng tác giả), chỉ đọc làm nguồn dữ liệu. Bản đồ hiểm họa: <a href="https://kahuola.org">kahuola.org</a>.',
    v: { wildfire_smoke: "Có thể là khói cháy rừng", vog_kilauea: "Có thể là sương mù núi lửa (vog) từ Kīlauea", vog_mauna_loa: "Có thể là sương mù núi lửa (vog) từ Mauna Loa",
         dust: "Có thể là bụi", cloud: "Mây", uncertain: "Có mù, chưa xác định được nguồn", no_plume: "Không phát hiện vệt mù" },
    tooCloudy: "Nhiều mây, khó nhìn thấy mù",
    liveLabel: "Trực tiếp", openLive: "Mở lượt quét trực tiếp", checkedAgo: (n) => n < 90 ? `kiểm tra ${n} phút trước` : `kiểm tra ${Math.round(n / 60)} giờ trước`,
    clouds: { clear: "trời quang", partly: "mây rải rác", mostly: "nhiều mây", overcast: "u ám" },
    seeSam: "Xem SAM hoạt động → bản xem lại Kīlauea", seeAlerts: "Xem cảnh báo 5 ngôn ngữ → bản xem lại Kīlauea",
    noSparkPlume: "Muse Spark không thấy vệt mù nào trong ảnh này, nên không có gì để đóng khung.",
    noSamLive: "Ảnh này không có vệt mù, nên SAM không có gì để tách.",
    confidence: "Độ tin cậy",
    scanned: "Ảnh vệ tinh",
    updated: "Kiểm tra lúc",
    noLive: "Chưa có lượt quét trực tiếp nào.",
    status: {
      night: "Hawaiʻi đang là ban đêm. Ảnh màu thật sẽ quét lại sau khi trời sáng; đang hiển thị lượt quét ban ngày gần nhất.",
      unchanged: "Chưa có ảnh vệ tinh mới; đang hiển thị lượt quét gần nhất.",
      budget_stop: "Đã tạm dừng quét trực tiếp (hết ngân sách demo). Đang hiển thị lượt quét gần nhất.",
      error: "Lượt quét mới nhất bị lỗi. Đang hiển thị lượt quét thành công gần nhất.",
      not_started: "",
      ok: "",
    },
    unconfirmed: "Chưa xác nhận (dưới 70% hoặc mặt nạ không đáng tin)",
    openSteps: "Xem cách đưa ra kết luận",
    steps: ["Ảnh màu thật", "Tín hiệu sol khí", "Khung của Muse Spark", "Mặt nạ SAM", "Dấu vết tác tử", "Kết luận và bằng chứng", "Cảnh báo"],
    sAgent: "Muse Spark tự quyết định gọi công cụ nào và theo thứ tự nào, rồi mới phân loại. Mỗi dòng bằng chứng phải dẫn nguồn một kết quả công cụ (E1, E2, …); kết luận không dẫn nguồn sẽ bị loại và hệ thống dùng bộ phân loại cố định.",
    agentCalls: (n, r) => `${n} lần gọi công cụ trong ${r} vòng`, round: "vòng", verified: "Mọi dòng bằng chứng đều dẫn nguồn kết quả công cụ.", rejectedV: "Kết luận của tác tử bị loại", fixedVs: "Bộ phân loại cố định trên cùng các vệt", agentVs: "Tác tử",
    noAgent: "Ảnh này không có vệt mù, nên tác tử không có gì để điều tra.", agentFixed: "Lượt chạy này dùng bộ phân loại cố định.", seeAgent: "Xem tác tử hoạt động → bản xem lại Kīlauea",
    guidance: "Hướng dẫn chính thức (trích dẫn)", guidanceNote: "Hướng dẫn sức khỏe được trích từ nguồn chính thức. AI chỉ chọn dòng, không tự viết lời khuyên sức khỏe.",
    verbatim: "nguyên văn", translationLabel: "bản dịch hướng dẫn chính thức, dịch máy", reviewedLabel: "bản dịch hướng dẫn chính thức, đã duyệt",
    newWorkTitle: "Xây dựng trong thời gian hackathon", newWork: "Toàn bộ dự án này (mã nguồn, quy trình, trang web, prompt, kiểm thử) được xây dựng từ 31/10 đến 4/11/2026. Đầu vào có sẵn từ trước: API công khai của Kahu Ola (/api/hazards/smoke-sat, /api/firms/hotspots), do cùng tác giả xây dựng trước đó, chỉ được đọc làm nguồn dữ liệu.",
    replayBanner: "Xem lại sự kiện đã qua. Không phải cảnh báo hiện tại.",
    daily: "lượt chụp vệ tinh hằng ngày",
    s1: "Ảnh GOES-West GeoColor (hoặc MODIS) trên lưới kinh độ/vĩ độ cố định. Mọi phép đo khác đều dựa trên lưới này.",
    s2: "Sản phẩm phát hiện sol khí của NOAA (qua Kahu Ola) đánh dấu các điểm ảnh có mù. Sản phẩm này không phân biệt được vog với khói, và không phát hiện không có nghĩa là không khí sạch.",
    s3: "Muse Spark xem ảnh và vẽ một khung quanh mỗi vệt mù, cùng một điểm nằm bên trong.",
    s4: "SAM 3.1 biến mỗi khung và điểm thành mặt nạ điểm ảnh. Lượt thứ hai nới khung thêm 15% để bắt phần đuôi mờ, và chỉ được giữ nếu mặt nạ liền mạch, không tràn lên đất liền.",
    s5: "Muse Spark cân nhắc ảnh cùng các bằng chứng đo được: gió, khoảng cách tới núi lửa, điểm cháy từ vệ tinh và tình trạng núi lửa chính thức của USGS lúc đó. Kết luận chung là loại nguy hiểm nhất được xác nhận từ 70% trở lên; các vệt yếu hơn được ghi là chưa xác nhận.",
    s6: "Muse Spark viết tóm tắt tình hình ngắn bằng năm ngôn ngữ và chọn các dòng hướng dẫn sức khỏe chính thức để trích dẫn. Muse Image vẽ nền không có chữ; chữ do mã của chúng tôi vẽ lên.",
    noAdp: "Không có dữ liệu phát hiện sol khí cho ảnh này.",
    noSam: "Không có vệt mù để tách.",
    noAlert: "Không phát cảnh báo. Cảnh báo chỉ được viết khi một mối nguy được xác nhận từ 70% trở lên.",
    scene: "Cảnh", cloud: "Độ che phủ mây", plumes: "Vệt mù tìm thấy", none: "không có",
    promptUsed: "Kiểu gợi ý", pass: "Lượt 1 → lượt 2", kept: "giữ", concepts: "Gợi ý bằng chữ (“smoke”, “haze”, “volcanic plume”) không tìm thấy gì trên ảnh vệ tinh, nên dùng khung của Muse Spark.",
    plume: "Vệt", evidence: "Bằng chứng (đầu ra của mô hình bằng tiếng Anh)", caveats: "Lưu ý", wind: "Gió (10 m)", from: "hướng",
    vents: "Khoảng cách từ đầu vệt (phía gió thổi tới)", fires: "Cụm điểm cháy từ vệ tinh (không phải núi lửa)", volcanic: "Ánh sáng miệng núi lửa (loại khỏi điểm cháy)",
    usgs: "Tình trạng núi lửa (USGS) tại thời điểm chụp", erupting: { yes: "đang phun trào", no: "không phun trào", episodic_pause: "tạm nghỉ giữa các đợt", unknown: "chưa rõ" },
    notice: "Thông báo HVO",
    languages: "Ngôn ngữ", machine: "Dịch máy", review: "Cần cộng đồng duyệt lại", reviewed: "đã duyệt",
    source: "Nguồn",
    how1: "Muse Spark (muse-spark-1.3)", how1d: "Thị giác để tìm vệt mù; tác tử gọi công cụ (gió, điểm cháy, tình trạng USGS, hình học) và dẫn nguồn mọi kết quả; tóm tắt năm ngôn ngữ trích dẫn hướng dẫn chính thức.",
    how2: "SAM 3.1 (sam-3.1)", how2d: "Khung và điểm trở thành mặt nạ chính xác tới từng điểm ảnh, qua hai lượt.",
    how3: "Muse Image (muse-image-1.0)", how3d: "Một ảnh nền không chữ cho mỗi bộ cảnh báo. Toàn bộ chữ do mã của chúng tôi vẽ.",
    costTitle: "Chi phí mỗi lượt chạy", costNote: "Chi phí quy trình tính từ mức sử dụng API của từng lượt. Cảnh báo tốn thêm khoảng 0,03–0,05 USD khi được phát.",
    run: "Lượt chạy", cost: "Chi phí", verdictCol: "Kết luận",
    km: "km", kmh: "km/h",
  },
};

const state = { lang: "en", index: null, runs: {}, current: null, step: 0, alertLang: null };
try { const s = localStorage.getItem("sov-lang"); if (s === "vi" || s === "en") state.lang = s; } catch (_) {}

const $ = (sel) => document.querySelector(sel);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k.nodeType ? k : document.createTextNode(String(k)));
  return n;
}
const t = () => T[state.lang];
const pct = (c) => `${Math.round((c || 0) * 100)}%`;

function fmtTime(iso) {
  if (!iso) return "";
  const loc = state.lang === "vi" ? "vi-VN" : "en-US";
  if (!iso.includes("T")) {
    const d = new Date(iso + "T12:00:00Z");
    return `${d.toLocaleDateString(loc, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" })} (${t().daily})`;
  }
  const d = new Date(iso);
  return d.toLocaleString(loc, { timeZone: "Pacific/Honolulu", year: "numeric", month: "short", day: "numeric",
                                 hour: "2-digit", minute: "2-digit" }) + " HST";
}
function verdictKey(run) { return run.detection === "no_plume" ? "no_plume" : (run.verdict && run.verdict.class) || "uncertain"; }
function hasVisiblePlume(run) {
  return !!run && ((run.steps.spark.plumes || []).length > 0 || (run.steps.sam.two_pass || []).length > 0 ||
                   ((run.verdict && run.verdict.confirmed) || []).length > 0);
}
function demoPath() {
  const r = state.index.replays.find((x) => x.slug === "kilauea_20261017") || state.index.replays[0];
  return r ? r.path : null;
}
function minutesAgo(iso) { return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000)); }

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}
async function loadRun(path) {
  if (!state.runs[path]) state.runs[path] = await getJSON(`data/${path}/run.json`);
  return state.runs[path];
}
/* Image names repeat between runs (live/image.jpg every hour), so version URLs by run id. */
const ver = (path) => (state.runs[path] && state.runs[path].run_id ? `?v=${encodeURIComponent(state.runs[path].run_id)}` : "");
const img = (path, file, alt, eager = true) => el("img", { src: `data/${path}/${file}${ver(path)}`, alt, loading: eager ? "eager" : "lazy", decoding: "async", width: 1000, height: 714 });

/* ---------------- static text ---------------- */
function applyStatic() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t()[n.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-html]").forEach((n) => { n.innerHTML = t()[n.dataset.i18nHtml]; }); // trusted strings above
  document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
}

/* ---------------- live ---------------- */
async function renderLive() {
  const box = $("#live");
  box.replaceChildren();
  const idx = state.index;
  if (!idx || !idx.live) { box.append(el("p", { class: "status-note", text: t().noLive })); return; }
  const run = await loadRun("live");
  const v = verdictKey(run);
  const note = t().status[idx.live_status] || "";
  if (!hasVisiblePlume(run)) {
    // Compact status: nothing to show step by step, so the viewer opens on a replay.
    const cloud = t().clouds[run.steps.spark.cloud_cover];
    const parts = [t().liveLabel, fmtTime(run.image_time), t().v.no_plume, cloud, t().checkedAgo(minutesAgo(idx.generated_at))].filter(Boolean);
    box.append(el("article", { class: "live__status" },
      el("span", { class: "live__dot", "aria-hidden": "true" }),
      el("p", { class: "live__line", text: parts.join(" · ") }),
      el("button", { type: "button", class: "btn", onclick: () => select("live", 0, true), text: t().openLive }),
      note && el("p", { class: "small live__note", text: note })));
    return;
  }
  const cloudy = v === "no_plume" && ["mostly", "overcast"].includes(run.steps.spark.cloud_cover);
  const line = cloudy ? `${t().v.no_plume}. ${t().tooCloudy}.` : t().v[v];
  const conf = run.verdict && run.verdict.confidence >= 0.7 && v !== "no_plume" ? `${t().confidence}: ${pct(run.verdict.confidence)}` : null;
  box.append(el("article", { class: "live__card" },
    el("div", { class: "live__img" }, img("live", v === "no_plume" ? run.steps.image.src : run.steps.classify.overlay,
                                          `${t().scanned}: ${fmtTime(run.image_time)}`)),
    el("div", { class: "live__text" },
      el("p", { class: "verdict-line", "data-v": cloudy ? "uncertain" : v, text: line }),
      conf && el("p", { class: "conf", text: conf }),
      el("p", { class: "small", text: `${t().scanned}: ${fmtTime(run.image_time)}. ${t().updated}: ${fmtTime(idx.generated_at)}.` }),
      note && el("p", { class: "status-note", text: note }),
      el("p", {}, el("a", { href: "#viewer", onclick: (e) => { e.preventDefault(); select("live", 0, true); }, text: t().openSteps })),
    )));
}

/* ---------------- replays ---------------- */
function renderReplays() {
  const ul = $("#replays");
  ul.replaceChildren();
  for (const r of state.index.replays) {
    const v = r.verdict ? r.verdict.class : "uncertain";
    ul.append(el("li", {}, el("button", {
      class: "replay", type: "button", "aria-current": String(state.current === r.path),
      onclick: () => select(r.path, 0, true),
    },
      el("img", { src: `data/${r.path}/image.jpg`, alt: "", loading: "lazy", width: 112, height: 80 }),
      el("span", {}, el("span", { class: "replay__title", text: r.title[state.lang] || r.title.en }),
        el("span", { class: "pill", "data-v": v, text: `${t().v[v]}${v !== "uncertain" ? " · " + pct(r.verdict.confidence) : ""}` })))));
  }
}

/* ---------------- viewer ---------------- */
async function select(path, step = 0, scroll = false) {
  state.current = path; state.step = step;
  try { history.replaceState(null, "", `#run=${path}&step=${step + 1}`); } catch (_) {}
  renderReplays();
  await renderViewer();
  if (scroll) $("#viewer").focus({ preventScroll: true }), $("#viewer").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function renderViewer() {
  const run = await loadRun(state.current);
  $("#viewer-h").textContent = run.mode === "live" ? `${t().v[verdictKey(run)]}` : (run.title[state.lang] || run.title.en);
  $("#viewer-meta").textContent = `${t().scanned}: ${fmtTime(run.image_time)} (${run.layer})`;
  $("#viewer-banner").replaceChildren(run.mode === "replay" ? el("p", { class: "replay-banner", text: t().replayBanner }) : "");
  const tabs = $("#steps");
  tabs.replaceChildren(...t().steps.map((name, i) => el("button", {
    class: "step", role: "tab", type: "button", id: `step-${i}`, "aria-selected": String(i === state.step),
    "aria-controls": "explain", tabindex: i === state.step ? "0" : "-1",
    onclick: () => select(state.current, i),
    onkeydown: (e) => {
      const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (d) { e.preventDefault(); const n = (state.step + d + 7) % 7; select(state.current, n).then(() => $(`#step-${n}`).focus()); }
    },
  }, el("b", { text: String(i + 1) }), name)));
  const active = tabs.querySelector('[aria-selected="true"]');
  if (active) tabs.scrollLeft = Math.max(0, active.offsetLeft - tabs.offsetLeft - 16);
  $("#explain").setAttribute("aria-labelledby", `step-${state.step}`);
  [step1, step2, step3, step4, stepAgent, step5, step6][state.step](run);
}

function frame(path, file, caption) {
  if (!file) return emptyFrame(state.runs[path], caption, null);
  $("#frame").replaceChildren(img(path, file, caption), el("figcaption", { text: caption }));
}
/* Never an empty black panel: the run's own true-color image, dimmed, with the message on top,
   and (optionally) a way to see the step working on the Kīlauea replay. */
function emptyFrame(run, message, cta) {
  const demo = demoPath();
  const showCta = cta && demo && state.current !== demo;
  $("#frame").replaceChildren(el("div", { class: "dim" },
    run ? img(state.current, run.steps.image.src, "") : "",
    el("div", { class: "dim__msg" },
      el("p", { text: message }),
      showCta && el("button", { type: "button", class: "btn btn--light",
        onclick: () => select(demo, cta.step, true), text: cta.label }))));
}
function explain(...nodes) { $("#explain").replaceChildren(...nodes); }
const dl = (pairs) => el("dl", {}, pairs.filter(Boolean).flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, v)]));

function step1(run) {
  const s = run.steps.image;
  frame(state.current, s.src, `${s.layer} · ${fmtTime(s.time)}`);
  explain(el("h3", { text: t().steps[0] }), el("p", { text: t().s1 }),
    dl([["Layer", s.layer], [t().scanned, fmtTime(s.time)], [t().source, s.source]]));
}
function step2(run) {
  const s = run.steps.adp;
  if (s.src) frame(state.current, s.src, "NOAA ADP (Kahu Ola)");
  else emptyFrame(run, t().noAdp, null);
  explain(el("h3", { text: t().steps[1] }), el("p", { text: t().s2 }),
    dl([["State", s.state || "—"], ["Regions", String(s.candidates)], s.reason && ["Note", s.reason],
        s.meaning_of_absence && ["Absence", s.meaning_of_absence]]));
}
function step3(run) {
  const s = run.steps.spark;
  if (s.plumes.length) frame(state.current, s.src, "Muse Spark");
  else emptyFrame(run, t().noSparkPlume, { step: 2, label: t().seeSam });
  explain(el("h3", { text: t().steps[2] }), el("p", { text: t().s3 }),
    dl([[t().scene, s.scene], [t().cloud, s.cloud_cover]]),
    el("h3", { text: t().plumes }),
    s.plumes.length ? el("ul", {}, s.plumes.map((p, i) => el("li", {}, el("strong", { text: `#${i + 1} ` }), `${p.label} (${p.visibility})`)))
                    : el("p", { text: t().none }));
}
function step4(run) {
  const s = run.steps.sam;
  if (s.src) frame(state.current, s.src, "SAM 3.1: red = pass 1, cyan = pass 2");
  else emptyFrame(run, t().noSamLive, { step: 3, label: t().seeSam });
  explain(el("h3", { text: t().steps[3] }), el("p", { text: t().s4 }),
    s.prompt_used ? dl([[t().promptUsed, s.prompt_used]]) : "",
    s.two_pass.length ? el("table", { class: "table" },
      el("thead", {}, el("tr", {}, el("th", { text: t().plume }), el("th", { text: t().pass }), el("th", { text: t().kept }))),
      el("tbody", {}, s.two_pass.map((r) => el("tr", {},
        el("td", { text: `#${r.plume_id}` }),
        el("td", { text: `${r.pass1_px.toLocaleString()} → ${r.pass2_px.toLocaleString()} px` }),
        el("td", { text: `${r.kept}: ${r.reason}` }))))) : el("p", { text: t().noSam }),
    el("p", { class: "small", text: t().concepts }));
}
function stepAgent(run) {
  const a = run.steps.agent || { calls: [] };
  if (!a.calls || !a.calls.length) {
    emptyFrame(run, hasVisiblePlume(run) ? t().agentFixed : t().noAgent, { step: 4, label: t().seeAgent });
    explain(el("h3", { text: t().steps[4] }), el("p", { text: t().sAgent }));
    return;
  }
  frame(state.current, run.steps.classify.overlay, t().agentCalls(a.calls.length, a.rounds));
  explain(
    el("h3", { text: t().steps[4] }), el("p", { text: t().sAgent }),
    el("p", { class: "small", text: `${t().agentCalls(a.calls.length, a.rounds)} · $${(a.cost_usd || 0).toFixed(3)}` }),
    el("ol", { class: "trace" }, a.calls.map((c) => el("li", {},
      el("span", { class: "cite", text: c.cite }), " ",
      el("strong", { text: c.name }),
      el("span", { class: "small", text: ` ${t().round} ${c.round} · ${Object.entries(c.arguments).map(([k, v]) => `${k}=${Array.isArray(v) ? "[" + v.join(", ") + "]" : v}`).join(", ")}` }),
      el("div", { text: c.summary })))),
    a.valid ? el("p", { class: "ok-note", text: t().verified }) : el("p", { class: "status-note", text: `${t().rejectedV}: ${a.rejected}` }),
    a.compare && a.compare.standard ? dl([[t().agentVs, t().v[a.compare.agent] || a.compare.agent || "—"],
                                          [t().fixedVs, t().v[a.compare.standard] || a.compare.standard]]) : "",
  );
}
function step5(run) {
  const s = run.steps.classify;
  const v = verdictKey(run);
  frame(state.current, s.overlay, t().v[v]);
  const ov = run.verdict || {};
  const plumeInfo = Object.fromEntries((s.plumes || []).map((p) => [p.plume_id, p]));
  const vol = (s.volcano_status && s.volcano_status.volcanoes) || {};
  explain(
    el("h3", { text: t().steps[5] }), el("p", { text: t().s5 }),
    el("p", { class: "verdict-line", "data-v": v, text: `${t().v[v]}${ov.confidence >= 0.7 ? ` (${pct(ov.confidence)})` : ""}` }),
    (ov.unconfirmed || []).length ? el("p", { class: "small", text: `${t().unconfirmed}: ` + ov.unconfirmed.map((u) =>
      `#${u.plume_id} ${t().v[u.class] || u.class} ${pct(u.confidence)}${u.not_confirmed_because ? " (" + u.not_confirmed_because + ")" : ""}`).join("; ") }) : "",
    ...(s.per_plume || []).map((p) => {
      const g = plumeInfo[p.plume_id] || {};
      return el("div", { class: "plume" },
        el("h3", { text: `${t().plume} #${p.plume_id}: ${t().v[p.class] || p.class} (${pct(p.confidence)})` }),
        g.upwind_end_distance_km ? el("p", { class: "small", text: `${t().vents}: Kīlauea ${g.upwind_end_distance_km.kilauea_summit} ${t().km}, Mauna Loa ${g.upwind_end_distance_km.mauna_loa_summit} ${t().km}` }) : "",
        el("p", { class: "small", text: t().evidence }),
        el("ul", {}, (p.evidence || []).map((e) => el("li", { text: e }))));
    }),
    s.caveats ? el("p", { class: "small" }, el("strong", { text: `${t().caveats}: ` }), s.caveats) : "",
    el("h3", { text: t().usgs }),
    el("ul", {}, Object.entries(vol).map(([k, x]) => el("li", {},
      el("strong", { text: k === "kilauea" ? "Kīlauea" : "Mauna Loa" }),
      `: ${x.alert_level || "?"} / ${x.aviation_color || "?"}, ${t().erupting[x.erupting] || x.erupting || "?"}. `,
      x.activity_summary ? el("span", { class: "small", text: x.activity_summary + " " }) : "",
      x.notice_url ? el("a", { href: x.notice_url, text: `${t().notice} ${x.notice_sent_utc || ""}` }) : ""))),
    s.wind ? el("h3", { text: t().wind }) : "",
    s.wind ? el("ul", {}, Object.entries(s.wind.sites || {}).map(([k, w]) => el("li", { text: `${k.replace(/_/g, " ")}: ${w.speed_kmh} ${t().kmh} ${t().from} ${w.from_deg}°` }))) : "",
    el("h3", { text: t().fires }),
    (s.firms.fire_clusters || []).length ? el("ul", {}, s.firms.fire_clusters.map((c) => el("li", { text: `${c.near}: ${c.n}` }))) : el("p", { text: t().none }),
    s.firms.volcanic_thermal_excluded && Object.keys(s.firms.volcanic_thermal_excluded).length
      ? el("p", { class: "small", text: `${t().volcanic}: ` + Object.entries(s.firms.volcanic_thermal_excluded).map(([z, n]) => `${z} ${n}`).join(", ") }) : "",
  );
}
function step6(run) {
  const a = run.steps.alerts;
  if (!a.available) {
    emptyFrame(run, t().noAlert, { step: 6, label: t().seeAlerts });
    explain(el("h3", { text: t().steps[6] }), el("p", { text: t().s6 }), el("p", { class: "status-note", text: t().noAlert }));
    return;
  }
  const lang = a.items.some((x) => x.lang === state.alertLang) ? state.alertLang : (state.lang === "vi" ? "vi" : "en");
  const it = a.items.find((x) => x.lang === lang);
  const f = $("#frame");
  f.replaceChildren(it.card ? el("img", { src: `data/${state.current}/${it.card}${ver(state.current)}`, alt: `${it.headline}. ${it.summary}`, width: 900, height: 506 }) : "", el("figcaption", { text: it.language }));
  explain(
    el("h3", { text: t().steps[6] }), el("p", { text: t().s6 }),
    el("div", { class: "tabs", role: "tablist", "aria-label": t().languages }, a.items.map((x) => el("button", {
      type: "button", role: "tab", "aria-selected": String(x.lang === lang),
      onclick: () => { state.alertLang = x.lang; step6(run); }, text: x.language }))),
    it.replay_banner ? el("p", { class: "replay-banner", text: it.replay_banner }) : "",
    el("p", {}, it.machine_translated ? el("span", { class: "flag", text: t().machine }) : "", it.needs_community_review ? el("span", { class: "flag", text: t().review }) : ""),
    el("p", { class: "verdict-line", "data-v": verdictKey(run), text: it.headline }),
    el("p", { text: it.summary }),
    el("h4", { class: "guidance-h", text: t().guidance }),
    el("p", { class: "small", text: t().guidanceNote }),
    el("ul", { class: "guidance" }, it.actions.map((x) => el("li", {},
      el("span", { text: x.text }),
      el("span", { class: "src" }, " — ", el("a", { href: x.source_url, text: x.publisher || t().source }),
        ` (${x.verbatim ? t().verbatim : (x.reviewed ? t().reviewedLabel : t().translationLabel)})`)))),
    el("p", { class: "small", text: `${it.confidence_label}. ${it.disclaimer}` }),
    el("p", { class: "small" }, el("a", { href: it.official_source_url, text: it.official_source_url })),
  );
}

/* ---------------- how it works ---------------- */
async function renderHow() {
  const paths = [...(state.index.live ? ["live"] : []), ...state.index.replays.map((r) => r.path)];
  const runs = await Promise.all(paths.map((p) => loadRun(p).catch(() => null)));
  $("#how").replaceChildren(
    el("div", { class: "how__models" },
      [["how1", "how1d"], ["how2", "how2d"], ["how3", "how3d"]].map(([a, b]) => el("div", { class: "model" }, el("strong", { text: t()[a] }), el("span", { text: t()[b] })))),
    el("h3", { text: t().costTitle }),
    el("table", { class: "table" },
      el("thead", {}, el("tr", {}, el("th", { text: t().run }), el("th", { text: t().verdictCol }), el("th", { text: t().cost }))),
      el("tbody", {}, runs.filter(Boolean).map((r) => el("tr", {},
        el("td", { text: r.title[state.lang] || r.title.en }),
        el("td", { text: t().v[verdictKey(r)] }),
        el("td", { text: `$${(r.cost_usd || 0).toFixed(3)}` }))))),
    el("p", { class: "small", text: t().costNote }),
    el("h3", { text: t().newWorkTitle }),
    el("p", { class: "small", text: t().newWork }));
}

/* ---------------- boot ---------------- */
async function renderAll() {
  applyStatic();
  await renderLive();
  renderReplays();
  await renderViewer();
  await renderHow();
}
document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
  state.lang = b.dataset.lang;
  try { localStorage.setItem("sov-lang", state.lang); } catch (_) {}
  renderAll();
}));

function routeFromHash() {
  const m = location.hash.match(/run=([\w/]+)(?:&step=(\d))?/);
  const known = [...(state.index.live ? ["live"] : []), ...state.index.replays.map((r) => r.path)];
  const live = state.runs.live;
  const fallback = live && hasVisiblePlume(live) ? "live" : (demoPath() || known[0]);
  return { path: m && known.includes(m[1]) ? m[1] : fallback,
           step: m && m[2] ? Math.min(6, Math.max(0, Number(m[2]) - 1)) : 0 };
}
window.addEventListener("hashchange", () => {
  if (!state.index) return;
  const r = routeFromHash();
  if (r.path !== state.current || r.step !== state.step) select(r.path, r.step);
});

(async function boot() {
  applyStatic();
  try {
    state.index = await getJSON("data/index.json");
  } catch (e) {
    $("#live").replaceChildren(el("p", { class: "status-note", text: `Could not load data/index.json (${e.message}).` }));
    return;
  }
  if (state.index.live) { try { await loadRun("live"); } catch (_) {} }
  const r = routeFromHash();
  state.current = r.path;
  state.step = r.step;
  await renderAll();
})();
