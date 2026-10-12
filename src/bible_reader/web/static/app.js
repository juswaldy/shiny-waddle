"use strict";
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="reader-token"]').content;
let current, sourceInfo, reviewData, allJobs = [], page = 0, requestVersion = 0, noticeTimer, viewedJob;
let pageSize = 40, reviewSaving = false;
const reviewDrafts = new Map(), visibleEditors = new Map();
let visibleRows = [], filteredRows = [];
let contextRow, contextReference, contextPinned = false, contextHideTimer, suppressContextFocus = false;

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
function closeVerseContext(restoreFocus = false) {
  clearTimeout(contextHideTimer);
  const reference = contextReference;
  reference?.setAttribute("aria-expanded", "false");
  $("verse-context").hidden = true;
  contextRow = contextReference = undefined; contextPinned = false;
  if (restoreFocus && reference?.isConnected) {
    suppressContextFocus = true; reference.focus({preventScroll: true}); suppressContextFocus = false;
  }
}
function positionVerseContext() {
  const popup = $("verse-context");
  if (popup.hidden || !contextReference?.isConnected) return;
  const reference = contextReference.getBoundingClientRect();
  const bounds = popup.getBoundingClientRect();
  const width = document.documentElement.clientWidth, height = window.innerHeight;
  const above = reference.top - bounds.height - 10;
  popup.style.left = `${Math.max(12, Math.min(reference.left, width - bounds.width - 12))}px`;
  popup.style.top = `${Math.max(12, Math.min(above >= 12 ? above : reference.bottom + 10, height - bounds.height - 12))}px`;
}
function showVerseContext(row, reference, pinned = false) {
  if (contextPinned && !pinned) return;
  const verse = reviewData?.verses.find(v => v.reference === row.reference);
  if (!verse) return;
  clearTimeout(contextHideTimer);
  contextReference?.setAttribute("aria-expanded", "false");
  contextRow = row; contextReference = reference; contextPinned = pinned;
  reference.setAttribute("aria-expanded", "true");
  const popup = $("verse-context"); popup.dataset.reviewAnchor = row.anchor; popup.dataset.pinned = String(pinned);
  $("verse-context-reference").textContent = row.reference.replaceAll(".", " ");
  $("verse-context-state").textContent = pinned ? "Pinned" : "Click reference to pin";
  const text = $("verse-context-text"); text.replaceChildren();
  let previous;
  for (const token of verse.tokens) {
    const surface = token.source_surface.replaceAll("/", "");
    if (!surface) continue;
    const kind = token.kind;
    if (previous !== undefined && !["x-maqqef", "x-sof-pasuq"].includes(kind) && previous !== "x-maqqef") text.append(" ");
    const highlighted = token.id === row.token_id;
    const word = el(highlighted ? "strong" : "span", surface, `verse-context-token${highlighted ? " verse-context-highlight" : ""}`);
    word.dataset.tokenId = token.id; word.lang = {hbo: "he", arc: "arc", grc: "el"}[token.language] || token.language;
    word.dir = ["hbo", "arc"].includes(token.language) ? "rtl" : "ltr";
    text.append(word);
    if (["ketiv", "qere"].includes(token.reading)) {
      const reading = el("bdi", token.reading, "verse-context-reading"); reading.dir = "ltr"; reading.lang = "en"; text.append(reading);
    }
    previous = kind;
  }
  popup.hidden = false; positionVerseContext();
}
function scheduleVerseContextClose() {
  clearTimeout(contextHideTimer);
  contextHideTimer = setTimeout(() => {
    const popup = $("verse-context");
    if (!contextPinned && !contextReference?.matches(":hover, :focus") && !popup.matches(":hover") && !popup.contains(document.activeElement)) closeVerseContext();
  }, 150);
}
function verseReference(row) {
  const reference = el("button", row.reference.replaceAll(".", " "), "reference verse-reference"); reference.type = "button";
  reference.setAttribute("aria-label", `Verse context for ${row.anchor}`); reference.setAttribute("aria-controls", "verse-context");
  reference.setAttribute("aria-haspopup", "dialog"); reference.setAttribute("aria-expanded", "false");
  reference.addEventListener("mouseenter", () => showVerseContext(row, reference));
  reference.addEventListener("focus", () => {if (!suppressContextFocus) showVerseContext(row, reference);});
  reference.addEventListener("mouseleave", scheduleVerseContextClose); reference.addEventListener("blur", scheduleVerseContextClose);
  reference.addEventListener("click", () => {
    if (contextPinned && contextRow?.anchor === row.anchor) closeVerseContext();
    else showVerseContext(row, reference, true);
  });
  return reference;
}
function tab(name) {
  if (name !== "review") closeVerseContext();
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
    paper: c.layout.paper, "paper-width": c.layout.paper_width_mm ?? 140, "paper-height": c.layout.paper_height_mm ?? 216,
    "verse-layout": c.layout.verse_layout ?? "continuous", "word-colors": c.layout.word_colors ?? "auto", "hebrew-font": c.layout.hebrew_font, "body-pt": c.layout.body_pt, "leading-pt": c.layout.leading_pt,
    "notes-pt": c.layout.notes_pt, folio: c.layout.first_folio, readings: c.readings, cantillation: c.cantillation};
  Object.entries(values).forEach(([id, value]) => { $(id).value = value; });
  document.querySelectorAll("[data-word-class]").forEach(row => {
    const category = row.dataset.wordClass, override = c.layout.word_color_overrides?.[category];
    $("word-color-" + category).value = override === "auto" ? "auto" : override ? "custom" : "preset";
    $("word-color-custom-" + category).value = override && override !== "auto" ? override : row.dataset.presetColor;
  });
  updateWordColorFields();
  updatePaperFields();
  $("frequency").disabled = c.selection !== "book-frequency";
  $("edition-title").textContent = c.name;
  $("edition-subtitle").textContent = `${sourceInfo.books[c.book]?.title || c.book} ${c.passage} · Hebrew text with English lexical helps`;
  $("book-word").textContent = sourceInfo.books[c.book]?.hebrew || "";
}
function updatePaperFields() {
  const custom = $("paper").value === "custom";
  $("custom-paper").hidden = !custom;
  $("paper-width").disabled = $("paper-height").disabled = !custom;
}
function updateWordColorFields() {
  const enabled = $("word-colors").value === "word-class";
  $("word-color-settings").hidden = !enabled;
  document.querySelectorAll("[data-word-class]").forEach(row => {
    const category = row.dataset.wordClass, choice = $("word-color-" + category).value;
    const picker = $("word-color-custom-" + category);
    $("word-color-" + category).disabled = !enabled;
    picker.disabled = !enabled || choice === "auto";
    if (choice !== "custom") picker.value = choice === "auto" ? "#000000" : row.dataset.presetColor;
  });
}
async function loadProject(identity) {
  try {requireSavedReview();} catch (error) {if (current) $("project-picker").value = current.id; throw error;}
  closeVerseContext();
  viewedJob = undefined;
  $("review-edit-result").hidden = true;
  current = await api(`/projects/${identity}`); page = 0; fillForm();
  localStorage.setItem("reader-project", identity);
  await refreshReview(); renderJobs();
}
function formConfig() {
  const c = structuredClone(current.config);
  Object.assign(c, {name: $("project-name").value, book: $("book").value, passage: $("passage").value.trim(), selection: $("selection").value,
    frequency_max: Number($("frequency").value), readings: $("readings").value, cantillation: $("cantillation").value});
  Object.assign(c.layout, {paper: $("paper").value, verse_layout: $("verse-layout").value, word_colors: $("word-colors").value, hebrew_font: $("hebrew-font").value, body_pt: Number($("body-pt").value),
    leading_pt: Number($("leading-pt").value), notes_pt: Number($("notes-pt").value), first_folio: Number($("folio").value)});
  c.layout.word_color_overrides = {};
  document.querySelectorAll("[data-word-class]").forEach(row => {
    const category = row.dataset.wordClass, choice = $("word-color-" + category).value;
    if (choice === "auto") c.layout.word_color_overrides[category] = "auto";
    else if (choice === "custom") c.layout.word_color_overrides[category] = $("word-color-custom-" + category).value.toUpperCase();
  });
  c.layout.word_color_overrides = Object.fromEntries(Object.entries(c.layout.word_color_overrides).sort(([a], [b]) => a.localeCompare(b)));
  if (c.layout.paper === "custom") {
    if (!$("paper-width").reportValidity() || !$("paper-height").reportValidity()) {
      throw new Error("Enter a valid custom paper width and height in millimetres.");
    }
    Object.assign(c.layout, {paper_width_mm: Number($("paper-width").value), paper_height_mm: Number($("paper-height").value)});
  }
  if (c.book !== current.config.book) c.decisions = {};
  return c;
}
async function saveConfig(config) {
  if (JSON.stringify(config) !== JSON.stringify(current.config)) {
    requireSavedReview();
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
    const names = data.rows.filter(row => row.name_excluded).length;
    $("coverage").replaceChildren(...[[data.verse_count, "VERSES"], [data.help_count, "DISTINCT HELPS"], [unresolved, "TO REVIEW"], [names, "NAMES OMITTED"]].map(([value, label]) => {const node = el("div", undefined, "metric"); node.append(el("b", String(value)), el("span", label)); return node;}));
    $("review-intro").textContent = unresolved ? `${unresolved} selected helps need a source-entry choice or explicit omission before export.` : "Every selected help resolves to a source entry. Review wording and meaning in context before publishing your edition.";
    $("review-intro").className = unresolved ? "info-card error" : "info-card";
    renderReview();
  } catch (error) {
    if (version !== requestVersion) return;
    closeVerseContext();
    reviewData = null; visibleRows = []; filteredRows = []; visibleEditors.clear();
    $("review-list").replaceChildren(el("p", "Open Sources to install this book, then refresh the review.", "empty"));
    $("review-intro").textContent = error.message; $("review-intro").className = "info-card error"; $("coverage").replaceChildren();
    updateReviewActions();
  }
}
function initialEdit(row) {
  return {included: row.selected, entry_id: row.entry_id || "", gloss: row.gloss, scope: "book"};
}
function rowEdit(row) { return reviewDrafts.get(row.anchor) || initialEdit(row); }
function nameExcluded(row, edit = rowEdit(row)) {
  const morphology = row.candidates.find(candidate => candidate.id === edit.entry_id)?.morphology || "";
  const analyses = morphology.split("/").map(part => part.trim()).filter(Boolean);
  return Boolean(row.fixed_name_reason) || (analyses.length > 0 && analyses.every(part => part.startsWith("N:")));
}
function requireSavedReview() {
  if (reviewSaving) throw new Error("Wait for the lexical page to finish saving.");
  if (reviewDrafts.size) throw new Error("Save or discard your lexical review edits before changing edition settings, switching projects, or building.");
}
function setDraft(row, value, explicit = false) {
  if (!explicit && JSON.stringify(value) === JSON.stringify(initialEdit(row))) reviewDrafts.delete(row.anchor);
  else reviewDrafts.set(row.anchor, value);
  visibleEditors.get(row.anchor)?.update();
  updateReviewActions();
}
function updateReviewActions() {
  const count = visibleRows.filter(row => reviewDrafts.has(row.anchor)).length;
  const elsewhere = reviewDrafts.size - count;
  $("draft-count").textContent = reviewSaving ? "Saving page…" : reviewDrafts.size ? `${count} unsaved edit${count === 1 ? "" : "s"} on this page${elsewhere ? ` · ${elsewhere} elsewhere` : ""}` : "No unsaved edits";
  $("save-page").disabled = reviewSaving || !count;
  $("save-next").disabled = reviewSaving || !count || (page + 1) * pageSize >= filteredRows.length;
  $("discard-page").disabled = reviewSaving || !count;
  $("include-page").disabled = $("omit-page").disabled = reviewSaving || !visibleRows.length;
  $("previous").disabled = reviewSaving || page === 0;
  $("next").disabled = reviewSaving || (page + 1) * pageSize >= filteredRows.length;
}
function decisionPayload(row) {
  const edit = rowEdit(row), entry = row.candidates.find(candidate => candidate.id === edit.entry_id);
  const gloss = edit.gloss.trim();
  return {anchor: row.anchor, scope: edit.scope, decision: {
    action: edit.included ? "include" : "exclude", entry_id: edit.entry_id || null,
    gloss: gloss && gloss !== entry?.gloss ? gloss : null,
    reason: edit.scope === "book" ? `Edited all occurrences of ${row.consonants} by consonants in ${current.config.book}, from ${row.anchor}` : "Edited in lexical review"
  }};
}
function validateReviewEdits(rows) {
  for (const row of rows) {
    const edit = rowEdit(row);
    if (edit.gloss.length > 1200) throw new Error(`Gloss for ${row.anchor} must be at most 1200 characters.`);
    if ((edit.included || edit.gloss.trim()) && !edit.entry_id) {
      visibleEditors.get(row.anchor)?.choice.focus();
      throw new Error(`Choose a source entry for ${row.reference.replaceAll(".", " ")} (${row.anchor}), or omit the word and leave its gloss empty.`);
    }
  }
}
function showEditResult(result, show) {
  const message = `Saved ${result.applied.length} lexical decision${result.applied.length === 1 ? "" : "s"}`;
  const outcome = $("review-edit-result"); outcome.replaceChildren(el("span", message)); outcome.hidden = !show;
  if (result.skipped.length) {
    outcome.hidden = false;
    outcome.append(el("p", `${result.skipped.length} word references stayed unchanged:`));
    const list = el("ul");
    result.skipped.forEach(item => {
      const li = el("li"); li.append(el("span", `${item.reference.replaceAll(".", " ")} · `));
      const surface = el("bdi", item.source_surface.replaceAll("/", "")); surface.dir = "rtl";
      li.append(surface, el("span", ` · ${item.anchor} · ${item.reason}`)); list.append(li);
    });
    outcome.append(list);
  }
  return message;
}
async function submitReview(rows, {batch = false, next = false} = {}) {
  if (reviewSaving || !rows.length) return;
  validateReviewEdits(rows);
  const edits = rows.map(decisionPayload);
  // Locate the following page by source anchor: resolved/omitted rows may leave the filter after saving.
  const nextAnchor = next ? filteredRows[(page + 1) * pageSize]?.anchor : null;
  reviewSaving = true; updateReviewActions();
  $("review-list").setAttribute("aria-busy", "true");
  const controls = [...document.querySelectorAll("#review-panel input, #review-panel select, #review-panel textarea, #review-panel button")];
  const disabled = controls.map(control => control.disabled);
  controls.forEach(control => {control.disabled = true;});
  try {
    const result = await api(`/projects/${current.id}/decisions${batch ? "/batch" : ""}`, "POST",
      batch ? {revision: current.revision, edits} : {revision: current.revision, ...edits[0]});
    current = result.project;
    rows.forEach(row => reviewDrafts.delete(row.anchor));
    fillForm(); await refreshReview(); renderJobs();
    if (nextAnchor) {
      const index = filteredRows.findIndex(row => row.anchor === nextAnchor);
      if (index >= 0) {page = Math.floor(index / pageSize); renderReview();}
    }
    const message = showEditResult(result, batch || edits.some(edit => edit.scope === "book"));
    notice(batch || edits[0].scope === "book" ? message : "Lexical decision saved");
    if (next) {
      visibleEditors.values().next().value?.gloss.focus();
      $("review-list").scrollIntoView({block: "start"});
    }
  } finally {
    reviewSaving = false;
    controls.forEach((control, index) => {if (control.isConnected) control.disabled = disabled[index];});
    // Refresh replaces row controls; release both the old and newly rendered editors.
    visibleEditors.forEach(editor => editor.update());
    $("review-list").setAttribute("aria-busy", "false"); updateReviewActions();
  }
}
function saveReviewPage(next = false) {
  return submitReview(visibleRows.filter(row => reviewDrafts.has(row.anchor)), {batch: true, next});
}
function moveGloss(anchor, offset) {
  const index = visibleRows.findIndex(row => row.anchor === anchor);
  const target = visibleEditors.get(visibleRows[index + offset]?.anchor)?.gloss;
  if (target) {target.focus(); target.select();}
}
function createReviewChoice(row, field, label, options, radio) {
  const element = el(radio ? "fieldset" : "select", undefined, radio ? "review-choice" : undefined);
  element.setAttribute("aria-label", `${label} for ${row.anchor}`);
  const inputs = [];
  if (radio) element.setAttribute("role", "radiogroup");
  for (const [value, text] of options) {
    if (radio) {
      const option = el("label", undefined, "review-radio");
      const input = el("input"); input.type = "radio"; input.name = `${field}-${row.anchor}`; input.value = value;
      option.append(input, el("span", text)); element.append(option); inputs.push(input);
    } else {
      const option = el("option", text); option.value = value; element.append(option);
    }
  }
  return {element,
    get value() {return radio ? inputs.find(input => input.checked)?.value || "" : element.value;},
    set value(value) {if (radio) inputs.forEach(input => {input.checked = input.value === value;}); else element.value = value;},
    set disabled(value) {if (radio) inputs.forEach(input => {input.disabled = value;}); else element.disabled = value;},
    focus() {(radio ? inputs.find(input => input.checked) || inputs[0] : element)?.focus();}
  };
}
function createReviewEditor(row, grid) {
  const card = el(grid ? "tr" : "article", undefined, "help-row"); card.dataset.anchor = row.anchor;
  const include = el("input"); include.type = "checkbox"; include.setAttribute("aria-label", `Include ${row.reference} ${row.surface}`);
  const word = el("div"); const reference = verseReference(row); word.append(reference);
  const surface = el("div", row.surface, "help-word"); surface.lang = "he"; surface.dir = "rtl"; word.append(surface);
  const source = el("div");
  const sourceLine = el("div", undefined, "row-source");
  const headword = el("span", "", "headword"); headword.lang = "he"; headword.dir = "rtl";
  sourceLine.append(headword, el("small", row.reading === "normal" ? row.lemma : `${row.lemma} · ${row.reading}`)); source.append(sourceLine);
  const choice = createReviewChoice(row, "source-entry", "Source entry",
    [["", grid ? "No source entry selected" : "Choose a source entry…"], ...row.candidates.map(candidate => [candidate.id, `${candidate.gloss} · ${candidate.id}`])], grid);
  if (grid || row.candidates.length > 1 || !row.entry_id) source.append(choice.element);
  const details = el("details"); details.append(el("summary", "Source & selection"));
  details.append(el("div", `${row.reason} · ${row.method} · ${row.morphology} · ${row.book_frequency} occurrences in this book · anchor ${row.anchor}`, "source-detail")); source.append(details);
  const glossBox = el("div", undefined, "help-edit");
  const gloss = el("textarea"); gloss.maxLength = 1200; gloss.rows = 2; gloss.setAttribute("aria-label", `Gloss for ${row.anchor}`); glossBox.append(gloss);
  const tools = el("div", undefined, "gloss-tools");
  const resetSource = el("button", "Source gloss", "text-button"); resetSource.type = "button"; resetSource.setAttribute("aria-label", `Use source gloss for ${row.anchor}`);
  const undo = el("button", "Undo row", "text-button"); undo.type = "button"; undo.setAttribute("aria-label", `Undo edits for ${row.anchor}`);
  tools.append(resetSource, undo); glossBox.append(tools);
  const provenance = el("div", undefined, "gloss-provenance"); glossBox.append(provenance);
  const scopeBox = el("div");
  const scope = createReviewChoice(row, "apply-to", "Apply to",
    [["occurrence", "This occurrence"], ["book", `All ${row.word_occurrences} occurrences in this book (consonants only)`]], grid);
  if (grid) scopeBox.append(scope.element);
  else {const scopeLabel = el("label", "Apply to", "source-detail"); scopeLabel.append(scope.element); scopeBox.append(scopeLabel);}
  const scopeHint = el("p", undefined, "hint"); scopeHint.append(el("span", "Matches "));
  const key = el("bdi", row.consonants); key.dir = "rtl"; key.lang = "he"; scopeHint.append(key);
  scopeHint.append(el("span", " across the book, including other passages and written/read forms. Replaces earlier edits. Occurrences without the chosen source candidate stay unchanged."));
  if (grid) scope.element.title = `Matches \u2067${row.consonants}\u2069 across the book, including other passages and written/read forms. Replaces earlier edits. Occurrences without the chosen source candidate stay unchanged.`;
  else scopeBox.append(scopeHint);
  const actions = el(grid ? "td" : "div", undefined, "help-actions");
  actions.append(el("span", row.label === null ? "—" : String(row.label), "note-label"));
  const status = el("span", "", "row-status"); actions.append(status);
  const save = el("button", "Save help", "secondary"); save.type = "button"; actions.append(save);
  const record = () => setDraft(row, {included: include.checked, entry_id: choice.value, gloss: gloss.value, scope: scope.value});
  include.addEventListener("change", record); gloss.addEventListener("input", record); scope.element.addEventListener("change", record);
  choice.element.addEventListener("change", () => {
    gloss.value = row.candidates.find(candidate => candidate.id === choice.value)?.gloss || "";
    if (nameExcluded(row, {entry_id: choice.value})) include.checked = false;
    record();
  });
  resetSource.addEventListener("click", () => {gloss.value = row.candidates.find(candidate => candidate.id === choice.value)?.gloss || ""; record(); gloss.focus();});
  undo.addEventListener("click", () => {reviewDrafts.delete(row.anchor); renderReview();});
  gloss.addEventListener("keydown", event => {
    if (event.isComposing) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
      event.preventDefault();
      const previous = visibleRows[visibleRows.findIndex(item => item.anchor === row.anchor) - 1];
      if (!previous || !choice.value || rowEdit(previous).entry_id !== choice.value) {
        notice("Copy previous gloss needs two rows with the same chosen source entry.", true); return;
      }
      gloss.value = rowEdit(previous).gloss; record();
    } else if (event.key === "Enter" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault(); moveGloss(row.anchor, event.shiftKey ? -1 : 1);
    }
  });
  gloss.addEventListener("paste", event => {
    const text = event.clipboardData?.getData("text/plain") || "";
    if (!grid || !/[\r\n]/.test(text)) return;
    event.preventDefault();
    const values = text.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n");
    const index = visibleRows.findIndex(item => item.anchor === row.anchor);
    const targets = visibleRows.slice(index, index + values.length);
    if (values.some(value => value.includes("\t") || value.length > 1200) || targets.length !== values.length) {
      notice("Paste one column of glosses, at most 1200 characters each, into rows on the current page.", true); return;
    }
    if (targets.some((target, offset) => values[offset].trim() && !rowEdit(target).entry_id)) {
      notice("Choose a source entry for each destination row before pasting glosses.", true); return;
    }
    targets.forEach((target, offset) => setDraft(target, {...rowEdit(target), gloss: values[offset]}));
    notice(`Pasted ${values.length} glosses. Review them, then save the page.`);
  });
  save.addEventListener("click", guard(() => submitReview([row])));
  if (grid) {
    for (const node of [include, word, source, glossBox, scopeBox]) {const cell = el("td"); cell.append(node); card.append(cell);}
    card.append(actions);
  } else {
    const edit = el("div", undefined, "help-edit"); edit.append(source, glossBox, scopeBox); card.append(include, word, edit, actions);
  }
  const editor = {card, choice, gloss, reference, update() {
    const value = rowEdit(row), entry = row.candidates.find(candidate => candidate.id === value.entry_id);
    include.checked = value.included; choice.value = value.entry_id; gloss.value = value.gloss; scope.value = value.scope;
    headword.textContent = entry?.headword || "—";
    card.classList.toggle("dirty", reviewDrafts.has(row.anchor));
    const excludedName = nameExcluded(row, value);
    status.textContent = reviewDrafts.has(row.anchor) ? "unsaved" : excludedName ? "name omitted" : row.selected ? row.status : "omitted";
    status.classList.toggle("unresolved", value.included && !value.entry_id);
    scopeHint.hidden = value.scope !== "book"; save.textContent = value.scope === "book" ? "Save all" : "Save help";
    provenance.textContent = !entry ? "Choose a source entry" : value.gloss.trim() && value.gloss.trim() !== entry.gloss ? "Editorial wording · STEP source entry" : "STEP source gloss";
    resetSource.disabled = reviewSaving || !entry || value.gloss === entry.gloss;
    undo.disabled = reviewSaving || !reviewDrafts.has(row.anchor);
    save.disabled = reviewSaving;
    for (const field of [include, choice, gloss, scope]) field.disabled = reviewSaving;
    include.disabled = reviewSaving || excludedName;
    include.title = excludedName ? "Names are excluded from lexical helps" : "";
  }};
  visibleEditors.set(row.anchor, editor); editor.update(); return editor;
}
function renderReview() {
  if (!reviewData) return;
  if (!contextPinned) closeVerseContext();
  let pinnedReference;
  const query = $("search").value.toLowerCase();
  const editedOnly = $("edited-only").checked;
  filteredRows = reviewData.rows.filter(row => (editedOnly ? reviewDrafts.has(row.anchor) :
    ($("show-all").checked || row.selected) && (!$("unresolved-only").checked || (row.selected && row.status !== "resolved")) && (!$("resolved-only").checked || row.status === "resolved")) &&
    `${row.surface} ${row.gloss} ${row.reference} ${row.lemma} ${row.entry_id || ""} ${rowEdit(row).gloss}`.toLowerCase().includes(query));
  page = Math.max(0, Math.min(page, Math.ceil(filteredRows.length / pageSize) - 1));
  visibleRows = filteredRows.slice(page * pageSize, (page + 1) * pageSize);
  visibleEditors.clear();
  const grid = $("review-view").value === "grid";
  const fragment = document.createDocumentFragment();
  const table = grid ? el("table", undefined, "review-grid") : null;
  const body = grid ? el("tbody") : fragment;
  if (grid) {
    table.append(el("caption", "Lexical review · edited rows are saved together with Save page"));
    const header = el("thead"), line = el("tr");
    for (const title of ["Include", "Word / verse", "Source entry", "Gloss", "Apply to", "Help / save"]) {const cell = el("th", title); cell.scope = "col"; line.append(cell);}
    header.append(line); table.append(header, body);
  }
  for (const row of visibleRows) {
    const editor = createReviewEditor(row, grid); body.append(editor.card);
    if (contextPinned && contextRow?.anchor === row.anchor) pinnedReference = {row, reference: editor.reference};
  }
  if (grid && visibleRows.length) {const scroll = el("div", undefined, "review-grid-scroll"); scroll.append(table); fragment.append(scroll);}
  if (!filteredRows.length) fragment.append(el("p", "No helps match these filters.", "empty"));
  $("review-list").replaceChildren(fragment);
  if (pinnedReference) showVerseContext(pinnedReference.row, pinnedReference.reference, true);
  else closeVerseContext();
  $("row-count").textContent = filteredRows.length ? `Page ${page + 1} of ${Math.ceil(filteredRows.length / pageSize)} · ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, filteredRows.length)} of ${filteredRows.length} word references` : "0 word references";
  updateReviewActions();
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
$("close-verse-context").onclick = () => closeVerseContext(true);
$("verse-context").addEventListener("mouseenter", () => clearTimeout(contextHideTimer));
$("verse-context").addEventListener("mouseleave", scheduleVerseContextClose);
$("verse-context").addEventListener("focusout", scheduleVerseContextClose);
document.addEventListener("keydown", event => {if (event.key === "Escape" && !$("verse-context").hidden) {event.preventDefault(); closeVerseContext(true);}});
window.addEventListener("resize", positionVerseContext);
document.addEventListener("scroll", positionVerseContext, true);
$("show-sources").onclick = () => tab("sources");
$("project-picker").onchange = guard(() => loadProject($("project-picker").value));
$("project-form").onsubmit = guard(async event => {event.preventDefault(); await saveConfig(formConfig()); notice("Edition settings saved");});
$("selection").onchange = () => { $("frequency").disabled = $("selection").value !== "book-frequency"; };
$("paper").onchange = updatePaperFields;
$("word-colors").onchange = updateWordColorFields;
$("word-colors-clear").onclick = () => {
  document.querySelectorAll("[data-word-class]").forEach(row => {$("word-color-" + row.dataset.wordClass).value = "auto";});
  updateWordColorFields();
  notice("All word classes set to no color. Save settings to keep this palette.");
};
document.querySelectorAll("[data-word-class]").forEach(row => {
  const category = row.dataset.wordClass;
  $("word-color-" + category).onchange = updateWordColorFields;
  $("word-color-custom-" + category).oninput = () => {$("word-color-" + category).value = "custom";};
});
$("book").onchange = () => {if ($("book").value !== "Prov") {$("selection").value = "book-frequency"; $("passage").value = "1:1-10"; $("frequency").disabled = false;}};
$("new-project").onclick = guard(async () => {requireSavedReview(); const config = structuredClone(current.config); config.name = "New reader edition"; const project = await api("/projects", "POST", config); await refreshProjects(project.id);});
$("build").onclick = guard(async () => {requireSavedReview(); viewedJob = undefined; await saveConfig(formConfig()); const job = await api(`/projects/${current.id}/builds`, "POST"); allJobs.unshift(job); tab("preview"); renderJobs();});
$("import-source").onclick = guard(async () => {const job = await api("/sources/import", "POST", {book: $("import-book").value}); allJobs.unshift(job); renderJobs(); notice("Source import queued");});
$("check-environment").onclick = guard(async () => { $("environment").textContent = JSON.stringify(await api("/doctor"), null, 2); });
$("reload-review").onclick = guard(refreshReview);
for (const id of ["search", "show-all", "unresolved-only", "resolved-only", "edited-only"]) $(id).addEventListener("input", () => {
  if (id === "unresolved-only" && $(id).checked) $("resolved-only").checked = false;
  if (id === "resolved-only" && $(id).checked) $("unresolved-only").checked = false;
  page = 0; renderReview();
});
$("previous").onclick = () => {page--; renderReview();}; $("next").onclick = () => {page++; renderReview();};
$("review-view").onchange = () => {localStorage.setItem("reader-review-view", $("review-view").value); renderReview();};
$("review-view").value = localStorage.getItem("reader-review-view") === "grid" ? "grid" : "cards";
$("review-page-size").onchange = () => {pageSize = Number($("review-page-size").value); page = 0; renderReview();};
$("save-page").onclick = guard(() => saveReviewPage());
$("save-next").onclick = guard(() => saveReviewPage(true));
$("discard-page").onclick = () => {visibleRows.forEach(row => reviewDrafts.delete(row.anchor)); renderReview();};
for (const [id, included] of [["include-page", true], ["omit-page", false]]) $(id).onclick = () => {
  visibleRows.forEach(row => {
    if (!nameExcluded(row)) setDraft(row, {...rowEdit(row), included}, true);
  });
};
$("review-panel").addEventListener("keydown", guard(async event => {
  if (!event.isComposing && (event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault(); await saveReviewPage();
  }
}));
window.addEventListener("beforeunload", event => {
  if (reviewDrafts.size || reviewSaving) {event.preventDefault(); event.returnValue = "";}
});
(async () => {try {await refreshSources(); await refreshProjects(localStorage.getItem("reader-project")); await poll();} catch (error) {notice(error.message, true);}})();
