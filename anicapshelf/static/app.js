const state = {
  captures: [],
  token: "",
};

const capturesEl = document.querySelector("#captures");
const detailEl = document.querySelector("#detail-body");
const summaryEl = document.querySelector("#summary");
const tagsEl = document.querySelector("#tags");
const collectionsEl = document.querySelector("#collections");
const tokenInput = document.querySelector("#api-token");

tokenInput.addEventListener("input", () => {
  state.token = tokenInput.value.trim();
});

document.querySelector("#reload").addEventListener("click", () => {
  loadArchive();
});

async function apiGet(path) {
  const headers = {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(path, { headers });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadArchive() {
  setError("");
  try {
    const [captures, tags, collections] = await Promise.all([
      apiGet("/api/captures?limit=120"),
      apiGet("/api/tags"),
      apiGet("/api/collections"),
    ]);
    state.captures = captures.captures;
    renderSummary();
    await renderCaptures();
    renderTags(tags.tags);
    renderCollections(collections.collections);
  } catch (error) {
    setError(`読み込みに失敗しました: ${error.message}`);
  }
}

function renderSummary() {
  summaryEl.textContent = `${state.captures.length}件のキャプチャ`;
}

async function renderCaptures() {
  const cards = [];
  for (const capture of state.captures) {
    cards.push(await captureCard(capture));
  }
  capturesEl.replaceChildren(...cards);
}

async function captureCard(capture) {
  const button = document.createElement("button");
  button.className = "capture-card";
  button.type = "button";
  button.addEventListener("click", () => loadCaptureDetail(capture.id));
  const image = document.createElement("img");
  image.src = await imageSource(`/api/captures/${capture.id}/image`);
  image.alt = capture.filename;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.append(
    textNode("div", capture.filename, "filename"),
    textNode("div", capture.recording_title || "録画未確定", "subtext"),
    textNode("div", (capture.tags || []).join(" / "), "subtext"),
  );
  button.append(image, meta);
  return button;
}

async function imageSource(path) {
  if (!state.token) {
    return path;
  }
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return URL.createObjectURL(await response.blob());
}

async function loadCaptureDetail(captureId) {
  setError("");
  try {
    const detail = await apiGet(`/api/captures/${captureId}`);
    await renderDetail(detail);
  } catch (error) {
    setError(`詳細の読み込みに失敗しました: ${error.message}`);
  }
}

async function renderDetail(detail) {
  const capture = detail.capture;
  if (!capture) {
    detailEl.textContent = "キャプチャが見つかりません。";
    return;
  }
  const tags = detail.annotations.flatMap((annotation) => annotation.tags || []);
  const bestMatch = detail.matches.find((match) => match.is_best) || detail.matches[0];
  detailEl.replaceChildren(
    imageNode(await imageSource(`/api/captures/${capture.id}/image`), capture.filename),
    kv("ファイル", capture.filename),
    kv("撮影時刻", capture.captured_at || ""),
    kv("録画", bestMatch?.recording_title || "未確定"),
    kv("動画内秒数", bestMatch?.source_time_seconds ?? ""),
    kv("タグ", [...new Set(tags)].join(" / ")),
    kv("字幕", detail.subtitles.map((subtitle) => subtitle.text).join(" / ")),
    kv("OCR", detail.ocr_results.map((result) => result.text).join(" / ")),
    kv("コレクション", detail.collections.map((collection) => collection.name).join(" / ")),
    kv("ShareX", detail.sharex_history.map((item) => item.url || item.host || item.type).join(" / ")),
  );
}

function renderTags(tags) {
  tagsEl.replaceChildren(
    ...tags.map((tag) => textNode("span", `${tag.name} ${tag.count}`, "pill")),
  );
}

function renderCollections(collections) {
  collectionsEl.replaceChildren(
    ...collections.map((collection) =>
      textNode("div", `${collection.name} (${collection.capture_count})`, "list-item"),
    ),
  );
}

function kv(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "kv";
  wrapper.append(textNode("span", label), textNode("strong", String(value || "")));
  return wrapper;
}

function imageNode(src, alt) {
  const image = document.createElement("img");
  image.src = src;
  image.alt = alt;
  return image;
}

function textNode(tagName, text, className = "") {
  const node = document.createElement(tagName);
  if (className) {
    node.className = className;
  }
  node.textContent = text;
  return node;
}

function setError(message) {
  if (!message) {
    return;
  }
  detailEl.replaceChildren(textNode("div", message, "error"));
}

loadArchive();
