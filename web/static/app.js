/* QUILL demo — interactive widget wiring.
   Plain JS, no framework. State machine: idle | generating | done | error. */

"use strict";

// ─────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────
const state = {
  essay: "",
  prompt: "",
  mode: "live",            // "live" | "demo"
  status: "idle",          // "idle" | "generating" | "done" | "error"
  result: null,
  error: null,
  samples: [],
  health: null,
  pendingDemoId: null,     // when user picks a precomputed sample
  abortCtrl: null,
  progressTimer: null,
  progressStartA: 0,
  progressStartB: 0,
};

// ─────────────────────────────────────────────────────────────
// DOM helpers
// ─────────────────────────────────────────────────────────────
const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function setBind(name, valueOrNode) {
  $$(`[data-bind="${name}"]`).forEach(el => {
    if (valueOrNode instanceof Node) {
      el.innerHTML = "";
      el.appendChild(valueOrNode);
    } else {
      el.textContent = valueOrNode == null ? "" : String(valueOrNode);
    }
  });
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ─────────────────────────────────────────────────────────────
// Simple feedback-text renderer.
// Paragraphs separated by blank lines. Inside, recognises:
//   - "Specific corrections noted in your essay:" header → caption + ul
//   - "- 'X' → 'Y' (type)" lines → <li>
//   - "→" anywhere else → styled arrow.
// ─────────────────────────────────────────────────────────────
function renderFeedback(text) {
  const container = document.createElement("div");
  if (!text) {
    container.textContent = "—";
    return container;
  }
  const blocks = text.split(/\n{2,}/);
  for (const blockRaw of blocks) {
    const block = blockRaw.trim();
    if (!block) continue;

    if (/^Specific corrections noted in your essay:/i.test(block)) {
      const head = document.createElement("span");
      head.className = "corrections-head";
      head.textContent = "Specific corrections noted in your essay";
      container.appendChild(head);

      const lines = block.split("\n").slice(1);
      const ul = document.createElement("ul");
      for (const line of lines) {
        const m = line.match(/^\s*[-•]\s*(.+?)\s*$/);
        if (!m) continue;
        const li = document.createElement("li");
        li.innerHTML = renderInlineArrow(m[1]);
        ul.appendChild(li);
      }
      if (ul.childElementCount > 0) container.appendChild(ul);
      continue;
    }

    // Multi-line paragraph (e.g. inline bullet list separated by "\n- ")
    if (/^\s*[-•]\s/m.test(block) && block.includes("\n")) {
      const ul = document.createElement("ul");
      block.split("\n").forEach(line => {
        const m = line.match(/^\s*[-•]\s*(.+?)\s*$/);
        if (m) {
          const li = document.createElement("li");
          li.innerHTML = renderInlineArrow(m[1]);
          ul.appendChild(li);
        }
      });
      if (ul.childElementCount > 0) {
        container.appendChild(ul);
        continue;
      }
    }

    const p = document.createElement("p");
    p.innerHTML = renderInlineArrow(block.replace(/\n/g, " "));
    container.appendChild(p);
  }
  return container;
}

function renderInlineArrow(text) {
  // Escape first, then replace literal arrows with a styled span.
  return escapeHtml(text).replace(/→/g, '<span class="arr">→</span>');
}

// ─────────────────────────────────────────────────────────────
// Render
// ─────────────────────────────────────────────────────────────
function render() {
  // word count
  setBind("essay-words", state.essay.trim().split(/\s+/).filter(Boolean).length);

  // mode help copy
  setBind("mode-help",
    state.mode === "live"
      ? "Live mode runs both conditions against Groq. Expect ~30 seconds for the full pipeline."
      : "Demo mode replays a pre-computed essay from the final experiment. Returns in <1s, no network."
  );
  $$(".mode-toggle button").forEach(btn => {
    const on = btn.dataset.mode === state.mode;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });

  // status pill
  const statusEl = $("#run-status");
  statusEl.classList.remove("is-ok", "is-warn", "is-err");
  let statusText = "Ready.";
  if (state.status === "generating") {
    statusEl.classList.add("is-warn");
    statusText = state.mode === "demo" ? "Loading precomputed…" : "Calling backend…";
  } else if (state.status === "done") {
    statusEl.classList.add("is-ok");
    statusText = "Done.";
  } else if (state.status === "error") {
    statusEl.classList.add("is-err");
    statusText = "Failed.";
  }
  setBind("status-text", statusText);

  // generate button enabled?
  const btn = $("#generate-btn");
  const canSubmit = state.essay.trim().length >= 20 && state.status !== "generating";
  btn.disabled = !canSubmit;

  // initial vs progress
  $("#run-aside-initial").style.display = state.status === "generating" ? "none" : "flex";
  $("#run-progress").classList.toggle("is-on", state.status === "generating");

  // error
  $("#run-error").classList.toggle("is-on", state.status === "error");
  if (state.error) {
    setBind("error-title",
      state.error.code === "rate_limited" ? "Backend rate-limited" :
      state.error.code === "timeout" ? "Timed out" :
      "Backend error");
    setBind("error-message", state.error.message || "Unknown error.");
  }

  // results
  const resultsEl = $("#run-results");
  resultsEl.classList.toggle("is-on", state.status === "done" && state.result);
  if (state.status === "done" && state.result) {
    const r = state.result;
    setBind("result-mode", r.mode_used === "demo" ? "Demo mode · precomputed" : "Live mode · just generated");
    setBind("a-text", renderFeedback(r.a.text));
    setBind("b-text", renderFeedback(r.b.text));
    setBind("a-elapsed", `Elapsed ${r.a.elapsed.toFixed(1)}s`);
    setBind("b-elapsed", `Elapsed ${r.b.elapsed.toFixed(1)}s`);
    const aScoreEl = $('[data-bind="a-score"]');
    const bScoreEl = $('[data-bind="b-score"]');
    if (r.a.overall_score != null) { aScoreEl.textContent = `Score ${r.a.overall_score}/5`; aScoreEl.hidden = false; }
    else                            { aScoreEl.hidden = true; }
    if (r.b.overall_score != null) { bScoreEl.textContent = `Score ${r.b.overall_score}/5`; bScoreEl.hidden = false; }
    else                            { bScoreEl.hidden = true; }

    renderIntermediate(r.intermediate);
  }
}

function renderIntermediate(intermediate) {
  const body = $("#run-intermediate-body");
  body.innerHTML = "";
  const AGENTS = [
    ["A1", "Structure",   "Evaluates organisation, paragraph flow, transitions.",                       false],
    ["A2", "Content",     "Measures prompt adherence, thesis quality, argumentation depth.",          false],
    ["A3", "Language",    "Scores grammar, vocabulary, register — emits original → corrected pairs.",  true ],
    ["A4", "Synthesizer", "Merges A1/A2/A3 evaluations into a coherent student-facing report.",        false],
    ["A5", "Moderator",   "Filters tone, bias, vagueness; produces the final text.",                   false],
  ];
  const keys = ["a1", "a2", "a3", "a4", "a5"];

  AGENTS.forEach(([id, name, role, accent], i) => {
    const node = document.createElement("div");
    node.className = "agent-acc" + (accent ? " is-accent" : "");
    node.innerHTML = `
      <div class="agent-acc__head" role="button" tabindex="0" aria-expanded="false">
        <span class="agent-acc__id">${escapeHtml(id)}</span>
        <span class="agent-acc__name">${escapeHtml(name)}</span>
        <span class="chevron">›</span>
      </div>
      <div class="agent-acc__body"><pre></pre></div>
    `;
    const pre = node.querySelector("pre");
    const data = intermediate?.[keys[i]];
    pre.textContent = data ? JSON.stringify(data, null, 2) : "(no data — agent did not run)";
    const head = node.querySelector(".agent-acc__head");
    head.addEventListener("click", () => toggleAccordion(node));
    head.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleAccordion(node); }
    });
    // Open A3 by default (the differentiator we want to highlight)
    if (accent) toggleAccordion(node, true);
    body.appendChild(node);
  });
}

function toggleAccordion(node, force) {
  const willOpen = force !== undefined ? force : !node.classList.contains("is-open");
  node.classList.toggle("is-open", willOpen);
  node.querySelector(".agent-acc__head").setAttribute("aria-expanded", willOpen ? "true" : "false");
}

// ─────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────
async function loadHealth() {
  try {
    const r = await fetch("/api/health");
    if (!r.ok) throw new Error("health " + r.status);
    state.health = await r.json();
  } catch (e) {
    state.health = { status: "down", backend: "?", api_reachable: false };
  }
  renderHealthPill();
}

function renderHealthPill() {
  const pill = $("#health-pill");
  pill.classList.remove("is-ok", "is-warn", "is-err");
  const h = state.health;
  if (!h) { setBind("health-text", "Checking…"); return; }
  if (h.status === "ok" && h.api_reachable) {
    pill.classList.add("is-ok");
    setBind("health-text", `Backend: ${h.backend} · reachable`);
  } else if (h.precomputed_available) {
    pill.classList.add("is-warn");
    setBind("health-text", `Backend: ${h.backend} · demo only`);
  } else {
    pill.classList.add("is-err");
    setBind("health-text", `Backend: ${h.backend} · offline`);
  }
}

async function loadSamples() {
  try {
    const r = await fetch("/api/samples");
    const data = await r.json();
    state.samples = data.samples || [];
  } catch (_) {
    state.samples = [];
  }
  const select = $("#sample-select");
  // Clear all but the placeholder
  select.querySelectorAll("option:not(:first-child)").forEach(o => o.remove());
  // Group: hand-crafted samples, then precomputed LEAF essays
  const handwritten = state.samples.filter(s => !s.is_precomputed);
  const leaf = state.samples.filter(s => s.is_precomputed);
  if (handwritten.length) {
    const og = document.createElement("optgroup");
    og.label = "Sample essays";
    handwritten.forEach(s => {
      const o = document.createElement("option");
      o.value = s.name;
      o.textContent = `${s.name} · ${s.word_count}w · ${s.preview}…`;
      og.appendChild(o);
    });
    select.appendChild(og);
  }
  if (leaf.length) {
    const og = document.createElement("optgroup");
    og.label = "Pre-run LEAF essays (best for demo mode)";
    leaf.forEach(s => {
      const o = document.createElement("option");
      o.value = s.name;
      o.textContent = `${s.name} · ${s.word_count}w · ${s.preview}…`;
      og.appendChild(o);
    });
    select.appendChild(og);
  }
}

async function loadSample(name) {
  try {
    const r = await fetch(`/api/sample/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error("sample " + r.status);
    const data = await r.json();
    state.essay = data.essay || "";
    state.prompt = data.prompt || "";
    state.pendingDemoId = data.source === "precomputed" ? (data.essay_id || name) : null;
    $("#essay-input").value = state.essay;
    $("#prompt-input").value = state.prompt;
    render();
  } catch (e) {
    console.error("loadSample failed", e);
  }
}

async function submitGenerate() {
  if (state.essay.trim().length < 20) return;
  state.status = "generating";
  state.result = null;
  state.error = null;
  startProgressClock();
  render();
  try {
    const body = {
      essay: state.essay,
      prompt: state.prompt || null,
      mode: state.mode,
      demo_essay_id: state.mode === "demo" ? state.pendingDemoId : null,
    };
    state.abortCtrl = new AbortController();
    const r = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: state.abortCtrl.signal,
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ message: r.statusText }));
      state.status = "error";
      state.error = {
        code: err.error || ("http_" + r.status),
        message: err.message || `Server returned ${r.status}`,
        suggest_demo: err.suggest_demo,
      };
    } else {
      state.result = await r.json();
      state.status = "done";
      // Scroll the results into view after a tick
      setTimeout(() => $("#run-results").scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    }
  } catch (e) {
    if (e.name === "AbortError") {
      state.status = "idle";
    } else {
      state.status = "error";
      state.error = { code: "network", message: e.message || "Network error" };
    }
  } finally {
    stopProgressClock();
    state.abortCtrl = null;
    render();
  }
}

// Progress clock — updates the elapsed timers on screen during generation.
function startProgressClock() {
  state.progressStartA = performance.now();
  state.progressStartB = performance.now();
  $("#prog-a").classList.remove("is-done");
  $("#prog-b").classList.remove("is-done");
  setBind("prog-a-time", "0.0s");
  setBind("prog-b-time", "0.0s");

  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = setInterval(() => {
    // After ~baseline-typical (3s) mark A as "done" visually so users see motion
    const elapsedA = (performance.now() - state.progressStartA) / 1000;
    const elapsedB = (performance.now() - state.progressStartB) / 1000;
    if (elapsedA > 4 && !$("#prog-a").classList.contains("is-done")) {
      $("#prog-a").classList.add("is-done");
      setBind("prog-a-time", `${elapsedA.toFixed(1)}s`);
    } else if (!$("#prog-a").classList.contains("is-done")) {
      setBind("prog-a-time", `${elapsedA.toFixed(1)}s`);
    }
    setBind("prog-b-time", `${elapsedB.toFixed(1)}s`);
  }, 200);
}

function stopProgressClock() {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  $("#prog-a").classList.remove("is-done");
  $("#prog-b").classList.remove("is-done");
}

// ─────────────────────────────────────────────────────────────
// Event wiring
// ─────────────────────────────────────────────────────────────
function wire() {
  // Sticky-nav state
  window.addEventListener("scroll", () => {
    $("#nav").classList.toggle("is-scrolled", window.scrollY > 24);
  }, { passive: true });

  // Sample dropdown
  $("#sample-select").addEventListener("change", (e) => {
    const name = e.target.value;
    if (name) loadSample(name);
  });

  // Inputs
  $("#essay-input").addEventListener("input", (e) => {
    state.essay = e.target.value;
    // typing your own essay clears the demo-id lock from the dropdown
    state.pendingDemoId = null;
    render();
  });
  $("#prompt-input").addEventListener("input", (e) => {
    state.prompt = e.target.value;
  });

  // Mode toggle
  $$(".mode-toggle button").forEach(btn => {
    btn.addEventListener("click", () => {
      if (state.status === "generating") return;
      state.mode = btn.dataset.mode;
      render();
    });
  });

  // Submit
  $("#run-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (state.status === "generating") return;
    submitGenerate();
  });

  // Error → fallback to demo
  $("#error-fallback-btn").addEventListener("click", () => {
    state.mode = "demo";
    state.status = "idle";
    state.error = null;
    render();
    submitGenerate();
  });
  $("#error-dismiss-btn").addEventListener("click", () => {
    state.status = "idle";
    state.error = null;
    render();
  });

  // Intermediate disclosure
  const interToggle = $("#run-intermediate-toggle");
  function toggleInter() {
    const el = $("#run-intermediate");
    const open = !el.classList.contains("is-open");
    el.classList.toggle("is-open", open);
    interToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  interToggle.addEventListener("click", toggleInter);
  interToggle.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleInter(); }
  });
}

// ─────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────
(async function init() {
  wire();
  render();
  await Promise.all([loadHealth(), loadSamples()]);
  render();
})();
