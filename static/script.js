// Runs in your browser: handles uploads (click + drag/drop), talks to app.py,
// renders the AI's results nicely, and shows the two brains side by side.

const $ = (id) => document.getElementById(id);

function selectedEngines() {
  return [...document.querySelectorAll(".engine:checked")].map((c) => c.value);
}

// Colored heading for each result column.
function engineHeader(engine, extra = "") {
  const map = {
    claude: `<span class="dot claude"></span>Claude <span class="tag paid">paid</span>`,
    gpt: `<span class="dot gpt"></span>GPT <span class="tag paid">paid</span>`,
    ollama: `<span class="dot ollama"></span>Ollama <span class="tag free">free</span>`,
  };
  return `<div class="col-head">${map[engine] || engine}<span class="grow"></span>${extra}</div>`;
}

// ---- Upload zones: click to pick OR drag & drop ----
function wireUpload(inputId, previewId, onChange) {
  const input = $(inputId);
  const zone = input.closest(".uploader");

  const show = (file) => {
    if (!file) return;
    const preview = $(previewId);
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
    zone.classList.add("has-file");
    zone.querySelector(".up-main").textContent = file.name;
    zone.querySelector(".up-sub").textContent = "Click or drop to replace";
    onChange();
  };

  input.addEventListener("change", (e) => show(e.target.files[0]));

  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("drag"); }));
  ["dragleave", "dragend"].forEach((ev) =>
    zone.addEventListener(ev, () => zone.classList.remove("drag")));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag");
    if (e.dataTransfer.files[0]) {
      input.files = e.dataTransfer.files;   // keep the file on the input for upload
      show(e.dataTransfer.files[0]);
    }
  });
}

function layoutColumns(container, count) {
  container.classList.remove("two", "three");
  if (count === 2) container.classList.add("two");
  if (count >= 3) container.classList.add("three");
  container.hidden = false;
}

// Show a spinner card for each engine while we wait.
function renderLoading(container, engines, task) {
  container.innerHTML = "";
  engines.forEach((engine) => {
    const div = document.createElement("div");
    div.className = "result";
    const note = engine === "ollama" ? ' <span class="hint">(first run ~30–60s)</span>' : "";
    div.innerHTML = engineHeader(engine) +
      `<div class="loading-row"><span class="spinner tint"></span> ${task}${note}</div>`;
    container.appendChild(div);
  });
  layoutColumns(container, engines.length);
}

// ---------- tiny, safe Markdown -> HTML ----------
function inlineMd(s) {
  return s
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}
function renderMarkdown(md) {
  const lines = escapeHtml(md).split(/\r?\n/);
  let html = "", inUl = false, inOl = false;
  const closeLists = () => {
    if (inUl) { html += "</ul>"; inUl = false; }
    if (inOl) { html += "</ol>"; inOl = false; }
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closeLists(); continue; }

    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {          // # heading
      closeLists(); html += `<h4>${inlineMd(m[2])}</h4>`; continue;
    }
    if ((m = line.match(/^\*\*(.+?)\*\*:?\s*$/))) {        // a line that's all bold = heading
      closeLists(); html += `<h4>${inlineMd(m[1])}</h4>`; continue;
    }
    if ((m = line.match(/^[-*•]\s+(.*)$/))) {              // - bullet
      if (!inUl) { closeLists(); html += "<ul>"; inUl = true; }
      html += `<li>${inlineMd(m[1])}</li>`; continue;
    }
    if ((m = line.match(/^\d+[.)]\s+(.*)$/))) {            // 1. numbered
      if (!inOl) { closeLists(); html += "<ol>"; inOl = true; }
      html += `<li>${inlineMd(m[1])}</li>`; continue;
    }
    closeLists();
    html += `<p>${inlineMd(line)}</p>`;
  }
  closeLists();
  return html;
}

// ---------- STEP 1: instructions ----------
wireUpload("ref1", "ref1Preview", () => { $("analyzeBtn").disabled = false; });

$("analyzeBtn").addEventListener("click", async () => {
  const file = $("ref1").files[0];
  const engines = selectedEngines();
  if (!file) return;
  if (!engines.length) { alert("Tick at least one AI brain at the top."); return; }

  const btn = $("analyzeBtn");
  setLoading(btn, "Thinking…");
  renderLoading($("instructions"), engines, "Reading the photo…");

  const form = new FormData();
  form.append("reference", file);
  form.append("engines", engines.join(","));

  try {
    const res = await fetch("/analyze", { method: "POST", body: form });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const container = $("instructions");
    container.innerHTML = "";
    engines.forEach((engine) => {
      const r = data[engine] || {};
      const div = document.createElement("div");
      div.className = "result" + (r.error ? " error" : "");
      if (r.error) {
        div.innerHTML = engineHeader(engine) + `<div class="error-text">${escapeHtml(r.error)}</div>`;
      } else {
        div.innerHTML =
          engineHeader(engine, `<button class="copy-btn">Copy</button>`) +
          `<div class="md">${renderMarkdown(r.instructions)}</div>`;
        const btnCopy = div.querySelector(".copy-btn");
        btnCopy.addEventListener("click", () => copyText(btnCopy, r.instructions));
      }
      container.appendChild(div);
    });
    layoutColumns(container, engines.length);
  } catch (err) {
    alert("Something went wrong: " + err.message);
    $("instructions").hidden = true;
  } finally {
    resetButton(btn, "Get instructions");
  }
});

// ---------- STEP 2: matching preset ----------
function checkMatchReady() {
  $("matchBtn").disabled = !($("ref2").files[0] && $("mine").files[0]);
}
wireUpload("ref2", "ref2Preview", checkMatchReady);
wireUpload("mine", "minePreview", checkMatchReady);

$("matchBtn").addEventListener("click", async () => {
  const engines = selectedEngines();
  if (!engines.length) { alert("Tick at least one AI brain at the top."); return; }

  const btn = $("matchBtn");
  setLoading(btn, "Building preset…");
  renderLoading($("matchResult"), engines, "Comparing the photos…");

  const form = new FormData();
  form.append("reference", $("ref2").files[0]);
  form.append("mine", $("mine").files[0]);
  form.append("engines", engines.join(","));

  try {
    const res = await fetch("/match", { method: "POST", body: form });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    const container = $("matchResult");
    container.innerHTML = "";
    engines.forEach((engine) => {
      const r = data[engine] || {};
      const div = document.createElement("div");
      div.className = "result" + (r.error ? " error" : "");

      if (r.error) {
        div.innerHTML = engineHeader(engine) + `<div class="error-text">${escapeHtml(r.error)}</div>`;
      } else {
        const blob = new Blob([r.xmp], { type: "application/xml" });
        const url = URL.createObjectURL(blob);
        const fileName = (r.presetName || "Photo Match").replace(/[^\w -]/g, "") + " (" + engine + ").xmp";
        div.innerHTML = engineHeader(engine) +
          `<a class="btn download" href="${url}" download="${fileName}">⬇ Download “${escapeHtml(r.presetName || "preset")}”</a>
           <details class="howto">
             <summary>How to use this preset</summary>
             <ol>
               <li>Click download above to save the <code>.xmp</code>.</li>
               <li>Lightroom Classic → <b>Develop</b> module.</li>
               <li><b>Presets</b> panel → <b>+</b> → <b>Import Presets</b> → pick the file.</li>
               <li>Click your photo, then click the preset (under <b>Photo Match App</b>).</li>
               <li>Apply the tweak notes below by hand.</li>
             </ol>
           </details>
           <div class="tweaks-box"><span class="lbl">Tweak notes</span>${escapeHtml(r.tweaks || "No extra tweaks needed.")}</div>`;
      }
      container.appendChild(div);
    });
    layoutColumns(container, engines.length);
  } catch (err) {
    alert("Something went wrong: " + err.message);
    $("matchResult").hidden = true;
  } finally {
    resetButton(btn, "Build matching preset");
  }
});

// ---------- shared helpers ----------
function setLoading(btn, text) {
  btn.innerHTML = `<span class="spinner"></span>${text}`;
  btn.disabled = true;
}
function resetButton(btn, label) {
  btn.textContent = label;
  btn.disabled = false;
}
function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    const old = btn.textContent;
    btn.textContent = "Copied ✓";
    setTimeout(() => (btn.textContent = old), 1400);
  });
}
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
