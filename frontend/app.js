/* Farm Advisor web page (Ananya).
 * RULE: no decision logic here. This file only collects input, calls the backend, and displays
 * what the backend returned. Label dictionaries below are display text only.
 */

// ---- The ONLY place to change when switching backends -------------------------------------
const API_BASE = "";                 // "" = same server that serves this page (uvicorn api:app)
const ASK_URL = API_BASE + "/ask";   // the single backend call goes through askBackend()
const REFERENCE_URL = API_BASE + "/reference";
const SAMPLE_BASE = API_BASE + "/eval/";
// -------------------------------------------------------------------------------------------

// TODO(Prakruthi/Pavithra): verify this number before it appears in any public material.
const EXPERT_HELP = "Kisan Call Centre: 1800-180-1551 (free)  |  ಕಿಸಾನ್ ಕಾಲ್ ಸೆಂಟರ್: 1800-180-1551";
const MOCK = new URLSearchParams(location.search).has("mock");

// Display-only labels
const DECISION_LABELS = {
  IRRIGATE_NOW: "Irrigate now · ಈಗ ನೀರು ಹಾಯಿಸಿ",
  IRRIGATE_SOON: "Irrigate soon · ಶೀಘ್ರದಲ್ಲೇ ನೀರು ಹಾಯಿಸಿ",
  WAIT: "Wait · ಕಾಯಿರಿ",
  INSUFFICIENT_DATA: "Not enough data · ಸಾಕಷ್ಟು ಮಾಹಿತಿ ಇಲ್ಲ",
  ABOVE_RECENT: "Above recent price · ಇತ್ತೀಚಿನ ಬೆಲೆಗಿಂತ ಹೆಚ್ಚು",
  NEAR_RECENT: "Near recent price · ಇತ್ತೀಚಿನ ಬೆಲೆಗೆ ಹತ್ತಿರ",
  BELOW_RECENT: "Below recent price · ಇತ್ತೀಚಿನ ಬೆಲೆಗಿಂತ ಕಡಿಮೆ",
  STALE_DATA: "Old price data · ಹಳೆಯ ಬೆಲೆ ಮಾಹಿತಿ",
  UNSUPPORTED: "Ask an expert · ತಜ್ಞರನ್ನು ಕೇಳಿ",
};
const FRESHNESS_LABELS = {
  live: "● Live", cached: "Cached (saved earlier)", reference: "Reference data",
  recorded_sample: "Recorded sample (not live)",
};
const CROP_PICTURES = { Ragi: "🌾", Maize: "🌽", Tomato: "🍅", Groundnut: "🥜" };

// Used only if GET /reference is unreachable (e.g. page opened without the API).
const FALLBACK_REFERENCE = {
  crops: [
    { name_en: "Ragi", name_kn: "ರಾಗಿ" }, { name_en: "Maize", name_kn: "ಮೆಕ್ಕೆಜೋಳ" },
    { name_en: "Tomato", name_kn: "ಟೊಮೇಟೊ" }, { name_en: "Groundnut", name_kn: "ಕಡಲೆಕಾಯಿ" },
  ],
  soils: [{ soil_type: "sandy_loam" }, { soil_type: "loam" }, { soil_type: "clay_loam" }, { soil_type: "black_clay" }],
  mandis: [{ mandi_name: "Kolar", district: "Kolar", latitude: "13.14", longitude: "78.13" }],
};

const $ = (id) => document.getElementById(id);
let reference = FALLBACK_REFERENCE;
let selectedCrop = null;
let lastQuestion = "";

// ---------------------------------------------------------------- profile -------------------
function soilLabel(type) {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function fillProfileControls() {
  const loc = $("location");
  loc.replaceChildren(...reference.mandis.map((m, i) => {
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = `${m.mandi_name} (${m.district})`;
    return o;
  }));
  const soil = $("soil_type");
  soil.replaceChildren(...reference.soils.map((s) => {
    const o = document.createElement("option");
    o.value = s.soil_type;
    o.textContent = soilLabel(s.soil_type);
    return o;
  }));
  renderCropButtons($("crop-buttons"), (name) => { selectedCrop = name; markSelected(); }, true);
}

function renderCropButtons(container, onPick, isRadio) {
  container.replaceChildren(...reference.crops.map((c) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pic-btn";
    b.dataset.crop = c.name_en;
    if (isRadio) { b.setAttribute("role", "radio"); b.setAttribute("aria-checked", "false"); }
    const pic = document.createElement("span"); pic.className = "pic"; pic.textContent = CROP_PICTURES[c.name_en] || "🌱";
    const kn = document.createElement("span"); kn.className = "kn"; kn.lang = "kn"; kn.textContent = c.name_kn;
    const en = document.createElement("span"); en.className = "en"; en.textContent = c.name_en;
    b.append(pic, kn, en);
    b.addEventListener("click", () => onPick(c.name_en));
    return b;
  }));
}

function markSelected() {
  document.querySelectorAll("#crop-buttons .pic-btn").forEach((b) =>
    b.setAttribute("aria-checked", String(b.dataset.crop === selectedCrop)));
}

function collectProfile() {
  const m = reference.mandis[Number($("location").value)] || {};
  const area = parseFloat($("area_acres").value);
  return {
    crop: selectedCrop,                              // null if the farmer has not picked one
    soil_type: $("soil_type").value || null,
    sowing_date: $("sowing_date").value || null,     // YYYY-MM-DD
    area_acres: Number.isFinite(area) ? area : null,
    water_source: $("water_source").value || null,
    mandi: m.mandi_name || null,
    latitude: m.latitude ? Number(m.latitude) : null,   // already rounded in data/mandis.csv
    longitude: m.longitude ? Number(m.longitude) : null,
  };
}

// ---------------------------------------------------------------- backend -------------------
// All backend traffic goes through this one function.
async function askBackend(payload) {
  const res = await fetch(ASK_URL, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok && res.status !== 500) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadSample(name) {
  const res = await fetch(SAMPLE_BASE + name);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadReference() {
  try {
    const res = await fetch(REFERENCE_URL);
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (data.crops?.length && data.soils?.length && data.mandis?.length) reference = data;
  } catch (_) { /* keep fallback lists */ }
  fillProfileControls();
}

// ---------------------------------------------------------------- result states -------------
function show(id, visible) { $(id).hidden = !visible; }

function resetResult() {
  ["state-loading", "state-error", "card", "confirm"].forEach((id) => show(id, false));
}

function showLoading() { resetResult(); show("result", true); show("state-loading", true); }

function showError(text) {
  resetResult(); show("result", true);
  const el = $("state-error");
  el.textContent = text;
  show("state-error", true);
}

function fillList(id, items) {
  const ul = $(id);
  ul.replaceChildren(...(items || []).map((t) => { const li = document.createElement("li"); li.textContent = String(t); return li; }));
}

function formatTimestamp(ts) {
  if (!ts) return "not available";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime()) || !String(ts).includes("T")) return String(ts);   // plain date: show as given
  return `${d.toLocaleString()} (${ts})`;
}

function renderResult(r) {
  // Backend asked the farmer to confirm the crop (proposed contract: status "needs_confirmation").
  if (r.status === "needs_confirmation") { showCropConfirmation(); return; }
  if (r.status === "error" && !r.decision) {
    showError((r.reasons && r.reasons[0]) || "Something went wrong. Please try again. / ಏನೋ ತಪ್ಪಾಗಿದೆ. ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.");
    return;
  }
  resetResult(); show("result", true); show("card", true);

  const decision = r.decision || (r.intent === "UNSUPPORTED" ? "UNSUPPORTED" : "");
  const badge = $("badge");
  badge.dataset.decision = decision;
  badge.textContent = DECISION_LABELS[decision] || decision || "—";

  const fresh = $("freshness");
  fresh.dataset.fresh = r.freshness || "";
  fresh.textContent = FRESHNESS_LABELS[r.freshness] || r.freshness || "Freshness unknown";

  $("msg-local").textContent = r.message_local || "";
  $("msg-en").textContent = r.message_en || "";
  $("msg-local").hidden = !r.message_local;
  $("msg-en").hidden = !r.message_en;
  fillList("reasons", r.reasons);

  const stale = $("stale-warning");
  const isStale = decision === "STALE_DATA" || r.freshness === "cached" || r.freshness === "recorded_sample";
  stale.hidden = !isStale;
  if (isStale) {
    stale.textContent = `⚠ This data is not live. Data date: ${formatTimestamp(r.data_timestamp)} · ಈ ಮಾಹಿತಿ ಹಳೆಯದಾಗಿರಬಹುದು.`;
  }
  const expert = $("expert");
  const needsExpert = decision === "UNSUPPORTED" || r.intent === "UNSUPPORTED";
  expert.hidden = !needsExpert;
  if (needsExpert) expert.textContent = EXPERT_HELP;

  $("source").textContent = r.source || "not available";
  $("timestamp").textContent = formatTimestamp(r.data_timestamp);
  $("confidence").textContent = r.confidence || "not available";
  fillList("why-reasons", r.reasons);
  fillList("why-assumptions", r.assumptions);
  $("why").open = false;

  const audio = $("reply-audio");
  audio.hidden = !r.audio_url;
  if (r.audio_url) audio.src = r.audio_url;
}

function showCropConfirmation() {
  resetResult(); show("result", false); show("confirm", true);
  renderCropButtons($("confirm-buttons"), (name) => {
    selectedCrop = name; markSelected(); show("confirm", false); submitQuestion();
  }, false);
  $("confirm").scrollIntoView({ behavior: "smooth", block: "center" });
}

// ---------------------------------------------------------------- ask -----------------------
async function submitQuestion() {
  const question = $("question").value.trim() || lastQuestion;
  if (!question) { showError("Please type or speak a question. / ದಯವಿಟ್ಟು ಪ್ರಶ್ನೆ ಬರೆಯಿರಿ ಅಥವಾ ಮಾತನಾಡಿ."); return; }
  lastQuestion = question;
  const btn = $("ask-btn");
  btn.disabled = true; showLoading();
  try {
    const result = await askBackend({ question, language: $("language").value, profile: collectProfile() });
    renderResult(result);
  } catch (err) {
    showError("Could not reach the advisor. Check your internet and try again. / ಸಂಪರ್ಕ ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ಇಂಟರ್ನೆಟ್ ಪರಿಶೀಲಿಸಿ.");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- voice ---------------------
let recorder = null, chunks = [], stream = null;

async function toggleRecording() {
  const btn = $("mic-btn"), msg = $("mic-msg");
  if (recorder && recorder.state === "recording") { recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    msg.textContent = "Voice recording is not supported in this browser. Please type your question.";
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (_) {
    msg.textContent = "Microphone is blocked. Allow the microphone in your browser settings, or type your question. / ಮೈಕ್ ನಿರ್ಬಂಧಿಸಲಾಗಿದೆ. ಪ್ರಶ್ನೆಯನ್ನು ಬರೆಯಿರಿ.";
    return;
  }
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    const player = $("playback");
    player.src = URL.createObjectURL(blob);
    player.hidden = false;
    btn.setAttribute("aria-pressed", "false");
    $("mic-label").textContent = "Speak";
    msg.textContent = "Recorded. Play it back below. (Sending voice to the advisor comes after the backend is ready; for now please also type your question.)";
  };
  recorder.start();
  btn.setAttribute("aria-pressed", "true");
  $("mic-label").textContent = "Stop";
  msg.textContent = "Recording… speak now / ಮಾತನಾಡಿ…";
}

// ---------------------------------------------------------------- start ---------------------
$("ask-btn").addEventListener("click", submitQuestion);
$("mic-btn").addEventListener("click", toggleRecording);
$("question").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitQuestion(); });

if (MOCK) {
  show("mock-bar", true);
  document.querySelectorAll("[data-sample]").forEach((b) => b.addEventListener("click", async () => {
    showLoading();
    try { renderResult(await loadSample(b.dataset.sample)); }
    catch (_) { showError("Could not load the sample file."); }
  }));
}
loadReference();
