/* Tablero: detalle de la conversación, arrastrar entre columnas, confirmar la sugerencia y refresco automático. */
(function () {
  var root = document.getElementById("board-root");
  var drawer = document.getElementById("drawer");
  var finding = document.getElementById("finding");
  if (!root || !drawer) return;

  var openId = null;
  var dragging = false;
  var toastTimer = null;

  function toast(message) {
    var el = document.querySelector(".toast") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "toast", role: "status" }));
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.hidden = true; }, 3500);
  }

  function request(url, options) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (r) {
      if (r.redirected && /\/login/.test(r.url)) { location.href = "/login"; throw new Error("sesión"); }
      return r;
    });
  }

  function post(url, params) {
    return request(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(params || {}).toString(),
    });
  }

  function syncFinding() {
    var data = document.getElementById("board-data");
    if (data && finding) finding.textContent = data.getAttribute("data-finding") || "";
  }

  function markOpen() {
    root.querySelectorAll(".cardk").forEach(function (card) {
      card.setAttribute("aria-expanded", String(card.getAttribute("data-id") === String(openId)));
    });
  }

  function refresh() {
    if (dragging) return Promise.resolve();
    return request("/board").then(function (r) { return r.text(); }).then(function (html) {
      var board = document.getElementById("board");
      var x = board ? board.scrollLeft : 0;
      root.innerHTML = html;
      board = document.getElementById("board");
      if (board) board.scrollLeft = x;
      syncFinding();
      markOpen();
    }).catch(function () {});
  }

  function loadDrawer(id) {
    return request("/conversations/" + id + "/drawer").then(function (r) { return r.text(); }).then(function (html) {
      drawer.innerHTML = html;
    });
  }

  function openDrawer(id) {
    openId = id;
    loadDrawer(id).then(function () {
      drawer.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
      markOpen();
      var close = drawer.querySelector("[data-close]");
      if (close) close.focus();
    });
  }

  function closeDrawer() {
    openId = null;
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    markOpen();
  }

  function setStatus(id, status) {
    return post("/conversations/" + id + "/status", { status: status }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) { toast(data.error || "No se pudo cambiar el estado."); return; }
      return refresh().then(function () { if (String(openId) === String(id)) return loadDrawer(id); });
    });
  }

  // --- tablero ---
  root.addEventListener("click", function (event) {
    if (event.target.closest("a.go")) return; // "Ir al chat" abre WhatsApp, no el detalle
    var confirmBtn = event.target.closest("[data-confirm]");
    if (confirmBtn) {
      event.stopPropagation();
      setStatus(confirmBtn.closest(".cardk").getAttribute("data-id"), confirmBtn.getAttribute("data-confirm"));
      return;
    }
    var jump = event.target.closest("[data-jump]");
    if (jump) {
      event.preventDefault();
      var lane = document.getElementById("lane-" + jump.getAttribute("data-jump"));
      if (lane) lane.scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
      return;
    }
    var card = event.target.closest(".cardk");
    if (card) openDrawer(card.getAttribute("data-id"));
  });

  root.addEventListener("keydown", function (event) {
    if ((event.key === "Enter" || event.key === " ") && event.target.classList && event.target.classList.contains("cardk")) {
      event.preventDefault();
      openDrawer(event.target.getAttribute("data-id"));
    }
  });

  root.addEventListener("dragstart", function (event) {
    var card = event.target.closest(".cardk");
    if (!card) return;
    dragging = true;
    card.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.getAttribute("data-id"));
  });

  root.addEventListener("dragend", function () {
    dragging = false;
    root.querySelectorAll(".dragging, .drop").forEach(function (el) { el.classList.remove("dragging", "drop"); });
  });

  root.addEventListener("dragover", function (event) {
    var lane = event.target.closest(".lane");
    if (!lane || lane.getAttribute("data-status") === "sin_clasificar") return;
    event.preventDefault();
    root.querySelectorAll(".lane.drop").forEach(function (el) { if (el !== lane) el.classList.remove("drop"); });
    lane.classList.add("drop");
  });

  root.addEventListener("drop", function (event) {
    var lane = event.target.closest(".lane");
    if (!lane || lane.getAttribute("data-status") === "sin_clasificar") return;
    event.preventDefault();
    var id = event.dataTransfer.getData("text/plain");
    var card = root.querySelector('.cardk[data-id="' + id + '"]');
    dragging = false;
    root.querySelectorAll(".drop").forEach(function (el) { el.classList.remove("drop"); });
    if (card && card.getAttribute("data-column") !== lane.getAttribute("data-status")) setStatus(id, lane.getAttribute("data-status"));
  });

  // --- detalle ---
  drawer.addEventListener("click", function (event) {
    if (event.target.closest("[data-close]")) { closeDrawer(); return; }
    var set = event.target.closest("[data-set]");
    if (set) { setStatus(openId, set.getAttribute("data-set")); return; }
    var analyze = event.target.closest("[data-analyze]");
    if (analyze) {
      analyze.disabled = true;
      analyze.textContent = "Analizando…";
      post("/conversations/" + openId + "/analyze").then(function (r) { return r.json(); }).then(function (data) {
        if (!data.ok) toast(data.error || "No se pudo analizar ahora.");
        return refresh().then(function () { return loadDrawer(openId); });
      }).catch(function () { toast("No se pudo analizar ahora."); analyze.disabled = false; analyze.textContent = "Analizar ahora"; });
    }
  });

  document.addEventListener("keydown", function (event) { if (event.key === "Escape" && openId) closeDrawer(); });

  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

  var analyzeAll = document.getElementById("analyze-all");
  if (analyzeAll) analyzeAll.addEventListener("click", function () {
    analyzeAll.disabled = true;
    analyzeAll.textContent = "Analizando…";
    post("/board/analyze").then(function (r) { return r.json(); }).then(function (data) {
      if (!data.ok) { toast(data.error || "No se pudo analizar ahora."); return; }
      var parts = [];
      parts.push(data.analyzed ? plural(data.analyzed, "chat analizado", "chats analizados") : "No hay chats por analizar");
      if (data.failed) parts.push(plural(data.failed, "falló", "fallaron") + " (el modelo está saturado, reintenta en un momento)");
      if (data.more) parts.push("quedan más: vuelve a pulsar");
      toast(parts.join(" · "));
      return refresh();
    }).catch(function () { toast("No se pudo analizar ahora."); }).then(function () {
      analyzeAll.disabled = false;
      analyzeAll.textContent = "Analizar ahora";
    });
  });

  var refreshBtn = document.getElementById("refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", function () { refresh().then(function () { toast("Tablero actualizado"); }); });

  syncFinding();
  setInterval(function () { if (!document.hidden && !dragging) refresh(); }, 30000);
})();
