import { t, lang, setLang } from "./i18n.js";
import {
  THEMES,
  recommendedGeometry,
  scoreKind,
  currentTheme,
  shotNumber as displayShotNumber,
} from "./editor-data.js";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const id = () => crypto.randomUUID().replaceAll("-", "");
const clone = (v) => structuredClone(v);
const fmt = (v) =>
  `${Math.floor((v || 0) / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor((v || 0) % 60)
    .toString()
    .padStart(2, "0")}`;
const S = {
  p: null,
  totals: null,
  history: {},
  provider: { configured: false, source: "none" },
  remoteQuery: "",
  remoteResults: null,
  remoteLoading: false,
  projects: [],
  courses: [],
  jobs: [],
  view: "editor",
  tab: "round",
  shot: null,
  overlay: null,
  time: 0,
  zoom: 1,
  source: null,
  saving: false,
  conflict: false,
  chain: Promise.resolve(),
};
const icons = { editor: "▣", courses: "⚑", rounds: "▦", exports: "↗" };
const clubs = [
  "Driver",
  "3 Wood",
  "5 Wood",
  "3 Hybrid",
  "4 Hybrid",
  "3 Iron",
  "4 Iron",
  "5 Iron",
  "6 Iron",
  "7 Iron",
  "8 Iron",
  "9 Iron",
  "PW",
  "GW",
  "SW",
  "LW",
  "Putter",
];
const style = () => ({
  ...recommendedGeometry("shot", S.p?.video),
  ...THEMES.broadcast,
  opacity: 0.9,
  overlay_opacity: 1,
  radius: 14,
  font_size: 24,
  font: "sans",
  panel: true,
  show_course: true,
});
async function api(path, options = {}) {
  const r = await fetch("/api/v1" + path, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!r.ok) {
    let msg = await r.text();
    try {
      const d = JSON.parse(msg).detail;
      msg = typeof d === "string" ? t(d) : JSON.stringify(d);
    } catch {}
    if (
      r.status === 409 &&
      path.startsWith("/projects/") &&
      options.method === "PUT"
    ) {
      S.conflict = true;
      msg = t("conflict");
    }
    throw Error(msg);
  }
  return r.json();
}
function notice(message, error = false) {
  $("#notice").innerHTML =
    `<span>${esc(message)}</span><button data-action="dismiss" aria-label="${t("dismiss")}">×</button>`;
  $("#notice").className = error ? "notice error" : "notice";
  $("#notice").hidden = false;
  if (!error) setTimeout(() => ($("#notice").hidden = true), 5000);
}
function error(e) {
  notice(e.message || e, true);
}
function downloadJSON(value, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function setProject(data) {
  S.p = data.project;
  S.history = data.history || {};
  S.totals = data.totals;
  S.overrides = data.overrides || [];
  localStorage.setItem("gvs-project", S.p.id);
  render();
}
async function refreshProjects() {
  S.projects = await api("/projects");
  renderSidebar();
}
async function loadProject(pid) {
  await S.chain;
  if (S.conflict) return notice(t("conflict"), true);
  setProject(await api(`/projects/${pid}`));
}
function change(fn) {
  const task = S.chain.then(async () => {
    if (S.conflict) throw Error(t("conflict"));
    const p = clone(S.p);
    fn(p);
    S.saving = true;
    renderStatus();
    try {
      const data = await api(`/projects/${p.id}`, {
        method: "PUT",
        body: JSON.stringify(p),
      });
      setProject(data);
    } catch (e) {
      if (S.conflict) S.p = p;
      throw e;
    } finally {
      S.saving = false;
      renderStatus();
    }
  });
  S.chain = task.catch(() => {});
  task.catch(error);
  return task;
}
function button(action, label, css = "", extra = "") {
  return `<button class="${css}" data-action="${action}" ${extra}>${label}</button>`;
}
function field(label, key, value, type = "text", extra = "", scope = "round") {
  if (type === "number" && typeof value === "number")
    value = Number(value.toFixed(4));
  return `<label class="field"><span>${t(label)}</span><input type="${type}" data-scope="${scope}" data-key="${key}" value="${esc(value)}" ${extra}></label>`;
}
function select(label, key, value, options, scope) {
  return `<label class="field"><span>${t(label)}</span><select data-scope="${scope}" data-key="${key}">${options.map(([v, k]) => `<option value="${v}" ${v === value ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>`;
}
function shell() {
  document.documentElement.lang = lang;
  $("#app").innerHTML = `
<aside class="sidebar"><a class="brand" href="#"><span class="brand-mark">⚑</span><div>${t("brand")}<b>${t("studio")}<i>®</i></b></div></a><p class="eyebrow">${t("workspace")}</p><nav>${Object.keys(
    icons,
  )
    .map((k) =>
      button(
        "view",
        `<span>${icons[k]}</span>${t(k)}`,
        "nav",
        `data-view="${k}"`,
      ),
    )
    .join(
      "",
    )}</nav><div class="project-head"><span class="eyebrow">${t("projects")}</span>${button("new", "+", "icon", `aria-label="${t("newProject")}"`)}</div><div id="projects"></div><button class="new-project" data-action="new">＋ ${t("newProject")}</button><div class="sidebar-footer"><span class="online-dot"></span>${t("local")}<p>${t("private")}</p>${button("project-trash", t("projectTrash"), "text-button")}${button("help", t("help"), "text-button")}</div></aside>
<div class="app-main"><header class="topbar"><div class="breadcrumb">${t("workspace")}<span>/</span><input id="project-name" aria-label="${t("projectName")}"></div><div class="top-actions"><span id="save-status"></span>${button("delete-project", t("deleteProject"), "subtle danger")}<select id="language" aria-label="${t("language")}"><option value="ko" ${lang === "ko" ? "selected" : ""}>한국어</option><option value="en" ${lang === "en" ? "selected" : ""}>EN</option></select>${button("export", `↗ &nbsp;${t("export")}`, "primary")}</div></header>
<div class="workspace-body"><main><section id="studio-view"><div class="section-head"><div><span class="eyebrow">${t("preview")}</span><h1 id="video-title">${t("noVideo")}</h1></div><span id="metadata"></span></div><div class="preview-well"><div id="empty-preview"><div class="empty-copy"><span class="pill">GOLF VIDEO STUDIO / 01</span><h2>${t("emptyTitle")}</h2><p>${t("emptyDesc")}</p>${button("upload", `＋ &nbsp; ${t("choose")}`, "primary large")}<small>${t("formats")}</small></div><span class="art-label">${t("sample")}</span></div><div id="video-box" hidden><video id="video" playsinline preload="metadata"></video><div id="overlay-layer"></div></div></div><div class="playback"><span id="video-meta"></span><div>${button("prev", "│◀", "icon", `aria-label="${t("prevFrame")}"`)}${button("play", "▶", "play-button", `aria-label="${t("play")}"`)}${button("next", "▶│", "icon", `aria-label="${t("nextFrame")}"`)}</div><span id="time">00:00 / 00:00</span></div><div id="onboarding" class="onboarding">${["step1", "step2", "step3"].map((k, i) => `<div><b>0${i + 1}</b><span>${t(k)}</span><i>${i === 0 ? "↗" : i === 1 ? "▦" : "✓"}</i></div>`).join("")}</div>
<div class="timeline"><div class="timeline-head"><span class="eyebrow">${t("timeline")}</span><div>${button("add-shot", `＋ ${t("addShot")}`, "subtle")}${button("add-card", `＋ ${t("addCard")}`, "subtle")}<label class="zoom">− <input id="zoom" type="range" min="1" max="8" value="${S.zoom}" aria-label="${t("zoom")}"> ＋</label></div></div><input id="seek" type="range" min="0" max="1" step=".001" value="0" aria-label="${t("seek")}"><div class="timeline-scroll"><div id="tracks"></div></div><p class="timeline-help">${t("markers")}</p></div><div class="shotlist-head"><span class="eyebrow">${t("shotList")}</span><span id="shot-count"></span></div><div id="shot-list"></div></section><section id="courses-view" hidden></section><section id="rounds-view" hidden></section><section id="exports-view" hidden></section></main><aside class="inspector"><div class="inspector-head"><span class="eyebrow">${t("inspector")}</span><span>☷</span></div><div class="tabs">${["round", "shot", "design"].map((k) => button("tab", t(k), "", `data-tab="${k}"`)).join("")}</div><div id="inspector-content"></div></aside></div></div><div id="notice" hidden></div><input hidden type="file" id="video-file" accept=".mp4,.mov,.webm"><input hidden type="file" id="csv-file" accept=".csv"><input hidden type="file" id="reference-file" accept=".png,.jpg,.jpeg,.pdf"><input hidden type="file" id="course-file" accept=".json"><dialog id="dialog"></dialog>`;
  $("#video").addEventListener("timeupdate", tick);
  $("#video").addEventListener("seeked", tick);
  $("#video").addEventListener("play", () => {
    updatePlay();
    animate();
  });
  $("#video").addEventListener("pause", updatePlay);
  $("#video").addEventListener("ended", updatePlay);
  $("#video").addEventListener("error", () =>
    notice(t("fileUnsupported"), true),
  );
  $("#video").addEventListener("loadedmetadata", fitVideo);
  new ResizeObserver(fitVideo).observe($(".preview-well"));
  render();
}
function renderStatus() {
  $("#save-status").innerHTML =
    `<i class="${S.saving ? "saving" : "saved"}"></i>${t(S.saving ? "saving" : "saved")}`;
}
function renderSidebar() {
  $("#projects").innerHTML = S.projects
    .map((p) =>
      button(
        "project",
        `<span>▤</span><span>${esc(p.name)}</span>`,
        "project " + (p.id === S.p?.id ? "selected" : ""),
        `data-id="${p.id}"`,
      ),
    )
    .join("");
  $$('[data-action="view"]').forEach((b) =>
    b.classList.toggle("active", b.dataset.view === S.view),
  );
}
function render() {
  if (!$("#studio-view")) return;
  renderStatus();
  renderSidebar();
  for (const v of ["editor", "courses", "rounds", "exports"])
    $("#" + (v === "editor" ? "studio" : v) + "-view").hidden = S.view !== v;
  if (!S.p) return;
  const p = S.p;
  $("#project-name").value = p.name;
  $("#video-title").textContent = p.video?.filename || t("noVideo");
  $("#empty-preview").hidden = !!p.video;
  $("#video-box").hidden = !p.video;
  $("#onboarding").hidden = !!p.video;
  $("#metadata").textContent = p.video
    ? `${p.video.width} × ${p.video.height}  ·  ${p.video.fps.toFixed(2)} FPS`
    : "";
  $("#video-meta").textContent = p.video
    ? (p.video.has_audio ? "◖))  " : "") + t("fit")
    : t("noVideo");
  if (S.source !== p.id && p.video) {
    S.source = p.id;
    $("#video").src = `/api/v1/projects/${p.id}/video`;
  } else if (!p.video) {
    S.source = null;
    $("#video").removeAttribute("src");
  }
  $("#seek").max = p.video?.duration || 1;
  renderInspector();
  renderTimeline();
  renderShots();
  renderGraphics();
  if (S.view === "rounds") renderRound();
  if (S.view === "courses") renderCourses();
  if (S.view === "exports") renderExports();
  tick();
  fitVideo();
}
function historyBar(scope) {
  const counts = S.history[scope] || { undo: 0, redo: 0 };
  return `<section class="history-panel"><div class="history-actions" role="group" aria-label="${t(scope)} ${t("editHistory")}">${button("history-undo", `↶ ${t("undoLabel")}`, "outline", `data-scope="${scope}" ${counts.undo ? "" : "disabled"} title="${t("undo")}"`)}${button("history-redo", `↷ ${t("redoLabel")}`, "outline", `data-scope="${scope}" ${counts.redo ? "" : "disabled"} title="${t("redo")}"`)}${button("history-reset", t("resetLabel"), "subtle", `data-scope="${scope}" title="${t("reset_" + scope)}"`)}</div><p class="inspector-note">${t("historyHelp")}</p></section>`;
}
function commitHistory(action, scope) {
  const task = S.chain.then(async () => {
    if (S.conflict) throw Error(t("conflict"));
    const p = S.p;
    if (!p || (action !== "reset" && !S.history[scope]?.[action])) return;
    S.saving = true;
    renderStatus();
    try {
      setProject(
        await api(`/projects/${p.id}/history`, {
          method: "POST",
          body: JSON.stringify({
            revision: p.revision,
            scope,
            action,
            confirm_reset: action === "reset",
          }),
        }),
      );
      notice(
        t(
          action === "reset"
            ? "resetDone"
            : action === "undo"
              ? "undoDone"
              : "redoDone",
        ),
      );
    } finally {
      S.saving = false;
      renderStatus();
    }
  });
  S.chain = task.catch(() => {});
  return task;
}
function resetDialog(scope) {
  dialog(
    `<div class="dialog-head"><h2>${t(scope)} · ${t("resetLabel")}</h2>${button("close", "×", "icon")}</div><p>${t("reset_" + scope)}</p><p class="inspector-note">${t("resetUndoHelp")}</p><div class="snapshot-actions">${button("close", t("cancel"), "outline")}${button("confirm-reset", t("resetConfirm"), "primary", `data-scope="${scope}"`)}</div>`,
  );
}
async function showTrash() {
  const [items, cleanup] = await Promise.all([
    api("/projects-trash"),
    api("/projects-trash/cleanup-status"),
  ]);
  S.trashItems = items;
  S.trashCleanupPending = cleanup.pending;
  dialog(
    `<div class="dialog-head"><h2>${t("projectTrash")}</h2>${button("close", "×", "icon")}</div><p>${t("trashHelp")}</p><div class="trash-list">${items.length ? items.map((p) => `<article class="trash-item"><div><strong>${esc(p.name)}</strong><small>${esc(new Date(p.deleted_at).toLocaleString(lang))}</small></div>${button("restore-project", t("restoreProject"), "outline", `data-id="${p.id}" data-revision="${p.revision}"`)}</article>`).join("") : `<p class="empty-note">${t("trashEmpty")}</p>`}</div>${cleanup.pending ? `<p role="status">${t("trashCleanupPending")}</p>` : ""}<div class="snapshot-actions">${button("empty-trash", t(items.length ? "emptyTrash" : cleanup.pending ? "retryTrashCleanup" : "emptyTrash"), "danger", items.length || cleanup.pending ? "" : "disabled")}</div>`,
  );
}
function confirmEmptyTrashDialog() {
  S.emptyTrashDraft = (S.trashItems || []).map((p) => ({
    id: p.id,
    revision: p.revision,
  }));
  const items = S.trashItems || [];
  $("#dialog").innerHTML =
    `<div class="dialog-head"><h2>${t("emptyTrash")}</h2>${button("project-trash", "×", "icon")}</div><p class="trash-permanent-warning">${t("emptyTrashWarning")}</p><p>${t("emptyTrashCount")}: <strong>${items.length}</strong></p><ul class="trash-confirm-list">${items.map((p) => `<li>${esc(p.name)}</li>`).join("")}</ul>${S.trashCleanupPending ? `<p>${t("trashCleanupPending")}</p>` : ""}<p id="empty-trash-error" role="alert" hidden></p><div class="snapshot-actions">${button("project-trash", t("cancel"), "outline")}${button("confirm-empty-trash", t("permanentlyDelete"), "danger")}</div>`;
}
async function emptyTrash() {
  const buttons = $$("#dialog button");
  buttons.forEach((b) => (b.disabled = true));
  try {
    const result = await api("/projects-trash/empty", {
      method: "POST",
      body: JSON.stringify({
        projects: S.emptyTrashDraft,
        confirm_permanent_delete: true,
      }),
    });
    S.emptyTrashDraft = null;
    $("#dialog").close();
    await showTrash();
    notice(
      t(result.pending_cleanup ? "trashCleanupPending" : "trashEmptied"),
      Boolean(result.pending_cleanup),
    );
  } catch (e) {
    buttons.forEach((b) => (b.disabled = false));
    const target = $("#empty-trash-error");
    if (target) {
      target.hidden = false;
      target.textContent = e.message;
    } else throw e;
  }
}
async function deleteCurrentProject() {
  await S.chain;
  if (S.conflict) throw Error(t("conflict"));
  const p = S.p;
  await api(`/projects/${p.id}`, {
    method: "DELETE",
    body: JSON.stringify({ revision: p.revision, confirm_delete: true }),
  });
  $("#dialog").close();
  $("#video").pause();
  S.shot = S.overlay = null;
  await refreshProjects();
  if (S.projects.length) setProject(await api(`/projects/${S.projects[0].id}`));
  else {
    setProject(
      await api("/projects", {
        method: "POST",
        body: JSON.stringify({ name: t("newName") }),
      }),
    );
    await refreshProjects();
  }
  notice(t("projectDeleted"));
}
function renderInspector() {
  const p = S.p;
  if (!p) return;
  $$('[data-action="tab"]').forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === S.tab),
  );
  let html = "";
  if (S.tab === "round") {
    const r = p.round;
    html = `<div class="panel-title"><h3>${t("courseFields")}</h3><span class="tag">${t(S.overrides?.length ? "manualOverrides" : r.reference ? "imported" : "manual")}</span></div>${field("player", "player", r.player)}${field("course", "course", r.course)}${field("date", "date", r.date, "date")}<div class="field-grid">${field("tee", "tee", r.tee)}${field("category", "category", r.category)}${field("rating", "rating", r.rating, "number", 'min="20" max="100" step=".1"')}${field("slope", "slope", r.slope, "number", 'min="55" max="155"')}${field("totalPar", "total_par", r.total_par, "number", 'min="27" max="108"')}${field("totalYards", "total_yardage", r.total_yardage, "number", 'min="500" max="15000"')}</div>${button("round-view", `▦ &nbsp;${t("all")}`, "wide outline")}${button("courses", `⚑ &nbsp;${t("setup")}`, "wide subtle")}${button("save-course", t("saveCourse"), "wide subtle")}${button("courses", t("providerTitle"), "wide outline")}<div class="inspector-note">${t("modified")}</div>`;
  }
  if (S.tab === "shot") {
    const shot = p.shots.find((s) => s.id === S.shot);
    html = shot
      ? `<div class="panel-title"><h3>${t("shotNumber")} ${shotNumber(shot)}</h3><span class="tag">H${shot.hole}</span></div>${select(
          "hole",
          "hole",
          shot.hole,
          Array.from({ length: 18 }, (_, i) => [
            i + 1,
            t("hole") + " " + (i + 1),
          ]),
          "shot",
        )}${select(
          "club",
          "club",
          shot.club,
          clubs.map((c) => [c, c]),
          "shot",
        )}<div class="field-grid">${field("shotNumberLabel", "number", shot.number, "number", `min="1" max="99" placeholder="${t("automatic")}"`, "shot")}${field("distance", "distance", shot.distance, "number", 'min="0" max="1000" step=".1"', "shot")}${field("remaining", "remaining", shot.remaining, "number", 'min="0" max="1500" step=".1"', "shot")}${field("start", "start", shot.start, "number", 'min="0" step=".01"', "shot")}${field("end", "end", shot.end, "number", 'min=".01" step=".01"', "shot")}</div>${field("result", "result", shot.result, "text", "", "shot")}<label class="field"><span>${t("notes")}</span><textarea data-scope="shot" data-key="notes">${esc(shot.notes)}</textarea></label><div class="field-grid">${button("up", `↑ ${t("moveUp")}`, "subtle")}${button("down", `↓ ${t("moveDown")}`, "subtle")}</div>${button("delete-shot", t("deleteShot"), "wide danger")}`
      : `<p class="empty-note">${t("selectShot")}</p>${button("add-shot", `＋ ${t("addShot")}`, "wide primary")}`;
  }
  if (S.tab === "design") {
    const o = p.overlays.find((o) => o.id === S.overlay);
    if (o) {
      const s = o.style;
      html = `${snapshotInspector(o)}${select("colorTheme", "theme", currentTheme(s), [["custom", t("themeCustom")], ...Object.keys(THEMES).map((k) => [k, t("theme_" + k)])], "theme")}${button("apply-theme-all", t("applyThemeAll"), "wide subtle")}${select(
        "type",
        "type",
        o.type,
        o.shot_id
          ? [
              ["shot", t("shotType")],
              ["minimal", t("minimal")],
            ]
          : [
              ["full", t("full")],
              ["front", t("frontType")],
              ["back", t("backType")],
            ],
        "overlay",
      )}${button("fit-layout", t("fitLayout"), "wide outline")}<div class="field-grid">${field("start", "start", o.start, "number", 'min="0" step=".01"', "overlay")}${field("end", "end", o.end, "number", 'min=".01" step=".01"', "overlay")}</div><div class="color-fields">${field("textColor", "color", s.color, "color", "", "style")}${field("background", "background", s.background, "color", "", "style")}${field("accent", "accent", s.accent, "color", "", "style")}</div>${field("opacity", "opacity", s.opacity, "range", 'min="0" max="1" step=".01"', "style")}<label class="field"><span>${t("transparency")} <output id="transparency-value">${Math.round((1 - (s.overlay_opacity ?? 1)) * 100)}%</output></span><input type="range" data-scope="style" data-key="transparency" min="0" max="100" step="1" value="${Math.round((1 - (s.overlay_opacity ?? 1)) * 100)}" aria-label="${t("transparency")}"></label><p class="inspector-note">${t("transparencyHelp")}</p><h4>${t("position")}</h4><div class="field-grid">${["x", "y", "width", "height"].map((k) => field(k, k, s[k], "number", 'min="0" max="1" step="any"', "style")).join("")}${field("fontSize", "font_size", s.font_size, "number", 'min="12" max="48"', "style")}${field("radius", "radius", s.radius, "number", 'min="0" max="60"', "style")}</div>${select(
        "font",
        "font",
        s.font,
        [
          ["sans", t("sans")],
          ["serif", t("serif")],
          ["mono", t("mono")],
        ],
        "style",
      )}${[
        ["visible", o.visible, "overlay"],
        ["panel", s.panel, "style"],
        ["showCourse", s.show_course, "style"],
      ]
        .map(
          ([k, v, scope]) =>
            `<label class="check"><input type="checkbox" data-scope="${scope}" data-key="${k === "showCourse" ? "show_course" : k}" ${v ? "checked" : ""}>${t(k)}</label>`,
        )
        .join("")}<p class="inspector-note">${t("dragHelp")}</p>${select(
        "preset",
        "preset",
        "",
        Object.keys(p.presets).map((k) => [k, k]),
        "preset",
      )}${button("apply-preset", t("applyPreset"), "wide subtle")}${button("save-preset", t("savePreset"), "wide subtle")}${button("delete-overlay", t("deleteOverlay"), "wide danger")}`;
    } else html = `<p class="empty-note">${t("selectOverlay")}</p>`;
  }
  $("#inspector-content").innerHTML = historyBar(S.tab) + html;
}
function shotNumber(shot) {
  return displayShotNumber(S.p.shots, shot);
}
function renderTimeline() {
  const p = S.p,
    d = p.video?.duration || 60;
  const width = 100 * S.zoom;
  const ticks = Array.from(
    { length: 9 },
    (_, i) => `<span style="left:${i * 12.5}%">${fmt((d * i) / 8)}</span>`,
  ).join("");
  const marks = p.shots
    .map(
      (s) =>
        `<button class="marker shot-marker ${S.shot === s.id ? "selected" : ""}" data-action="select-shot" data-id="${s.id}" data-start="${s.start}" style="left:${(s.start / d) * 100}%;width:${Math.max(1, ((s.end - s.start) / d) * 100)}%">H${s.hole} · ${esc(s.club)}</button>`,
    )
    .join("");
  const graphics = p.overlays
    .map(
      (o) =>
        `<button class="marker graphic-marker ${o.snapshot_id ? "snapshot-marker" : ""} ${S.overlay === o.id ? "selected" : ""}" aria-label="${esc(graphicLabel(o))}" data-action="select-overlay" data-id="${o.id}" style="left:${(o.start / d) * 100}%;width:${Math.max(1, ((o.end - o.start) / d) * 100)}%">${esc(graphicLabel(o))}</button>`,
    )
    .join("");
  $("#tracks").style.width = width + "%";
  $("#tracks").innerHTML =
    `<div class="ruler">${ticks}</div><div class="track">${marks || `<span class="track-empty">${t("emptyTimeline")}</span>`}</div><div class="track graphics-track">${graphics}</div><div class="playhead" style="left:${(S.time / d) * 100}%"></div>`;
}
function renderShots() {
  $("#shot-count").textContent = S.p.shots.length;
  $("#shot-list").innerHTML = S.p.shots
    .map(
      (s) =>
        `<button data-action="select-shot" data-id="${s.id}" class="shot-card ${s.id === S.shot ? "selected" : ""}"><span class="hole-number">${String(s.hole).padStart(2, "0")}</span><span><strong>${esc(s.club)}</strong><small>${t("shotNumber")} ${shotNumber(s)} · ${fmt(s.start)} — ${fmt(s.end)}</small></span><b>${s.distance ?? "—"}<small>YDS</small></b><i>↗</i></button>`,
    )
    .join("");
}
function renderGraphics() {
  const layer = $("#overlay-layer");
  if (!S.p?.video) {
    layer.innerHTML = "";
    return;
  }
  layer.innerHTML = S.p.overlays
    .filter((o) => o.visible)
    .map(
      (o) =>
        `<div class="overlay-box ${S.overlay === o.id ? "selected" : ""}" data-overlay="${o.id}" style="left:${o.style.x * 100}%;top:${o.style.y * 100}%;width:${o.style.width * 100}%;height:${o.style.height * 100}%"><img draggable="false" src="/api/v1/projects/${S.p.id}/overlays/${o.id}.png?r=${S.p.revision}" alt="${esc(t(o.type === "shot" ? "shotType" : o.type === "front" ? "frontType" : o.type === "back" ? "backType" : o.type))}"><span class="resize-handle"></span></div>`,
    )
    .join("");
  updateVisible();
}
function updateVisible() {
  if (!S.p) return;
  $$("[data-overlay]").forEach((el) => {
    const o = S.p.overlays.find((o) => o.id === el.dataset.overlay);
    el.hidden = !(o.start <= S.time && S.time < o.end);
  });
}
function fitVideo() {
  const box = $("#video-box"),
    well = $(".preview-well");
  if (!S.p?.video || !box) return;
  const v = S.p.video,
    ratio = v.width / v.height;
  const w = Math.min(well.clientWidth, well.clientHeight * ratio);
  box.style.width = w + "px";
  box.style.height = w / ratio + "px";
}
function tick() {
  if (!S.p) return;
  const v = $("#video");
  S.time = v.currentTime || 0;
  $("#time").textContent = `${fmt(S.time)} / ${fmt(S.p.video?.duration || 0)}`;
  $("#seek").value = S.time;
  const line = $(".playhead");
  if (line)
    line.style.left = (S.time / (S.p.video?.duration || 60)) * 100 + "%";
  updateVisible();
}
function updatePlay() {
  const b = $('[data-action="play"]');
  if (b) b.textContent = $("#video").paused ? "▶" : "Ⅱ";
}
function animate() {
  tick();
  if (!$("#video").paused) requestAnimationFrame(animate);
}
function scoreTable(items, label) {
  const total = S.totals[label];
  const rows = ["par", "yardage", "score"]
    .map((key) => {
      const cells = items
        .map((hole) => {
          const input = `<input aria-label="${t("hole")} ${hole.number} ${t(key)}" data-hole="${hole.number}" data-key="${key}" type="number" min="${key === "par" ? 3 : 1}" max="${key === "par" ? 6 : key === "score" ? 40 : 1000}" value="${hole[key] ?? ""}" placeholder="—">`;
          return `<td>${key === "score" ? `<span class="score-entry ${scoreKind(hole)}">${input}</span>` : input}</td>`;
        })
        .join("");
      return `<tr><th scope="row">${t(key)}</th>${cells}<td>${total[key] ?? "—"}</td></tr>`;
    })
    .join("");
  return `<div class="score-table-wrap"><table class="score-table"><thead><tr><th scope="col">${t("hole")}</th>${items.map((h) => `<th scope="col">${String(h.number).padStart(2, "0")}</th>`).join("")}<th scope="col">${t("total")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function renderRound() {
  const p = S.p,
    all = S.totals.all,
    rel =
      all.relative == null
        ? "—"
        : all.relative > 0
          ? "+" + all.relative
          : all.relative === 0
            ? "E"
            : all.relative;
  $("#rounds-view").innerHTML =
    `<div class="page-title"><span class="eyebrow">${t("rounds")}</span><h2>${esc(p.round.course || t("courseTitle"))}</h2><p>${esc(p.round.player)} ${p.round.player ? "·" : ""} ${p.round.date} · ${esc(p.round.tee || t("tee"))}</p></div><div class="summary-cards">${[
      [t("front"), S.totals.front.score ?? "—"],
      [t("back"), S.totals.back.score ?? "—"],
      [t("total"), all.score ?? "—"],
      [t("relative"), rel],
    ]
      .map(([k, v]) => `<div><span>${k}</span><strong>${v}</strong></div>`)
      .join(
        "",
      )}</div><div class="scorecard-panel"><div class="section-head"><h3>${t("all")}</h3><span class="tag">${all.played}/18 ${t("played")}</span></div><h4>${t("front")}</h4>${scoreTable(p.round.holes.slice(0, 9), "front")}<h4>${t("back")}</h4>${scoreTable(p.round.holes.slice(9), "back")}<p class="inspector-note">${t("scoreHelp")}</p></div><div class="button-row">${button("csv", t("importCSV"), "outline")}${button("csv-template", t("downloadCSV"), "subtle")}${button("reference", t("reference"), "outline")}${p.reference_file ? `<a class="button" href="/api/v1/projects/${p.id}/reference" target="_blank">${t("openReference")} ↗</a>` : ""}</div><div class="source-panel"><span class="tag">${t(S.overrides?.length ? "manualOverrides" : p.round.reference ? "imported" : "manual")}</span><p>${t("modified")}</p>${p.round.reference ? `<details><summary>${t("savedReference")}</summary><pre>${esc(JSON.stringify(p.round.reference, null, 2))}</pre></details>` : ""}</div>`;
}
function renderCourses() {
  const query = $("#course-search")?.value || "";
  $("#courses-view").innerHTML =
    `<div class="page-title course-banner"><span class="eyebrow">${t("courses")}</span><h2>${t("courseTitle")}</h2><p>${t("courseDesc")}</p></div>
    <section class="provider-panel" aria-label="${t("providerTitle")}"><div class="section-head"><h3>${t("providerTitle")}</h3><span class="tag">${t(S.provider.configured ? "apiConfigured" : "apiNotConfigured")}</span></div>
    <p class="inspector-note">${t("apiKeyHelp")}</p>
    <label class="field"><span>${t("apiKey")}</span><input id="provider-key" type="password" autocomplete="new-password" maxlength="4096" placeholder="${t(S.provider.configured ? "apiKeyReplace" : "apiKeyPlaceholder")}" ${S.provider.source === "environment" ? "disabled" : ""}></label>
    <div class="button-row">${button("save-api-key", t("saveApiKey"), "outline", S.provider.source === "environment" ? "disabled" : "")}${button("clear-api-key", t("removeApiKey"), "subtle", S.provider.source !== "local" ? "disabled" : "")}<a class="button" href="https://golfcourseapi.com/" target="_blank" rel="noopener">${t("getApiKey")} ↗</a></div>
    ${S.provider.source === "environment" ? `<p class="inspector-note">${t("apiEnvironment")}</p>` : ""}
    <div class="course-tools"><input id="provider-query" value="${esc(S.remoteQuery)}" placeholder="${t("providerSearchPlaceholder")}" aria-label="${t("providerSearchPlaceholder")}" maxlength="160">${button("search-provider", t(S.remoteLoading ? "providerSearching" : "providerSearch"), "primary", S.remoteLoading ? "disabled" : "")}</div><p class="inspector-note">${t("providerSearchHelp")}</p><div id="provider-results"></div></section>
    <div class="course-tools"><input id="course-search" placeholder="${t("search")}" aria-label="${t("search")}" value="${esc(query)}">${button("import-course", `＋ ${t("importJSON")}`, "outline")}</div><div class="usga-note"><span>↗</span><div><a href="https://ncrdb.usga.org/courseTeeInfo.aspx" target="_blank" rel="noopener">${t("usga")}</a><p>${t("usgaNote")}</p></div></div><div id="course-results"></div>`;
  renderProviderResults();
  renderCourseResults(query);
}
function renderProviderResults() {
  if (!$("#provider-results")) return;
  $("#provider-results").innerHTML =
    S.remoteResults === null
      ? ""
      : S.remoteResults.items.length
        ? S.remoteResults.items
            .map(
              (c) =>
                `<article class="provider-result"><div><h4>${esc(c.name)}</h4><p>${esc([c.club, c.city, c.state, c.country].filter(Boolean).join(" · "))}</p><small>${c.tee_count} ${t("availableTees")}</small></div>${button("import-provider", t("importProvider"), "outline", `data-id="${esc(c.id)}"`)}</article>`,
            )
            .join("") +
          (S.remoteResults.cached
            ? `<p class="inspector-note">${t("cachedResults")}</p>`
            : "")
        : `<p class="empty-note">${t("providerNoResults")}</p>`;
}
function renderCourseResults(query = "") {
  const words = query.toLowerCase().split(/\s+/);
  const values = S.courses.filter((c) =>
    words.every((w) =>
      [c.name, c.club, c.city, c.state, c.zip_code]
        .join(" ")
        .toLowerCase()
        .includes(w),
    ),
  );
  $("#course-results").innerHTML = values.length
    ? values
        .map(
          (c) =>
            `<article class="course-card"><div class="course-icon">⚑</div><span class="tag">${t(c.verification === "manual" ? "manual" : "imported")}</span><h3>${esc(c.name)}</h3><p>${esc([c.city, c.state].filter(Boolean).join(", "))}</p><label class="field"><span>${t("teeSelect")}</span><select data-course="${c.id}">${c.tees.map((q) => `<option value="${q.id}">${esc(q.name)} · ${esc(q.category || "—")} · ${q.yardage ?? "—"} YDS · CR ${q.rating ?? "—"} / ${q.slope ?? "—"}</option>`).join("")}</select></label>${button("use-tee", t("useTee"), "wide primary", `data-id="${c.id}"`)}${c.source_name === "GolfCourseAPI" ? button("refresh-provider", t("refreshProvider"), "wide subtle", `data-id="${esc(c.external_id)}"`) : ""}<small>${esc(c.source_name)} · ${esc(c.updated_at.slice(0, 10))}</small></article>`,
        )
        .join("")
    : `<div class="empty-state"><span>⚑</span><h3>${t("noCourses")}</h3><p>${t("noCoursesDesc")}</p>${button("edit-course", t("courseFields"), "outline")}</div>`;
}
function renderExports() {
  const values = S.jobs.filter((j) => j.project_id === S.p.id);
  $("#exports-view").innerHTML =
    `<div class="page-title"><span class="eyebrow">${t("exports")}</span><h2>${t("exportTitle")}</h2><p>${t("exportDesc")}</p></div>${button("export", `↗ ${t("export")}`, "primary large")}<div class="export-list">${values.length ? values.map((j) => `<article class="export-job"><div class="export-icon">↗</div><div><h3>${esc(j.name)}</h3><p>${t(j.status)} · ${esc(j.resolution)} · ${esc(j.quality)} · ${j.id.slice(0, 8)}</p><progress max="1" value="${j.progress}"></progress>${j.error ? `<pre>${esc(j.error)}</pre>` : ""}</div><strong>${Math.round(j.progress * 100)}%</strong>${j.status === "done" ? `<a class="button primary" href="/api/v1/jobs/${j.id}/download">↓ ${t("download")}</a>` : ""}</article>`).join("") : `<p class="empty-note">${t("noExports")}</p>`}</div><p class="inspector-note">${t("exportNote")}</p>`;
}
function dialog(html) {
  $("#dialog").innerHTML = html;
  $("#dialog").showModal();
}
async function upload(path, file) {
  await S.chain;
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1" + path);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable)
        notice(`${t("upload")} ${Math.round((e.loaded / e.total) * 100)}%`);
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 400)
          throw Error(
            typeof data.detail === "string"
              ? data.detail
              : JSON.stringify(data.detail),
          );
        resolve(data);
      } catch (e) {
        reject(e);
      }
    };
    xhr.onerror = () => reject(Error(t("errorTitle")));
    const data = new FormData();
    data.append("file", file);
    xhr.send(data);
  });
}
async function addShot() {
  if (!S.p?.video) return notice(t("chooseVideoFirst"), true);
  const d = S.p.video.duration,
    start = Math.max(S.time, 0, ...S.p.shots.map((s) => s.end)),
    end = Math.min(d, start + 5);
  if (start >= end) return notice(t("noSpace"), true);
  const sid = id(),
    oid = id();
  await change((p) => {
    p.shots.push({
      id: sid,
      hole: 1,
      club: "Driver",
      distance: null,
      remaining: null,
      result: "",
      notes: "",
      start,
      end,
    });
    p.overlays.push({
      id: oid,
      type: "shot",
      shot_id: sid,
      start,
      end,
      visible: true,
      style: style(),
    });
  });
  S.shot = sid;
  S.overlay = oid;
  S.tab = "shot";
  render();
}
function snapshotSummary(s) {
  const relative =
    s.relative_to_par == null
      ? "—"
      : s.relative_to_par === 0
        ? "E"
        : s.relative_to_par > 0
          ? "+" + s.relative_to_par
          : s.relative_to_par;
  const values = [
    ["snapshotCurrentHole", s.current_hole ?? t("snapshotRoundComplete")],
    ["snapshotCompleted", `${s.completed_holes_count}/18`],
    ["front", s.front_nine_score ?? "—"],
    ["back", s.back_nine_score ?? "—"],
    ["snapshotTotal", s.total_score ?? "—"],
    ["relative", relative],
    ["snapshotPlayedPar", s.total_par ?? "—"],
    ["snapshotCoursePar", s.scorecard_data.course_par ?? "—"],
  ];
  return `<div class="snapshot-summary">${values.map(([label, value]) => `<div><span>${t(label)}</span><strong>${esc(value)}</strong></div>`).join("")}</div>`;
}
function snapshotTable(s) {
  return `<div class="snapshot-captured-course">${esc(s.scorecard_data.player)} · ${esc(s.scorecard_data.course)} · ${esc(s.scorecard_data.tee)}</div><table class="snapshot-table"><thead><tr><th>${t("hole")}</th><th>${t("par")}</th><th>${t("yardage")}</th><th>${t("score")}</th><th>${t("status")}</th></tr></thead><tbody>${s.scorecard_data.holes.map((h) => `<tr class="${h.status === "current" ? "snapshot-current" : ""}"><td>${h.number}</td><td>${h.par ?? "—"}</td><td>${h.yardage ?? "—"}</td><td>${h.score ?? "—"}</td><td>${t("snapshot_" + h.status)}</td></tr>`).join("")}</tbody></table>`;
}
function snapshotInspector(o) {
  const snap = S.p.snapshots?.[o.snapshot_id];
  if (!snap) return "";
  let previous = snap.previous_snapshot_id,
    history = [],
    seen = new Set();
  while (previous && !seen.has(previous)) {
    seen.add(previous);
    const old = S.p.snapshots[previous];
    if (!old) break;
    history.push(old);
    previous = old.previous_snapshot_id;
  }
  return `<section class="snapshot-inspector"><div class="panel-title"><h3>${t("snapshot")} v${snap.snapshot_version}</h3><span class="tag">${snap.completed_holes_count}/18</span></div><p class="inspector-note">${t("snapshotCaptured")}: ${esc(new Date(snap.created_at).toLocaleString(lang))}<br>${t("snapshotOriginalTime")}: ${fmt(snap.timeline_position)}${snap.legacy ? `<br>${t("snapshotLegacy")}` : ""}</p>${snapshotSummary(snap)}<details><summary>${t("snapshotInspect")}</summary>${snapshotTable(snap)}</details>${history.length ? `<details><summary>${t("snapshotHistory")}</summary>${history.map((old) => `<details><summary>v${old.snapshot_version} · ${old.completed_holes_count}/18 · ${esc(new Date(old.created_at).toLocaleString(lang))}</summary>${snapshotSummary(old)}${snapshotTable(old)}</details>`).join("")}</details>` : ""}<p class="inspector-note">${t("snapshotFrozenHelp")}</p>${button("new-snapshot", t("snapshotCreateNew"), "wide outline")}${button("replace-snapshot", t("snapshotReplace"), "wide subtle")}</section>`;
}
function graphicLabel(o) {
  const kind = t(
    o.type === "shot"
      ? "shotType"
      : o.type === "front"
        ? "frontType"
        : o.type === "back"
          ? "backType"
          : o.type,
  );
  const snap = S.p.snapshots?.[o.snapshot_id];
  return snap
    ? `${t("snapshot")} · ${kind} · ${snap.completed_holes_count}/18 · v${snap.snapshot_version}`
    : kind;
}
function snapshotDialogError(e) {
  const el = $("#snapshot-error");
  if (el) {
    el.textContent = e.message;
    el.hidden = false;
  } else error(e);
}
function renderSnapshotDialog() {
  const d = S.snapshotDraft,
    s = d.preview;
  const options = S.p.round.holes
    .filter((h) => h.score == null)
    .map(
      (h) =>
        `<option value="${h.number}" ${d.current_hole === h.number ? "selected" : ""}>${t("hole")} ${h.number}</option>`,
    )
    .join("");
  $("#dialog").innerHTML =
    `<div class="dialog-head"><h2>${t(d.replace ? "snapshotReplace" : "snapshotConfirmTitle")}</h2>${button("close", "×", "icon")}</div><p>${t(d.replace ? "snapshotReplaceWarning" : "snapshotConfirmHelp")}</p><label class="field"><span>${t("snapshotCurrentHole")}</span><select id="snapshot-current-hole"><option value="" ${d.current_hole == null ? "selected" : ""}>${t("automatic")}</option>${options}</select></label>${snapshotSummary(s)}<details><summary>${t("snapshotInspect")}</summary>${snapshotTable(s)}</details><p class="snapshot-error" id="snapshot-error" role="alert" hidden></p><div class="snapshot-actions">${button("close", t("cancel"), "outline")}${button("confirm-snapshot", t(d.replace ? "snapshotReplaceConfirm" : "snapshotAddConfirm"), "primary")}</div>`;
}
async function refreshSnapshotPreview() {
  const d = S.snapshotDraft,
    selectedHole = d.current_hole;
  d.ready = false;
  const confirm = $("[data-action='confirm-snapshot']");
  if (confirm) confirm.disabled = true;
  const preview = await api(`/projects/${S.p.id}/scorecard-snapshots/preview`, {
    method: "POST",
    body: JSON.stringify({
      revision: d.revision,
      timeline_position: d.time,
      current_hole: selectedHole,
    }),
  });
  // A slower response must not re-enable confirmation for an older selection.
  if (S.snapshotDraft !== d || d.current_hole !== selectedHole) return;
  d.preview = preview;
  d.ready = true;
  renderSnapshotDialog();
}
async function addCard(replace = false) {
  if (!S.p?.video) return notice(t("chooseVideoFirst"), true);
  await S.chain;
  const selected = replace
    ? S.p.overlays.find((o) => o.id === S.overlay)
    : null;
  if (replace && !selected?.snapshot_id) return;
  const s = style();
  Object.assign(s, recommendedGeometry("full", S.p.video), { font_size: 24 });
  S.snapshotDraft = {
    replace,
    revision: S.p.revision,
    time: selected
      ? selected.start
      : Math.min(S.time, Math.max(0, S.p.video.duration - 0.1)),
    current_hole: null,
    style: s,
    overlayId: selected?.id,
    snapshotId: selected?.snapshot_id,
  };
  await refreshSnapshotPreview();
  $("#dialog").showModal();
}
async function confirmSnapshot(buttonElement) {
  const d = S.snapshotDraft;
  if (!d?.ready) return;
  buttonElement.disabled = true;
  try {
    const path = d.replace
      ? `/projects/${S.p.id}/scorecard-snapshots/${d.snapshotId}/replace`
      : `/projects/${S.p.id}/scorecard-snapshots`;
    const body = d.replace
      ? {
          revision: d.revision,
          overlay_id: d.overlayId,
          current_hole: d.current_hole,
          confirm_replace: true,
        }
      : {
          revision: d.revision,
          timeline_position: d.time,
          current_hole: d.current_hole,
          type: "full",
          duration: 5,
          style: d.style,
        };
    const result = await api(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
    S.overlay = result.created_overlay_id;
    S.tab = "design";
    S.snapshotDraft = null;
    $("#dialog").close();
    setProject(result);
    $("#video").currentTime = d.time;
    notice(t(d.replace ? "snapshotReplaced" : "snapshotAdded"));
  } catch (e) {
    snapshotDialogError(e);
  } finally {
    buttonElement.disabled = false;
  }
}
async function action(name, el) {
  switch (name) {
    case "history-undo":
    case "history-redo":
      await commitHistory(
        name === "history-undo" ? "undo" : "redo",
        el.dataset.scope,
      );
      break;
    case "history-reset":
      resetDialog(el.dataset.scope);
      break;
    case "confirm-reset":
      el.disabled = true;
      try {
        await commitHistory("reset", el.dataset.scope);
        $("#dialog").close();
      } catch (e) {
        $("#dialog").close();
        throw e;
      }
      break;
    case "delete-project":
      dialog(
        `<div class="dialog-head"><h2>${t("deleteProject")}</h2>${button("close", "×", "icon")}</div><p><strong>${esc(S.p.name)}</strong></p><p>${t("deleteProjectHelp")}</p><div class="snapshot-actions">${button("close", t("cancel"), "outline")}${button("confirm-delete-project", t("moveToTrash"), "danger")}</div>`,
      );
      break;
    case "confirm-delete-project":
      el.disabled = true;
      try {
        await deleteCurrentProject();
      } catch (e) {
        el.disabled = false;
        $("#dialog").close();
        throw e;
      }
      break;
    case "project-trash":
      await showTrash();
      break;
    case "empty-trash":
      confirmEmptyTrashDialog();
      break;
    case "confirm-empty-trash":
      await emptyTrash();
      break;
    case "restore-project":
      await S.chain;
      if (S.conflict) throw Error(t("conflict"));
      el.disabled = true;
      try {
        setProject(
          await api(`/projects/${el.dataset.id}/restore`, {
            method: "POST",
            body: JSON.stringify({ revision: Number(el.dataset.revision) }),
          }),
        );
        $("#dialog").close();
        await refreshProjects();
        notice(t("projectRestored"));
      } catch (e) {
        el.disabled = false;
        $("#dialog").close();
        throw e;
      }
      break;
    case "view":
      S.view = el.dataset.view;
      render();
      break;
    case "new": {
      const name = prompt(t("projectName"), t("newName"));
      if (!name) return;
      await S.chain;
      S.conflict = false;
      S.shot = S.overlay = null;
      setProject(
        await api("/projects", {
          method: "POST",
          body: JSON.stringify({ name }),
        }),
      );
      await refreshProjects();
      break;
    }
    case "project":
      await loadProject(el.dataset.id);
      break;
    case "tab":
      S.tab = el.dataset.tab;
      renderInspector();
      break;
    case "upload":
      $("#video-file").click();
      break;
    case "play":
      if (!S.p.video) break;
      $("#video").paused ? await $("#video").play() : $("#video").pause();
      break;
    case "prev":
    case "next":
      $("#video").currentTime = Math.min(
        S.p.video?.duration || 0,
        Math.max(
          0,
          S.time + (name === "prev" ? -1 : 1) / (S.p.video?.fps || 30),
        ),
      );
      break;
    case "add-shot":
      await addShot();
      break;
    case "add-card":
      await addCard();
      break;
    case "new-snapshot":
      await addCard();
      break;
    case "replace-snapshot":
      await addCard(true);
      break;
    case "confirm-snapshot":
      await confirmSnapshot(el);
      break;
    case "select-shot": {
      S.shot = el.dataset.id;
      const shot = S.p.shots.find((s) => s.id === S.shot);
      S.overlay = S.p.overlays.find((o) => o.shot_id === S.shot)?.id;
      S.tab = "shot";
      $("#video").currentTime = shot.start;
      renderInspector();
      renderTimeline();
      renderShots();
      renderGraphics();
      break;
    }
    case "select-overlay": {
      S.overlay = el.dataset.id;
      const o = S.p.overlays.find((o) => o.id === S.overlay);
      if (o.shot_id) S.shot = o.shot_id;
      S.tab = "design";
      $("#video").currentTime = o.start;
      renderInspector();
      renderTimeline();
      renderGraphics();
      break;
    }
    case "delete-shot":
      if (confirm(t("confirmDelete")))
        await change((p) => {
          p.shots = p.shots.filter((s) => s.id !== S.shot);
          p.overlays = p.overlays.filter((o) => o.shot_id !== S.shot);
        });
      break;
    case "delete-overlay":
      await change(
        (p) => (p.overlays = p.overlays.filter((o) => o.id !== S.overlay)),
      );
      break;
    case "up":
    case "down":
      await change((p) => {
        const i = p.shots.findIndex((s) => s.id === S.shot),
          j = i + (name === "up" ? -1 : 1);
        if (j >= 0 && j < p.shots.length)
          [p.shots[i], p.shots[j]] = [p.shots[j], p.shots[i]];
      });
      break;
    case "round-view":
      S.view = "rounds";
      render();
      break;
    case "courses":
      S.view = "courses";
      render();
      break;
    case "edit-course":
      S.tab = "round";
      renderInspector();
      break;
    case "save-course": {
      await S.chain;
      const r = S.p.round;
      if (!r.course || !r.tee) throw Error(`${t("course")} / ${t("tee")}`);
      await api("/courses", {
        method: "POST",
        body: JSON.stringify({
          name: r.course,
          verification: "manual",
          source_name: t("manualSource"),
          tees: [
            {
              name: r.tee,
              category: r.category,
              par: r.total_par,
              yardage: r.total_yardage,
              rating: r.rating,
              slope: r.slope,
              holes: r.holes.map((h) => ({ ...h, score: null })),
            },
          ],
        }),
      });
      S.courses = (await api("/courses")).items;
      notice(t("savedCourse"));
      if (S.view === "courses") renderCourses();
      break;
    }
    case "save-api-key": {
      const input = $("#provider-key");
      const api_key = input.value.trim();
      if (!api_key) throw Error(t("golf_api_invalid_key"));
      S.provider = await api("/course-provider/settings", {
        method: "PUT",
        body: JSON.stringify({ api_key }),
      });
      input.value = "";
      renderCourses();
      notice(t("apiKeySaved"));
      break;
    }
    case "clear-api-key":
      S.provider = await api("/course-provider/settings", { method: "DELETE" });
      S.remoteResults = null;
      renderCourses();
      notice(t("apiKeyRemoved"));
      break;
    case "search-provider": {
      if (S.remoteLoading) return;
      S.remoteQuery = $("#provider-query").value.trim();
      if (S.remoteQuery.length < 2) throw Error(t("golf_api_query_required"));
      S.remoteLoading = true;
      S.remoteResults = null;
      renderCourses();
      try {
        S.remoteResults = await api(
          "/course-provider/search?q=" + encodeURIComponent(S.remoteQuery),
        );
      } finally {
        S.remoteLoading = false;
        if (S.view === "courses") renderCourses();
      }
      break;
    }
    case "import-provider":
    case "refresh-provider": {
      el.disabled = true;
      try {
        await api(
          `/course-provider/courses/${el.dataset.id}/import?refresh=${name === "refresh-provider"}`,
          { method: "POST" },
        );
        S.courses = (await api("/courses")).items;
        renderCourses();
        notice(t("providerImported"));
      } finally {
        el.disabled = false;
      }
      break;
    }
    case "import-course":
      $("#course-file").click();
      break;
    case "use-tee": {
      await S.chain;
      const c = S.courses.find((c) => c.id === el.dataset.id),
        tid = $(`[data-course="${c.id}"]`).value;
      if (!confirm(t("confirmCourse"))) return;
      setProject(
        await api(`/projects/${S.p.id}/course`, {
          method: "POST",
          body: JSON.stringify({
            course_id: c.id,
            tee_id: tid,
            revision: S.p.revision,
            confirm_replace: true,
          }),
        }),
      );
      S.view = "rounds";
      render();
      break;
    }
    case "csv":
      $("#csv-file").click();
      break;
    case "reference":
      $("#reference-file").click();
      break;
    case "csv-template": {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(
        new Blob(
          [
            "hole,par,yardage,score,handicap\n" +
              Array.from({ length: 18 }, (_, i) => `${i + 1},,,,`).join("\n"),
          ],
          { type: "text/csv" },
        ),
      );
      a.download = "holes.csv";
      a.click();
      URL.revokeObjectURL(a.href);
      break;
    }
    case "export":
      if (!S.p.video) return notice(t("chooseVideoFirst"), true);
      dialog(
        `<div class="dialog-head"><h2>${t("chooseExport")}</h2>${button("close", "×", "icon")}</div><p>${t("exportDesc")}</p><label class="field"><span>${t("quality")}</span><select id="export-quality"><option value="draft">${t("draft")}</option><option value="high" selected>${t("high")}</option><option value="master">${t("master")}</option></select></label><label class="field"><span>${t("resolution")}</span><select id="export-resolution"><option value="source">${t("source")}</option><option value="1080">1080p</option><option value="2160">4K</option></select></label><p class="inspector-note">${t("sound")}</p>${button("render", t("render"), "wide primary")}`,
      );
      break;
    case "render": {
      const quality = $("#export-quality").value,
        resolution = $("#export-resolution").value;
      await S.chain;
      await api(`/projects/${S.p.id}/exports`, {
        method: "POST",
        body: JSON.stringify({ quality, resolution, revision: S.p.revision }),
      });
      $("#dialog").close();
      S.jobs = await api("/jobs");
      S.view = "exports";
      render();
      break;
    }
    case "apply-theme-all": {
      const source = S.p.overlays.find((o) => o.id === S.overlay).style;
      const colors = {
        background: source.background,
        color: source.color,
        accent: source.accent,
      };
      await change((p) =>
        p.overlays.forEach((o) => Object.assign(o.style, colors)),
      );
      break;
    }
    case "fit-layout":
      await change((p) => {
        const o = p.overlays.find((o) => o.id === S.overlay);
        Object.assign(o.style, recommendedGeometry(o.type, p.video));
      });
      break;
    case "save-preset": {
      const key = prompt(t("presetName"));
      if (key)
        await change(
          (p) =>
            (p.presets[key.slice(0, 80)] = clone(
              p.overlays.find((o) => o.id === S.overlay).style,
            )),
        );
      break;
    }
    case "apply-preset": {
      const key = $('[data-scope="preset"]').value;
      if (key)
        await change(
          (p) =>
            (p.overlays.find((o) => o.id === S.overlay).style = clone(
              p.presets[key],
            )),
        );
      break;
    }
    case "export-json":
      downloadJSON(S.p, "golf-project.json");
      break;
    case "help":
      dialog(
        `<div class="dialog-head"><h2>${t("help")}</h2>${button("close", "×", "icon")}</div><p>${t("helpText")}</p>${button("export-json", t("downloadBackup"), "wide outline")}${button("reload", t("retry"), "wide subtle")}`,
      );
      break;
    case "reload":
      S.conflict = false;
      setProject(await api(`/projects/${S.p.id}`));
      $("#dialog").close();
      break;
    case "close":
      S.snapshotDraft = null;
      $("#dialog").close();
      break;
    case "dismiss":
      $("#notice").hidden = true;
      break;
  }
}
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-action]");
  if (el) action(el.dataset.action, el).catch(error);
});
document.addEventListener("change", async (e) => {
  const el = e.target;
  try {
    if (el.id === "snapshot-current-hole") {
      S.snapshotDraft.current_hole = el.value === "" ? null : Number(el.value);
      try {
        await refreshSnapshotPreview();
      } catch (e) {
        snapshotDialogError(e);
      }
      return;
    }
    if (el.id === "language") {
      setLang(el.value);
      $("#video").pause();
      S.source = null;
      shell();
      return;
    }
    if (el.id === "project-name") {
      await change((p) => (p.name = el.value));
      await refreshProjects();
      return;
    }
    if (el.id === "video-file" && el.files[0]) {
      setProject(await upload(`/projects/${S.p.id}/video`, el.files[0]));
      await refreshProjects();
      el.value = "";
      return;
    }
    if (el.id === "csv-file" && el.files[0]) {
      await S.chain;
      setProject(
        await upload(
          `/projects/${S.p.id}/holes-csv?revision=${S.p.revision}`,
          el.files[0],
        ),
      );
      el.value = "";
      return;
    }
    if (el.id === "reference-file" && el.files[0]) {
      await S.chain;
      setProject(
        await upload(
          `/projects/${S.p.id}/reference?revision=${S.p.revision}`,
          el.files[0],
        ),
      );
      el.value = "";
      return;
    }
    if (el.id === "course-file" && el.files[0]) {
      const c = JSON.parse(await el.files[0].text());
      c.verification = "imported";
      await api("/courses", { method: "POST", body: JSON.stringify(c) });
      S.courses = (await api("/courses")).items;
      renderCourses();
      el.value = "";
      return;
    }
    let key = el.dataset.key;
    if (el.dataset.hole) {
      await change(
        (p) =>
          (p.round.holes[Number(el.dataset.hole) - 1][key] =
            el.value === "" ? null : Number(el.value)),
      );
      return;
    }
    if (el.dataset.scope && key) {
      const scope = el.dataset.scope;
      if (scope === "preset") return;
      if (scope === "theme") {
        const theme = THEMES[el.value];
        if (theme)
          await change((p) =>
            Object.assign(
              p.overlays.find((o) => o.id === S.overlay).style,
              theme,
            ),
          );
        return;
      }
      let value =
        el.type === "checkbox"
          ? el.checked
          : ["number", "range"].includes(el.type)
            ? el.value === ""
              ? null
              : Number(el.value)
            : el.value;
      if (key === "hole") value = Number(value);
      if (key === "transparency") {
        key = "overlay_opacity";
        value = 1 - value / 100;
      }
      await change((p) => {
        let obj =
          scope === "round"
            ? p.round
            : scope === "shot"
              ? p.shots.find((s) => s.id === S.shot)
              : p.overlays.find((o) => o.id === S.overlay);
        if (scope === "style") obj = obj.style;
        obj[key] = value;
        if (scope === "shot" && (key === "start" || key === "end"))
          for (const o of p.overlays.filter((o) => o.shot_id === S.shot))
            o[key] = value;
      });
    }
  } catch (e) {
    error(e);
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "provider-query") S.remoteQuery = e.target.value;
  if (e.target.dataset.key === "transparency" && $("#transparency-value"))
    $("#transparency-value").textContent = e.target.value + "%";
  if (e.target.id === "seek") $("#video").currentTime = Number(e.target.value);
  if (e.target.id === "zoom") {
    S.zoom = Number(e.target.value);
    renderTimeline();
  }
  if (e.target.id === "course-search") renderCourseResults(e.target.value);
});
// Pointer gestures use normalized video coordinates, independent of letterboxing.
let drag = null,
  suppressClick = false;
document.addEventListener("pointerdown", (e) => {
  const graphic = e.target.closest("[data-overlay]"),
    marker = e.target.closest(".marker");
  if (graphic) {
    const o = S.p.overlays.find((o) => o.id === graphic.dataset.overlay);
    drag = {
      kind: "graphic",
      id: o.id,
      el: graphic,
      x: e.clientX,
      y: e.clientY,
      original: clone(o.style),
      resize: !!e.target.closest(".resize-handle"),
      rect: $("#video-box").getBoundingClientRect(),
    };
    graphic.setPointerCapture(e.pointerId);
    e.preventDefault();
  } else if (marker) {
    const isShot = marker.classList.contains("shot-marker"),
      item = (isShot ? S.p.shots : S.p.overlays).find(
        (v) => v.id === marker.dataset.id,
      );
    drag = {
      kind: "marker",
      isShot,
      id: item.id,
      el: marker,
      x: e.clientX,
      y: e.clientY,
      start: item.start,
      end: item.end,
      rect: $("#tracks").getBoundingClientRect(),
    };
    marker.setPointerCapture(e.pointerId);
  }
});
document.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const d = drag,
    dx = (e.clientX - d.x) / d.rect.width,
    dy = (e.clientY - d.y) / d.rect.height;
  if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) < 4) return;
  d.moved = true;
  if (d.kind === "graphic") {
    const s = { ...d.original };
    if (d.resize) {
      s.width = Math.min(1 - s.x, Math.max(0.15, s.width + dx));
      s.height = Math.min(1 - s.y, Math.max(0.12, s.height + dy));
    } else {
      s.x = Math.max(0, Math.min(1 - s.width, s.x + dx));
      s.y = Math.max(0, Math.min(1 - s.height, s.y + dy));
    }
    d.value = s;
    Object.assign(d.el.style, {
      left: s.x * 100 + "%",
      top: s.y * 100 + "%",
      width: s.width * 100 + "%",
      height: s.height * 100 + "%",
    });
  } else {
    const duration = S.p.video.duration;
    d.value = Math.max(
      0,
      Math.min(duration - (d.end - d.start), d.start + dx * duration),
    );
    d.el.style.left = (d.value / duration) * 100 + "%";
  }
});
document.addEventListener("pointerup", async () => {
  const d = drag;
  drag = null;
  if (!d) return;
  if (!d.moved) {
    if (d.kind === "graphic") {
      S.overlay = d.id;
      S.tab = "design";
      renderInspector();
      renderGraphics();
    }
    return;
  }
  suppressClick = true;
  setTimeout(() => (suppressClick = false), 100);
  try {
    await change((p) => {
      if (d.kind === "graphic")
        p.overlays.find((o) => o.id === d.id).style = d.value;
      else {
        const item = (d.isShot ? p.shots : p.overlays).find(
            (o) => o.id === d.id,
          ),
          delta = d.value - item.start;
        item.start += delta;
        item.end += delta;
        if (d.isShot)
          for (const o of p.overlays.filter((o) => o.shot_id === d.id)) {
            o.start += delta;
            o.end += delta;
          }
      }
    });
  } catch {
    renderGraphics();
    renderTimeline();
  }
});
document.addEventListener(
  "click",
  (e) => {
    if (suppressClick) {
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  },
  true,
);
document.addEventListener("keydown", (e) => {
  if (e.target.id === "provider-query" && e.key === "Enter") {
    e.preventDefault();
    action("search-provider").catch(error);
    return;
  }
  if (
    ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) ||
    e.target.isContentEditable ||
    $("#dialog").open
  )
    return;
  if (
    (e.metaKey || e.ctrlKey) &&
    (e.key.toLowerCase() === "z" || e.key.toLowerCase() === "y")
  ) {
    e.preventDefault();
    const scope = S.view === "rounds" ? "round" : S.tab;
    commitHistory(
      e.shiftKey || e.key.toLowerCase() === "y" ? "redo" : "undo",
      scope,
    ).catch(error);
    return;
  }
  if (e.code === "Space") {
    e.preventDefault();
    action("play").catch(error);
  }
  if (e.key === "ArrowRight") action("next").catch(error);
  if (e.key === "ArrowLeft") action("prev").catch(error);
});
async function init() {
  shell();
  try {
    const health = await api("/health");
    if (!health.ffmpeg || !health.ffprobe) notice("FFmpeg / ffprobe", true);
    await refreshProjects();
    S.courses = (await api("/courses")).items;
    S.provider = await api("/course-provider/settings");
    const stored = localStorage.getItem("gvs-project");
    const project = S.projects.find((p) => p.id === stored) || S.projects[0];
    if (project) await loadProject(project.id);
    else {
      setProject(
        await api("/projects", {
          method: "POST",
          body: JSON.stringify({ name: t("newName") }),
        }),
      );
      await refreshProjects();
    }
    S.jobs = await api("/jobs");
    setInterval(async () => {
      try {
        S.jobs = await api("/jobs");
        if (S.view === "exports") renderExports();
      } catch {}
    }, 2000);
  } catch (e) {
    error(e);
  }
}
init();
