/* CometForge client: queue, options, upload, progress, and download. */

const MB = 1_000_000;
const els = {
  drop: document.getElementById("drop"), pickBtn: document.getElementById("pickBtn"),
  fileInput: document.getElementById("fileInput"), clearBtn: document.getElementById("clearBtn"),
  outName: document.getElementById("outName"), targetMb: document.getElementById("targetMb"),
  targetMbNumber: document.getElementById("targetMbNumber"), targetMbValue: document.getElementById("targetMbValue"),
  compressMode: document.getElementById("compressMode"), linearize: document.getElementById("linearize"),
  splitEnabled: document.getElementById("splitEnabled"), splitOptions: document.getElementById("splitOptions"),
  splitCount: document.getElementById("splitCount"), forgeBtn: document.getElementById("forgeBtn"),
  hint: document.getElementById("hint"), status: document.getElementById("status"), list: document.getElementById("list"),
  count: document.getElementById("count"), total: document.getElementById("total"), selectedCount: document.getElementById("selectedCount"),
  moveTopBtn: document.getElementById("moveTopBtn"), moveUpBtn: document.getElementById("moveUpBtn"),
  moveDownBtn: document.getElementById("moveDownBtn"), moveBottomBtn: document.getElementById("moveBottomBtn"),
  progressWrap: document.getElementById("progressWrap"), buildBar: document.getElementById("buildBar"),
  compressBar: document.getElementById("compressBar"),
  queueView: document.getElementById("queueView"), resultsView: document.getElementById("resultsView"),
  resultsSub: document.getElementById("resultsSub"), resultsNotice: document.getElementById("resultsNotice"),
  outputList: document.getElementById("outputList"), previewFrame: document.getElementById("previewFrame"),
  previewEmpty: document.getElementById("previewEmpty"), downloadAllBtn: document.getElementById("downloadAllBtn"),
  closeResultsBtn: document.getElementById("closeResultsBtn"),
  queueSort: document.getElementById("queueSort"),
  partProgress: document.getElementById("partProgress"), viewerMode: document.getElementById("viewerMode"),
  previewPair: document.getElementById("previewPair"), beforePane: document.getElementById("beforePane"),
  beforeFrame: document.getElementById("beforeFrame"), beforeSize: document.getElementById("beforeSize"),
  afterSize: document.getElementById("afterSize"), afterLabel: document.getElementById("afterLabel"),
};

let items = [];
let selectedIds = new Set();
let dragIds = [];
let lastSelectedIndex = -1;
let resultFiles = [];
let archiveResult = null;
let selectedOutput = null;
const nameCollator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });
function compareNames(a, b) {
  const aNumeric = /^\d/.test(a.name), bNumeric = /^\d/.test(b.name);
  if (aNumeric !== bNumeric) return aNumeric ? -1 : 1;
  return nameCollator.compare(a.name, b.name);
}
function applyQueueSort() {
  const mode = els.queueSort.value;
  if (mode === "manual") return;
  items.sort((a, b) => {
    if (mode === "name") return compareNames(a, b);
    return (mode === "date-newest" ? b.lastModified - a.lastModified : a.lastModified - b.lastModified) || compareNames(a, b);
  });
  lastSelectedIndex = -1;
}
function useManualOrder() {
  if (els.queueSort.value !== "manual") { els.queueSort.value = "manual"; els.queueSort.dispatchEvent(new Event("change")); }
}
function notifyChange() { window.dispatchEvent(new Event("cometforge:change")); }

function fmtMB(bytes) { return `${(bytes / MB).toFixed(2)} MB`; }
function setHint(text) { els.hint.textContent = text || ""; }
function setStatus(text) { els.status.textContent = text || ""; }
function setBar(el, pct, active) {
  el.style.width = `${(Math.max(0, Math.min(1, pct || 0)) * 100).toFixed(1)}%`;
  el.classList.toggle("active", Boolean(active));
}
function isPdf(file) { return file?.type === "application/pdf" || /\.pdf$/i.test(file?.name || ""); }
function isImage(file) { return (file?.type || "").startsWith("image/") || /\.(jpe?g|png|tiff?)$/i.test(file?.name || ""); }
function genId() { return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`; }
function normaliseOutputName(value) {
  const name = (value || "CometForge").trim() || "CometForge";
  return /\.pdf$/i.test(name) ? name : `${name}.pdf`;
}
function selectedItems() { return items.filter((item) => selectedIds.has(item.id)); }

function getSnapshot() {
  const splitCount = Math.max(1, Math.min(100, Number.parseInt(els.splitCount.value, 10) || 5));
  return {
    files: items.map((item) => item.file),
    options: {
      output_name: normaliseOutputName(els.outName.value), target_mb: Number(els.targetMb.value) || 20,
      compress_mode: els.compressMode.value || "targetfit", linearize: els.linearize.checked,
      dpi_fallback: 300, split_enabled: els.splitEnabled.checked,
      ...(els.splitEnabled.checked ? { split_count: splitCount } : {}),
    },
  };
}

function updateTarget(value) {
  const min = Number(els.targetMb.min) || 1;
  const max = Number(els.targetMb.max) || 200;
  const n = Math.round(Math.max(min, Math.min(max, Number(value) || 20)) * 10) / 10;
  const pretty = Number.isInteger(n) ? String(n) : n.toFixed(1);
  els.targetMb.value = String(n);
  els.targetMbNumber.value = String(n);
  els.targetMbValue.value = `${pretty} MB`;
  els.targetMbValue.textContent = `${pretty} MB`;
}

function updateSplitControl() {
  const enabled = els.splitEnabled.checked;
  els.splitOptions.classList.toggle("disabled", !enabled);
  els.splitCount.disabled = !enabled;
}
function updateCompressionNote() {
  const notes = { off: "Build only preserves image and PDF content. The size cap is not applied.", lossless: "Identical image quality; optimizes PDF structure. Some files remain above the cap.", targetfit: "Seeks the highest quality below the cap. May re-encode images; keeps text and vectors where possible. Requires Ghostscript." };
  document.getElementById("compressionNote").textContent = notes[els.compressMode.value] || notes.targetfit;
}

function refreshTotals() {
  els.count.textContent = String(items.length);
  els.total.textContent = fmtMB(items.reduce((sum, item) => sum + (item.size || 0), 0));
  const count = selectedIds.size;
  els.selectedCount.textContent = `${count} selected`;
  [els.moveTopBtn, els.moveUpBtn, els.moveDownBtn, els.moveBottomBtn].forEach((button) => { button.disabled = count === 0; });
}

async function addFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  let rejected = 0;
  for (const file of files) {
    if (!isPdf(file) && !isImage(file)) { rejected += 1; continue; }
    const kind = isPdf(file) ? "pdf" : "img";
    items.push({ id: genId(), file, name: file.name, size: file.size, lastModified: file.lastModified || 0, kind, thumbUrl: kind === "img" ? URL.createObjectURL(file) : "" });
  }
  els.fileInput.value = "";
  setHint(rejected ? `Ignored ${rejected} unsupported file${rejected === 1 ? "" : "s"}.` : "");
  applyQueueSort(); render(); notifyChange();
}

function clearAll() {
  items.forEach((item) => item.thumbUrl && URL.revokeObjectURL(item.thumbUrl));
  items = []; selectedIds.clear(); lastSelectedIndex = -1;
  setHint(""); setStatus(""); els.progressWrap.classList.add("hidden");
  setBar(els.buildBar, 0, false); setBar(els.compressBar, 0, false); render(); notifyChange();
}

function render() {
  const active = document.activeElement;
  const focusedRow = active?.closest(".item");
  const focusedId = focusedRow?.dataset.id;
  const focusedControl = active?.classList.contains("selectItem") ? ".selectItem" : active?.classList.contains("remove") ? ".remove" : null;
  selectedIds = new Set([...selectedIds].filter((id) => items.some((item) => item.id === id)));
  els.list.replaceChildren(...items.map(makeRow));
  refreshTotals();
  if (focusedId) {
    const row = Array.from(els.list.children).find((entry) => entry.dataset.id === focusedId);
    (focusedControl ? row?.querySelector(focusedControl) : row)?.focus({ preventScroll: true });
  }
}

function pdfThumbnail() {
  return "data:image/svg+xml;utf8," + encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' rx='12' fill='%230b0b0b' stroke='%23333333'/><text x='32' y='38' text-anchor='middle' font-size='18' fill='%23ce79d9' font-family='Arial' font-weight='700'>PDF</text></svg>");
}

function selectItem(id, checked, range) {
  const index = items.findIndex((item) => item.id === id);
  if (index < 0) return;
  if (range && lastSelectedIndex >= 0) {
    const start = Math.min(lastSelectedIndex, index); const end = Math.max(lastSelectedIndex, index);
    for (let i = start; i <= end; i += 1) checked ? selectedIds.add(items[i].id) : selectedIds.delete(items[i].id);
  } else if (checked) selectedIds.add(id);
  else selectedIds.delete(id);
  lastSelectedIndex = index;
  render();
}

function makeRow(item) {
  const row = document.createElement("div");
  row.className = `item${selectedIds.has(item.id) ? " selected" : ""}`;
  row.dataset.id = item.id; row.draggable = true; row.tabIndex = 0;
  row.setAttribute("aria-label", `${item.name}, ${fmtMB(item.size)}`);
  const check = document.createElement("input");
  check.type = "checkbox"; check.className = "selectItem"; check.checked = selectedIds.has(item.id);
  check.setAttribute("aria-label", `Select ${item.name}`);
  check.addEventListener("click", (event) => { event.stopPropagation(); selectItem(item.id, event.target.checked, event.shiftKey); });
  const handle = document.createElement("div");
  handle.className = "handle"; handle.textContent = "⋮⋮"; handle.title = "Drag selected files to reorder";
  const thumb = document.createElement("img");
  thumb.className = "thumb"; thumb.src = item.kind === "img" && item.thumbUrl ? item.thumbUrl : pdfThumbnail(); thumb.alt = "";
  const meta = document.createElement("div"); meta.className = "meta";
  const name = document.createElement("div"); name.className = "name"; name.textContent = item.name; name.title = item.name;
  const sub = document.createElement("div"); sub.className = "sub";
  const badge = document.createElement("span"); badge.className = `badge ${item.kind === "pdf" ? "pdf" : ""}`; badge.textContent = item.kind.toUpperCase();
  const size = document.createElement("span"); size.textContent = fmtMB(item.size || 0); sub.append(badge, size); meta.append(name, sub);
  const remove = document.createElement("button"); remove.className = "remove"; remove.type = "button"; remove.textContent = "Remove";
  remove.addEventListener("click", (event) => { event.stopPropagation(); removeItem(item.id); });
  row.addEventListener("click", (event) => { if (event.target === row || event.target === meta || event.target === name || event.target === sub) selectItem(item.id, !selectedIds.has(item.id), event.shiftKey); });
  row.addEventListener("dblclick", (event) => { if (!event.target.closest("button,input")) removeItem(item.id); });
  row.addEventListener("keydown", (event) => {
    if (event.target !== row) return;
    if (event.key === " " || event.key === "Enter") { event.preventDefault(); selectItem(item.id, !selectedIds.has(item.id), event.shiftKey); }
  });
  row.addEventListener("dragstart", (event) => {
    // Do not re-render here: removing the source node during dragstart cancels
    // native drag-and-drop in Safari and some Chromium builds.
    if (!selectedIds.has(item.id)) selectedIds = new Set([item.id]);
    els.list.querySelectorAll(".item").forEach((entry) => {
      entry.classList.toggle("selected", selectedIds.has(entry.dataset.id));
      entry.querySelector(".selectItem").checked = selectedIds.has(entry.dataset.id);
    });
    refreshTotals();
    dragIds = items.filter((entry) => selectedIds.has(entry.id)).map((entry) => entry.id);
    event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", dragIds.join(","));
    requestAnimationFrame(() => row.classList.add("dragging"));
  });
  row.addEventListener("dragend", () => { dragIds = []; document.querySelectorAll(".dropBefore,.dropAfter,.dragging").forEach((el) => el.classList.remove("dropBefore", "dropAfter", "dragging")); render(); });
  row.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!dragIds.length || dragIds.includes(item.id)) return;
    const rect = row.getBoundingClientRect(); const before = event.clientY - rect.top < rect.height / 2;
    row.classList.toggle("dropBefore", before); row.classList.toggle("dropAfter", !before); event.dataTransfer.dropEffect = "move";
  });
  row.addEventListener("dragleave", () => row.classList.remove("dropBefore", "dropAfter"));
  row.addEventListener("drop", (event) => {
    event.preventDefault(); event.stopPropagation();
    if (!dragIds.length || dragIds.includes(item.id)) return;
    const rect = row.getBoundingClientRect(); moveDraggedTo(item.id, event.clientY - rect.top < rect.height / 2);
  });
  row.append(check, handle, thumb, meta, remove);
  return row;
}

function removeItem(id) {
  const index = items.findIndex((item) => item.id === id);
  if (index < 0) return;
  if (items[index].thumbUrl) URL.revokeObjectURL(items[index].thumbUrl);
  items.splice(index, 1); selectedIds.delete(id); render(); notifyChange();
}

function moveDraggedTo(targetId, before) {
  const moving = items.filter((item) => dragIds.includes(item.id));
  const remaining = items.filter((item) => !dragIds.includes(item.id));
  const targetIndex = remaining.findIndex((item) => item.id === targetId);
  if (targetIndex < 0) return;
  useManualOrder(); remaining.splice(targetIndex + (before ? 0 : 1), 0, ...moving); items = remaining; render(); notifyChange();
}

function moveSelected(direction) {
  if (!selectedIds.size) return;
  useManualOrder();
  const chosen = selectedItems();
  if (direction === "top") items = [...chosen, ...items.filter((item) => !selectedIds.has(item.id))];
  else if (direction === "bottom") items = [...items.filter((item) => !selectedIds.has(item.id)), ...chosen];
  else if (direction === "up") {
    for (let i = 1; i < items.length; i += 1) if (selectedIds.has(items[i].id) && !selectedIds.has(items[i - 1].id)) [items[i - 1], items[i]] = [items[i], items[i - 1]];
  } else if (direction === "down") {
    for (let i = items.length - 2; i >= 0; i -= 1) if (selectedIds.has(items[i].id) && !selectedIds.has(items[i + 1].id)) [items[i], items[i + 1]] = [items[i + 1], items[i]];
  }
  render(); notifyChange();
}

async function startForge() {
  if (!items.length) { setStatus("Add files first."); return; }
  const outputName = normaliseOutputName(els.outName.value); els.outName.value = outputName;
  const targetMb = Number(els.targetMb.value) || 20;
  const splitCount = Math.max(1, Math.min(100, Number.parseInt(els.splitCount.value, 10) || 5)); els.splitCount.value = String(splitCount);
  const options = {
    output_name: outputName, target_mb: targetMb, compress_mode: els.compressMode.value || "lossless",
    linearize: els.linearize.checked, dpi_fallback: 300, split_enabled: els.splitEnabled.checked,
    ...(els.splitEnabled.checked ? { split_count: splitCount } : {}),
  };
  setStatus("Starting…"); els.forgeBtn.disabled = true; els.progressWrap.classList.remove("hidden"); setBar(els.buildBar, 0, true); setBar(els.compressBar, 0, false);
  window.dispatchEvent(new CustomEvent("cometforge:busy", {detail: true}));
  try {
    const formData = new FormData(); items.forEach((item) => formData.append("files", item.file, item.name)); formData.append("options_json", JSON.stringify(options));
    const response = await fetch("/api/forge", { method: "POST", body: formData }); const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.job_id) throw new Error(body.error || "Forge failed.");
    await pollJob(body.job_id, options);
  } catch (error) { setStatus(error?.message || "Forge failed."); }
  finally { els.forgeBtn.disabled = false; setBar(els.buildBar, 1, false); window.dispatchEvent(new CustomEvent("cometforge:busy", {detail: false})); }
}

function filenameFromResponse(response) {
  const value = response.headers.get("content-disposition") || "";
  const utf8 = value.match(/filename\*=UTF-8''([^;]+)/i); const quoted = value.match(/filename="?([^";]+)"?/i);
  try { return utf8 ? decodeURIComponent(utf8[1]) : (quoted?.[1] || "output.pdf"); } catch { return quoted?.[1] || "output.pdf"; }
}
function triggerDownload(url, filename) {
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
}

function closeResults() {
  window.CometForgeComparison?.clear();
  els.previewFrame.removeAttribute("src");
  els.beforeFrame.removeAttribute("src"); els.previewPair.classList.add("hidden");
  els.previewEmpty.classList.remove("hidden");
  resultFiles = []; archiveResult = null; selectedOutput = null;
  els.outputList.replaceChildren(); els.resultsNotice.textContent = ""; els.resultsNotice.classList.remove("warn");
  els.resultsView.classList.add("hidden"); els.queueView.classList.remove("hidden");
}

function selectOutput(file) {
  selectedOutput = file;
  els.previewEmpty.classList.add("hidden"); els.previewPair.classList.remove("hidden");
  els.afterSize.textContent = fmtMB(file.bytes);
  els.beforeSize.textContent = Number.isFinite(file.beforeBytes) ? fmtMB(file.beforeBytes) : "";
  els.afterLabel.textContent = file.pageStart && file.pageEnd ? `After · pages ${file.pageStart}–${file.pageEnd}` : "After · output";
  els.previewFrame.title = `${file.name} after compression`;
  els.beforeFrame.title = `${file.name}, same pages before compression`;
  updateComparison();
  els.outputList.querySelectorAll(".outputFile").forEach((button) => button.classList.toggle("selected", button.dataset.name === file.name));
}

function updateComparison() {
  const compare = els.viewerMode.value === "compare" && Boolean(selectedOutput?.beforeUrl);
  if (compare && selectedOutput?.renderBase && window.CometForgeComparison) {
    els.previewPair.classList.add("hidden");
    els.previewFrame.removeAttribute("src"); els.beforeFrame.removeAttribute("src");
    window.CometForgeComparison.show(selectedOutput, () => {
      els.previewPair.classList.remove("hidden");
      els.beforePane.classList.remove("hidden"); els.previewPair.classList.remove("outputOnly");
      els.previewFrame.src = selectedOutput.previewUrl;
      els.beforeFrame.src = selectedOutput.beforeUrl;
    });
    return;
  }
  window.CometForgeComparison?.clear();
  els.previewPair.classList.remove("hidden");
  if (selectedOutput) els.previewFrame.src = selectedOutput.previewUrl;
  if (els.viewerMode.value === "compare" && selectedOutput && !selectedOutput.beforeUrl) els.resultsNotice.textContent = "This earlier export has no original page comparison. Forge again to compare before and after.";
  els.beforePane.classList.toggle("hidden", !compare);
  els.previewPair.classList.toggle("outputOnly", !compare);
  if (compare) {
    if (els.beforeFrame.getAttribute("src") !== selectedOutput.beforeUrl) els.beforeFrame.src = selectedOutput.beforeUrl;
  } else els.beforeFrame.removeAttribute("src");
}

function showResults(files, archive, message, warning) {
  resultFiles = files; archiveResult = archive;
  els.queueView.classList.add("hidden"); els.resultsView.classList.remove("hidden");
  els.resultsSub.textContent = files.length > 1 ? `${files.length} page-based PDFs are ready. Select one to preview.` : files.length === 1 ? "Your PDF is ready. Select it to preview." : "Your output archive is ready to download.";
  els.resultsNotice.textContent = message || "Choose any file to preview or download it.";
  els.resultsNotice.classList.toggle("warn", Boolean(warning));
  els.outputList.replaceChildren(...files.map((file) => {
    const row = document.createElement("div"); row.className = "outputFile"; row.dataset.name = file.name;
    const open = document.createElement("button"); open.className = "outputOpen"; open.type = "button";
    const title = document.createElement("div"); title.className = "outputFileName"; title.textContent = file.name; title.title = file.name;
    const size = document.createElement("div"); size.className = "outputFileSize"; size.textContent = Number.isFinite(file.beforeBytes) ? `${fmtMB(file.beforeBytes)} → ${fmtMB(file.bytes)}` : fmtMB(file.bytes); open.append(title, size);
    open.addEventListener("click", () => selectOutput(file));
    const download = document.createElement("button"); download.className = "btn small outputDownload"; download.type = "button"; download.textContent = "Download";
    download.addEventListener("click", () => triggerDownload(file.previewUrl, file.name)); row.append(open, download); return row;
  }));
  const hasArchive = Boolean(archive);
  els.downloadAllBtn.classList.toggle("hidden", !hasArchive); if (hasArchive) els.downloadAllBtn.textContent = files.length > 1 ? "Download ZIP" : "Download PDF";
  if (files.length) selectOutput(files[0]);
}

async function loadOutputView(jobId, status, options) {
  const files = (status.outputs || []).map((output, index) => ({
    name: output.name,
    bytes: output.bytes,
    previewUrl: output.preview_url || `/api/job/${jobId}/preview/${index}`,
    beforeUrl: output.before_url || (Number.isFinite(output.before_bytes ?? output.original_bytes) ? `/api/job/${jobId}/before/${index}` : ""),
    beforeBytes: output.before_bytes ?? output.original_bytes,
    pageStart: output.page_start, pageEnd: output.page_end,
    pageCount: output.page_count || (output.page_end && output.page_start ? output.page_end - output.page_start + 1 : 1),
    renderBase: `/api/job/${jobId}/render/${index}`,
  }));
  if (!files.length) throw new Error("Done, but no previewable PDF output was returned.");
  const archive = {
    name: status.download_name || (files.length > 1 ? "CometForge.zip" : files[0].name),
    url: files.length > 1 ? `/api/job/${jobId}/download` : files[0].previewUrl,
  };
  const exceedsTarget = status.target_met === false;
  const guidance = exceedsTarget && options.compress_mode === "lossless"
    ? `At least one PDF exceeds the ${options.target_mb.toFixed(1)} MB target. Choose Target-fit compression and forge again to reduce it.`
    : "Select a PDF to preview it, or use its Download button.";
  showResults(files, archive, guidance, exceedsTarget);
}

async function pollJob(jobId, options) {
  const started = Date.now();
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 250));
    const response = await fetch(`/api/job/${jobId}`); const status = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(status.error || "Job status failed.");
    const elapsed = ((Date.now() - started) / 1000).toFixed(1); const stage = status.stage || "working";
    const part = status.part_count && status.part_index ? `PDF ${status.part_index} of ${status.part_count}` : "";
    const phase = status.detail || status.phase || (stage === "building" ? "Building PDF pages" : stage === "compressing" ? "Optimizing output" : "Preparing export");
    els.partProgress.textContent = [part, phase].filter(Boolean).join(" · ");
    if (stage === "building") { setBar(els.buildBar, (status.progress_build || 0) / 100, true); setStatus(`${[part, phase].filter(Boolean).join(" · ")} (${elapsed}s)`); continue; }
    if (stage === "compressing") { setBar(els.buildBar, 1, false); setBar(els.compressBar, (status.progress_compress || 0) / 100, true); setStatus(`${[part, phase].filter(Boolean).join(" · ")} (${elapsed}s)`); continue; }
    if (stage === "error") { setStatus(status.error || "Job failed."); return; }
    if (stage !== "done") { setStatus(`${stage[0].toUpperCase()}${stage.slice(1)}… (${elapsed}s)`); continue; }
    setBar(els.buildBar, 1, false); setBar(els.compressBar, 1, false);
    const outputCount = Array.isArray(status.outputs) ? status.outputs.length : 0;
    els.partProgress.textContent = `${outputCount} PDF${outputCount === 1 ? "" : "s"} ready · compression complete`;
    const isSplit = outputCount > 1;
    const measuredBytes = status.max_part_bytes || status.output_bytes || 0;
    const parts = [isSplit ? `Done • largest PDF ${fmtMB(measuredBytes)}` : `Done • ${fmtMB(measuredBytes)}`];
    if (typeof status.target_met === "boolean") {
      parts.push(status.target_met ? `within ${options.target_mb.toFixed(1)} MB target` : `over ${options.target_mb.toFixed(1)} MB target`);
    } else if (typeof status.diff_bytes === "number") {
      parts.push(`Δ to ${options.target_mb.toFixed(1)} MB: ${status.diff_bytes >= 0 ? "+" : "-"}${fmtMB(Math.abs(status.diff_bytes))}`);
    }
    if (isSplit) parts.push(`${outputCount} page-based PDFs in a ZIP`);
    if (status.target_met === false && options.compress_mode === "lossless") parts.push("use Target-fit to reduce the largest PDF");
    setStatus(parts.join(" • "));
    try {
      await loadOutputView(jobId, status, options);
      if (status.target_met !== false) window.dispatchEvent(new CustomEvent("cometforge:complete", {detail: {jobId, count: outputCount}}));
    } catch (error) { setStatus(error.message); }
    return;
  }
}

function setupPopupSelect(select) {
  const wrapper = document.createElement("div"); wrapper.className = "popupSelect";
  const trigger = document.createElement("button"); trigger.type = "button"; trigger.className = "popupTrigger"; trigger.id = `${select.id}Trigger`;
  trigger.setAttribute("aria-haspopup", "listbox"); trigger.setAttribute("aria-expanded", "false");
  const label = document.querySelector(`label[for="${select.id}"]`);
  if (label) { label.htmlFor = trigger.id; label.id ||= `${select.id}Label`; trigger.setAttribute("aria-labelledby", label.id); }
  else trigger.setAttribute("aria-label", select.getAttribute("aria-label") || "Choose an option");
  const value = document.createElement("span"); value.className = "popupValue";
  const chevron = document.createElement("span"); chevron.className = "popupChevron"; chevron.setAttribute("aria-hidden", "true");
  chevron.innerHTML = '<svg viewBox="0 0 12 16"><path d="m3 5 3-3 3 3M3 11l3 3 3-3"/></svg>';
  trigger.append(value, chevron);
  const menu = document.createElement("div"); menu.className = "popupMenu hidden"; menu.id = `${select.id}Menu`; menu.setAttribute("role", "listbox");
  menu.setAttribute("aria-label", label?.textContent || select.getAttribute("aria-label") || "Choose an option"); trigger.setAttribute("aria-controls", menu.id);
  const options = Array.from(select.options).map((option) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "popupOption"; button.setAttribute("role", "option"); button.tabIndex = -1;
    const checkmark = document.createElement("span"); checkmark.className = "popupCheck"; checkmark.textContent = "✓"; checkmark.setAttribute("aria-hidden", "true");
    const text = document.createElement("span"); text.textContent = option.text; button.append(checkmark, text);
    button.addEventListener("click", () => { select.value = option.value; select.dispatchEvent(new Event("change", { bubbles: true })); close(true); });
    menu.append(button); return button;
  });
  function sync() {
    value.textContent = select.selectedOptions[0]?.textContent || ""; trigger.title = value.textContent;
    options.forEach((button, i) => button.setAttribute("aria-selected", String(i === select.selectedIndex)));
  }
  function close(focus = false) { menu.classList.add("hidden"); trigger.setAttribute("aria-expanded", "false"); if (focus) trigger.focus(); }
  function open() {
    document.dispatchEvent(new CustomEvent("cometforge:closemenus", { detail: menu.id }));
    menu.classList.remove("hidden"); trigger.setAttribute("aria-expanded", "true");
    const rect = trigger.getBoundingClientRect();
    menu.style.width = "max-content"; menu.style.minWidth = `${rect.width}px`; menu.style.maxWidth = `${window.innerWidth - 16}px`;
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - bounds.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rect.top - select.selectedIndex * 34 - 5, window.innerHeight - bounds.height - 8))}px`;
    options[select.selectedIndex]?.focus({ preventScroll: true });
  }
  trigger.addEventListener("click", () => menu.classList.contains("hidden") ? open() : close(true));
  trigger.addEventListener("keydown", (event) => { if (["ArrowDown", "ArrowUp", " "].includes(event.key)) { event.preventDefault(); open(); } });
  let search = "", searchTime = 0;
  menu.addEventListener("keydown", (event) => {
    const current = options.indexOf(document.activeElement);
    if (event.key === "Escape") { event.preventDefault(); close(true); }
    else if (event.key === "Tab") close(false);
    else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      options[next].focus();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && event.key !== " ") {
      search = Date.now() - searchTime > 700 ? event.key : search + event.key; searchTime = Date.now();
      const match = Array.from(select.options).findIndex((option) => option.text.toLowerCase().startsWith(search.toLowerCase()));
      if (match >= 0) { event.preventDefault(); options[match].focus(); }
    }
  });
  document.addEventListener("pointerdown", (event) => { if (!wrapper.contains(event.target) && !menu.contains(event.target)) close(); });
  document.addEventListener("cometforge:closemenus", (event) => { if (event.detail !== menu.id) close(); });
  window.addEventListener("resize", () => close()); window.addEventListener("scroll", () => close(), true);
  select.addEventListener("change", sync);
  select.before(wrapper); wrapper.append(trigger, select); select.hidden = true; document.body.append(menu); sync();
}

function setupSidebar() {
  const app = document.getElementById("app"), toggle = document.getElementById("sidebarToggle"), content = document.getElementById("sidebarContent");
  let collapsed = false;
  try { collapsed = localStorage.getItem("cometforge:sidebar-collapsed") === "true"; } catch {}
  function sync() {
    app.classList.toggle("sidebarCollapsed", collapsed); content.hidden = collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed)); toggle.title = collapsed ? "Expand settings" : "Collapse settings";
    toggle.querySelector("span").textContent = toggle.title;
  }
  toggle.addEventListener("click", () => { collapsed = !collapsed; try { localStorage.setItem("cometforge:sidebar-collapsed", String(collapsed)); } catch {} sync(); document.dispatchEvent(new CustomEvent("cometforge:closemenus")); });
  sync();
}

els.pickBtn.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", (event) => {
  const files = Array.from(event.target.files || []); event.target.value = "";
  window.CometForgeImport ? window.CometForgeImport.files(files) : addFiles(files);
}); els.clearBtn.addEventListener("click", clearAll); els.forgeBtn.addEventListener("click", startForge);
els.outName.addEventListener("blur", () => { els.outName.value = normaliseOutputName(els.outName.value); });
els.targetMb.addEventListener("input", (event) => updateTarget(event.target.value)); els.targetMbNumber.addEventListener("change", (event) => updateTarget(event.target.value));
els.splitEnabled.addEventListener("change", updateSplitControl);
els.compressMode.addEventListener("change", updateCompressionNote);
els.queueSort.addEventListener("change", () => { applyQueueSort(); render(); notifyChange(); });
[els.targetMb, els.targetMbNumber, els.outName, els.compressMode, els.linearize, els.splitEnabled, els.splitCount].forEach((input) => {
  input.addEventListener("input", notifyChange); input.addEventListener("change", notifyChange);
});
els.moveTopBtn.addEventListener("click", () => moveSelected("top")); els.moveUpBtn.addEventListener("click", () => moveSelected("up")); els.moveDownBtn.addEventListener("click", () => moveSelected("down")); els.moveBottomBtn.addEventListener("click", () => moveSelected("bottom"));
els.closeResultsBtn.addEventListener("click", closeResults);
els.viewerMode.addEventListener("change", updateComparison);
els.downloadAllBtn.addEventListener("click", () => {
  if (archiveResult) triggerDownload(archiveResult.url, archiveResult.name);
});
els.list.addEventListener("dragover", (event) => {
  if (!dragIds.length) return;
  event.preventDefault(); event.dataTransfer.dropEffect = "move";
  const margin = 64;
  if (event.clientY < margin) window.scrollBy(0, -22);
  else if (event.clientY > window.innerHeight - margin) window.scrollBy(0, 22);
});
els.list.addEventListener("drop", (event) => {
  if (event.target.closest(".item") || !dragIds.length) return;
  event.preventDefault();
  const moving = items.filter((item) => dragIds.includes(item.id));
  const remaining = items.filter((item) => !dragIds.includes(item.id));
  useManualOrder(); items = [...remaining, ...moving]; render(); notifyChange();
});
window.CometForge = { getSnapshot, pollJob, startForge, setStatus, setHint, addFiles, showResults, loadOutputView, fmtMB, closeResults, dragActive: () => dragIds.length > 0 };
document.querySelectorAll("select[data-popup-select]").forEach(setupPopupSelect); setupSidebar();
updateTarget(els.targetMb.value); updateSplitControl(); updateCompressionNote(); render();
