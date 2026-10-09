"use strict";
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="reader-token"]').content;
let current, sourceInfo, reviewData, allJobs = [], page = 0, requestVersion = 0, noticeTimer, viewedJob;
const pageSize = 40;

async function api(path, method = "GET", body) {
  const response = await fetch(`/api${path}`, {method, headers: {"Content-Type": "application/json", "X-Reader-Token": csrf}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(e => `${e.loc.slice(1).join(".")}: ${e.msg}`).join("; ") : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}
function notice(message, error = false) {
  clearTimeout(noticeTimer); $("notice").textContent = message; $("notice").className = error ? "error" : ""; $("notice").hidden = false;
  noticeTimer = setTimeout(() => { $("notice").hidden = true; }, error ? 12000 : 4500);
}
function guard(action) { return async event => { try { await action(event); } catch (error) { notice(error.message, true); } }; }
function el(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function tab(name) {
  for (const n of ["review", "preview", "sources"]) $(`${n}-panel`).hidden = n !== name;
  document.querySelectorAll("[data-tab]").forEach(button => button.classList.toggle("active", button.dataset.tab === name));
}
async function refreshSources() {
  sourceInfo = await api("/sources");
  for (const id of ["book", "import-book"]) {
    const selected = $(id).value;
    $(id).replaceChildren();
    Object.entries(sourceInfo.books).forEach(([code, book]) => {
      const option = el("option", `${book.title}${sourceInfo.installed.includes(code) ? " · installed" : ""}`); option.value = code; $(id).append(option);
    });
    $(id).value = selected || "Prov";
  }
  $("source-status").textContent = `${sourceInfo.installed.length} books installed · ${sourceInfo.lexicon ? "Short-gloss lexicon installed" : "Lexicon not installed"}`;
  $("source-credits").replaceChildren(...sourceInfo.attributions.map(n => el("p", n)));
}
async function refreshProjects(selected) {
  const projects = await api("/projects");
  $("project-picker").replaceChildren(...projects.map(p => {const option = el("option", p.config.name); option.value = p.id; return option;}));
  const identity = projects.some(p => p.id === selected) ? selected : projects[0]?.id;
  if (identity) { $("project-picker").value = identity; await loadProject(identity); }
}
function fillForm() {
  const c = current.config;
  const values = {"project-name": c.name, book: c.book, passage: c.passage, selection: c.selection, frequency: c.frequency_max,
    paper: c.layout.paper, "verse-layout": c.layout.verse_layout ?? "continuous", "hebrew-font": c.layout.hebrew_font, "body-pt": c.layout.body_pt, "leading-pt": c.layout.leading_pt,
    "notes-pt": c.layout.notes_pt, folio: c.layout.first_folio, readings: c.readings, cantillation: c.cantillation};
  Object.entries(values).forEach(([id, value]) => { $(id).value = value; });
  $("frequency").disabled = c.selection !== "book-frequency";
  $("edition-title").textContent = c.name;
  $("edition-subtitle").textContent = `${sourceInfo.books[c.book]?.title || c.book} ${c.passage} · Hebrew text with English lexical helps`;
  $("book-word").textContent = sourceInfo.books[c.book]?.hebrew || "";
}
async function loadProject(identity) {
  viewedJob = undefined;
  current = await api(`/projects/${identity}`); page = 0; fillForm();
  localStorage.setItem("reader-project", identity);
  await refreshReview(); renderJobs();
}
function formConfig() {
  const c = structuredClone(current.config);
  Object.assign(c, {name: $("project-name").value, book: $("book").value, passage: $("passage").value.trim(), selection: $("selection").value,
    frequency_max: Number($("frequency").value), readings: $("readings").value, cantillation: $("cantillation").value});
  Object.assign(c.layout, {paper: $("paper").value, verse_layout: $("verse-layout").value, hebrew_font: $("hebrew-font").value, body_pt: Number($("body-pt").value),
    leading_pt: Number($("leading-pt").value), notes_pt: Number($("notes-pt").value), first_folio: Number($("folio").value)});
  if (c.book !== current.config.book) c.decisions = {};
  return c;
}
async function saveConfig(config) {
  if (JSON.stringify(config) !== JSON.stringify(current.config)) {
    current = await api(`/projects/${current.id}`, "PUT", {revision: current.revision, config});
    const option = $("project-picker").selectedOptions[0]; if (option) option.textContent = config.name;
  }
  fillForm(); await refreshReview(); renderJobs();
}
async function refreshReview() {
  if (!current) return;
  const version = ++requestVersion;
  $("review-intro").textContent = "Loading source text and lexical helps…";
  $("review-intro").className = "info-card";
  try {
    const data = await api(`/projects/${current.id}/review`);
    if (version !== requestVersion) return;
    reviewData = data;
    const unresolved = (data.coverage.ambiguous || 0) + (data.coverage.unmatched || 0);
    $("coverage").replaceChildren(...[[data.verse_count, "VERSES"], [data.help_count, "DISTINCT HELPS"], [unresolved, "TO REVIEW"]].map(([value, label]) => {const node = el("div", undefined, "metric"); node.append(el("b", String(value)), el("span", label)); return node;}));
    $("review-intro").textContent = unresolved ? `${unresolved} selected helps need a source-entry choice or explicit omission before export.` : "Every selected help resolves to a source entry. Review wording and meaning in context before publishing your edition.";
    $("review-intro").className = unresolved ? "info-card error" : "info-card";
    renderReview();
  } catch (error) {
    if (version !== requestVersion) return;
    reviewData = null; $("review-list").replaceChildren(el("p", "Open Sources to install this book, then refresh the review.", "empty"));
    $("review-intro").textContent = error.message; $("review-intro").className = "info-card error"; $("coverage").replaceChildren();
  }
}
function renderReview() {
  if (!reviewData) return;
  const query = $("search").value.toLowerCase();
  const rows = reviewData.rows.filter(r => ($("show-all").checked || r.selected) && (!$("unresolved-only").checked || (r.selected && r.status !== "resolved")) && `${r.surface} ${r.gloss} ${r.reference} ${r.lemma}`.toLowerCase().includes(query));
  page = Math.max(0, Math.min(page, Math.ceil(rows.length / pageSize) - 1));
  const fragment = document.createDocumentFragment();
  for (const row of rows.slice(page * pageSize, (page + 1) * pageSize)) {
    const card = el("article", undefined, "help-row"); card.dataset.anchor = row.anchor;
    const include = el("input"); include.type = "checkbox"; include.checked = row.selected; include.setAttribute("aria-label", `Include ${row.reference} ${row.surface}`);
    const word = el("div"); word.append(el("div", row.reference.replaceAll(".", " "), "reference"));
    const surface = el("div", row.surface, "help-word"); surface.lang = "he"; surface.dir = "rtl"; word.append(surface);
    const edit = el("div", undefined, "help-edit");
    const source = el("div", undefined, "row-source");
    const chosen = row.candidates.find(c => c.id === row.entry_id);
    const headword = el("span", chosen?.headword || "—", "headword"); headword.lang = "he"; headword.dir = "rtl";
    source.append(headword, el("small", row.reading === "normal" ? row.lemma : `${row.lemma} · ${row.reading}`)); edit.append(source);
    const choice = el("select"); choice.setAttribute("aria-label", `Source entry for ${row.anchor}`);
    const blank = el("option", "Choose a source entry…"); blank.value = ""; choice.append(blank);
    row.candidates.forEach(c => { const o = el("option", `${c.gloss} · ${c.id}`); o.value = c.id; choice.append(o); });
    choice.value = row.entry_id || ""; if (row.candidates.length > 1 || !row.entry_id) edit.append(choice);
    const gloss = el("textarea"); gloss.value = row.gloss; gloss.maxLength = 1200; gloss.setAttribute("aria-label", `Gloss for ${row.anchor}`); edit.append(gloss);
    choice.addEventListener("change", () => {const c = row.candidates.find(c => c.id === choice.value); gloss.value = c?.gloss || ""; headword.textContent = c?.headword || "—";});
    const details = el("details"); details.append(el("summary", "Source & selection")); details.append(el("div", `${row.reason} · ${row.method} · ${row.morphology} · ${row.book_frequency} occurrences in this book · anchor ${row.anchor}`, "source-detail")); edit.append(details);
    const actions = el("div", undefined, "help-actions"); actions.append(el("span", row.label === null ? "—" : String(row.label), "note-label"));
    actions.append(el("span", row.selected ? row.status : "omitted", `row-status${row.selected && row.status !== "resolved" ? " unresolved" : ""}`));
    const save = el("button", "Save help", "secondary");
    save.addEventListener("click", guard(async () => {
      const config = structuredClone(current.config); const entry = row.candidates.find(c => c.id === choice.value);
      config.decisions[row.anchor] = {action: include.checked ? "include" : "exclude", entry_id: choice.value || null,
        gloss: gloss.value.trim() && gloss.value.trim() !== entry?.gloss ? gloss.value.trim() : null, reason: "Edited in lexical review"};
      save.disabled = true;
      try { await saveConfig(config); notice("Lexical decision saved"); } finally { save.disabled = false; }
    }));
    actions.append(save); card.append(include, word, edit, actions); fragment.append(card);
  }
  if (!rows.length) fragment.append(el("p", "No helps match these filters.", "empty"));
  $("review-list").replaceChildren(fragment);
  $("row-count").textContent = rows.length ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, rows.length)} of ${rows.length} word references` : "0 word references";
  $("previous").disabled = page === 0; $("next").disabled = (page + 1) * pageSize >= rows.length;
}
function showBuild(job) {
  const result = job.result;
  const stale = current && job.project_revision !== current.revision;
  $("build-status").className = "info-card";
  $("build-status").textContent = `${result.reader_pages} reader page${result.reader_pages === 1 ? "" : "s"} + source credits · ${result.verse_count} verses · ${result.help_count} helps${stale ? " · Earlier project revision — rebuild to include your latest edits." : " · Current saved edition"}`;
  for (const [id, file] of [["download-pdf", "reader.pdf"], ["download-bundle", "reader-bundle.zip"]]) {
    $(id).href = `/api/jobs/${job.id}/artifacts/${file}?download=true`; $(id).hidden = false;
  }
  const url = `/api/jobs/${job.id}/artifacts/reader.pdf`;
  if ($("pdf-preview").getAttribute("src") !== url) $("pdf-preview").src = url;
  $("pdf-preview").hidden = false;
}
function renderJobs() {
  if (!current) return;
  const builds = allJobs.filter(j => j.kind === "build" && j.project_id === current.id);
  const active = builds.find(j => ["queued", "running"].includes(j.status));
  $("cancel-build").hidden = !active; $("build").disabled = Boolean(active);
  $("cancel-build").onclick = active ? guard(async () => { await api(`/jobs/${active.id}/cancel`, "POST"); notice("Cancellation requested"); }) : null;
  const latest = builds.find(j => j.id === viewedJob) || builds[0];
  if (latest?.status !== "succeeded") {
    $("pdf-preview").hidden = true; $("pdf-preview").removeAttribute("src");
    $("download-pdf").hidden = true; $("download-bundle").hidden = true;
  }
  if (latest?.status === "succeeded") showBuild(latest);
  else if (latest) {
    $("build-status").textContent = ["failed", "interrupted"].includes(latest.status) ? latest.error : `${latest.status === "cancelled" ? "Build cancelled" : latest.stage || "Build queued"}`;
    $("build-status").className = ["failed", "interrupted"].includes(latest.status) ? "info-card error" : "info-card";
  } else {
    $("build-status").textContent = "Build a reader to preview the actual PDF here.";
    $("pdf-preview").hidden = true; $("download-pdf").hidden = true; $("download-bundle").hidden = true;
  }
  $("build-history").replaceChildren(...builds.slice(0, 8).map(job => {
    const row = el("div", undefined, "history-row"); row.append(el("span", `${new Date(job.created).toLocaleString()} · ${job.status}`));
    if (job.status === "succeeded") {const button = el("button", "View edition", "text-button"); button.onclick = () => {viewedJob = job.id; showBuild(job);}; row.append(button);} return row;
  }));
  const importJob = allJobs.find(j => j.kind === "import");
  if (importJob && ["running", "queued", "failed"].includes(importJob.status)) {
    $("source-status").textContent = importJob.status === "failed" ? importJob.error : importJob.stage || "Import queued…";
  }
}
async function poll() {
  try {
    const previous = new Map(allJobs.map(j => [j.id, j.status])); allJobs = await api("/jobs");
    if (allJobs.some(j => j.kind === "import" && j.status === "succeeded" && previous.get(j.id) !== "succeeded")) {await refreshSources(); if (current) {fillForm(); await refreshReview();}}
    renderJobs();
  } catch (error) { notice(`Connection lost. Retrying… ${error.message}`, true); }
  setTimeout(poll, 1400);
}
document.querySelectorAll("[data-tab]").forEach(button => button.onclick = () => tab(button.dataset.tab));
$("show-sources").onclick = () => tab("sources");
$("project-picker").onchange = guard(() => loadProject($("project-picker").value));
$("project-form").onsubmit = guard(async event => {event.preventDefault(); await saveConfig(formConfig()); notice("Edition settings saved");});
$("selection").onchange = () => { $("frequency").disabled = $("selection").value !== "book-frequency"; };
$("book").onchange = () => {if ($("book").value !== "Prov") {$("selection").value = "book-frequency"; $("passage").value = "1:1-10"; $("frequency").disabled = false;}};
$("new-project").onclick = guard(async () => {const config = structuredClone(current.config); config.name = "New reader edition"; const project = await api("/projects", "POST", config); await refreshProjects(project.id);});
$("build").onclick = guard(async () => {viewedJob = undefined; await saveConfig(formConfig()); const job = await api(`/projects/${current.id}/builds`, "POST"); allJobs.unshift(job); tab("preview"); renderJobs();});
$("import-source").onclick = guard(async () => {const job = await api("/sources/import", "POST", {book: $("import-book").value}); allJobs.unshift(job); renderJobs(); notice("Source import queued");});
$("check-environment").onclick = guard(async () => { $("environment").textContent = JSON.stringify(await api("/doctor"), null, 2); });
$("reload-review").onclick = guard(refreshReview);
for (const id of ["search", "show-all", "unresolved-only"]) $(id).addEventListener("input", () => {page = 0; renderReview();});
$("previous").onclick = () => {page--; renderReview();}; $("next").onclick = () => {page++; renderReview();};
(async () => {try {await refreshSources(); await refreshProjects(localStorage.getItem("reader-project")); await poll();} catch (error) {notice(error.message, true);}})();
