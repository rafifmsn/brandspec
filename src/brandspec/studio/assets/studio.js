(() => {
  const COS_30 = Math.cos(Math.PI / 6);

  const state = {
    session: null,
    activeId: null,
    tab: "review",
    view: "positive",
    surfaceHex: "",
    status: "revise",
    pins: [],
    nextPinId: 1,
  };

  const el = {
    sessionDir: document.getElementById("session-dir"),
    modeTabs: document.getElementById("mode-tabs"),
    roundLabel: document.getElementById("round-label"),
    candidateCount: document.getElementById("candidate-count"),
    candidateStrip: document.getElementById("candidate-strip"),
    reviewStage: document.getElementById("review-stage"),
    mockupsPanel: document.getElementById("mockups-panel"),
    mockupsGrid: document.getElementById("mockups-grid"),
    candidateTitle: document.getElementById("candidate-title"),
    candidateSubtitle: document.getElementById("candidate-subtitle"),
    canvasFrame: document.getElementById("canvas-frame"),
    markImage: document.getElementById("mark-image"),
    pinLayer: document.getElementById("pin-layer"),
    metricsBar: document.getElementById("metrics-bar"),
    warningsBar: document.getElementById("warnings-bar"),
    surfaceHex: document.getElementById("surface-hex"),
    pinList: document.getElementById("pin-list"),
    reviewSummary: document.getElementById("review-summary"),
    submitBtn: document.getElementById("submit-review"),
    submitStatus: document.getElementById("submit-status"),
    historyBlock: document.getElementById("history-block"),
    historyList: document.getElementById("history-list"),
  };

  function activeCandidate() {
    if (!state.session || !state.session.candidates.length) return null;
    return (
      state.session.candidates.find((c) => c.id === state.activeId) ||
      state.session.candidates[0]
    );
  }

  function gridToCanvasPercent(xGrid, yGrid, meta) {
    if (!meta || !meta.affine || !meta.grid) return { xPct: 50, yPct: 50 };
    const unit = Number(meta.unit || 40);
    const canvasSize = Number(meta.canvas_size || 1000);
    const [sx, , , sy, tx, ty] = meta.affine;
    let dx = 0;
    let dy = 0;
    if (meta.grid.type === "square") {
      dx = xGrid * unit;
      dy = yGrid * unit;
    } else if (meta.grid.type === "isometric") {
      dx = xGrid * unit * COS_30;
      dy = (yGrid + 0.5 * xGrid) * unit;
    } else if (meta.grid.type === "polar") {
      const r = xGrid * unit;
      const rad = (yGrid * Math.PI) / 180;
      dx = r * Math.sin(rad);
      dy = -r * Math.cos(rad);
    }
    const cx = dx * sx + tx;
    const cy = dy * sy + ty;
    return {
      xPct: (cx / canvasSize) * 100,
      yPct: (cy / canvasSize) * 100,
    };
  }

  function pixelToGrid(px, py, rectWidth, rectHeight, meta) {
    if (!meta || !meta.affine || !meta.grid) {
      return {
        xGrid: Number(((px / rectWidth) * 10 - 5).toFixed(2)),
        yGrid: Number(((py / rectHeight) * 10 - 5).toFixed(2)),
      };
    }
    const unit = Number(meta.unit || 40);
    const canvasSize = Number(meta.canvas_size || 1000);
    const [sx, , , sy, tx, ty] = meta.affine;
    const x = ((px * canvasSize) / rectWidth - tx) / sx;
    const y = ((py * canvasSize) / rectHeight - ty) / sy;

    let xGrid = 0;
    let yGrid = 0;
    if (meta.grid.type === "square") {
      xGrid = x / unit;
      yGrid = y / unit;
    } else if (meta.grid.type === "isometric") {
      xGrid = x / (unit * COS_30);
      yGrid = y / unit - 0.5 * xGrid;
    } else if (meta.grid.type === "polar") {
      const r = Math.hypot(x, y) / unit;
      xGrid = r;
      yGrid = r <= 1e-9 ? 0 : ((Math.atan2(x, -y) * 180) / Math.PI + 360) % 360;
    }
    return {
      xGrid: Number(xGrid.toFixed(2)),
      yGrid: Number(yGrid.toFixed(2)),
    };
  }

  function renderCandidateStrip() {
    const candidates = state.session ? state.session.candidates : [];
    if (candidates.length <= 1) {
      el.candidateStrip.hidden = true;
      el.candidateStrip.innerHTML = "";
      return;
    }
    el.candidateStrip.hidden = false;
    el.candidateStrip.innerHTML = "";
    candidates.forEach((cand) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "candidate-tile" + (cand.id === state.activeId ? " is-selected" : "");
      const img = document.createElement("img");
      img.className = "candidate-thumb";
      img.src = cand.files.logo_svg;
      img.alt = cand.id;
      const lbl = document.createElement("div");
      lbl.className = "candidate-label";
      const idSpan = document.createElement("span");
      idSpan.textContent = cand.id;
      const statusSpan = document.createElement("span");
      statusSpan.textContent = cand.metrics && cand.metrics.passed ? "PASS" : "WARN";
      lbl.appendChild(idSpan);
      lbl.appendChild(statusSpan);
      btn.appendChild(img);
      btn.appendChild(lbl);
      btn.addEventListener("click", () => {
        state.activeId = cand.id;
        renderAll();
      });
      el.candidateStrip.appendChild(btn);
    });
  }

  function renderStage() {
    const cand = activeCandidate();
    if (!cand) {
      el.candidateTitle.textContent = "No candidates";
      el.candidateSubtitle.textContent = "Compile a mark or sweep first.";
      el.markImage.removeAttribute("src");
      el.metricsBar.innerHTML = "";
      return;
    }

    const name = (cand.meta && cand.meta.name) || cand.id;
    const concept = (cand.meta && cand.meta.concept) || "";
    el.candidateTitle.textContent = `${cand.id}: ${name}`;
    el.candidateSubtitle.textContent = concept;

    el.canvasFrame.className = "canvas-frame";
    el.canvasFrame.style.background = "";
    if (state.view === "inverted") {
      el.canvasFrame.classList.add("is-inverted");
    } else if (state.view === "96" || state.view === "48" || state.view === "24") {
      el.canvasFrame.classList.add(`is-scale-${state.view}`);
    }

    if (state.surfaceHex && /^#[0-9a-fA-F]{6}$/.test(state.surfaceHex)) {
      el.canvasFrame.style.background = state.surfaceHex;
    }

    if (state.view === "grid" && cand.files.overlay_svg) {
      el.markImage.src = cand.files.overlay_svg;
    } else {
      el.markImage.src = cand.files.logo_svg;
    }

    renderMetrics(cand.metrics);
    renderPinsOnCanvas(cand);
  }

  function renderMetrics(metrics) {
    el.metricsBar.innerHTML = "";
    if (!metrics) return;
    const items = [
      ["Ink Ratio", metrics.ink_ratio],
      ["24px Ink", metrics.ink_ratio_24px],
      ["Aspect", metrics.bbox_aspect],
      ["Islands", metrics.island_count],
      ["Slivers", metrics.tiny_island_count],
      ["Drift %", metrics.optical_drift_pct],
    ];
    items.forEach(([key, val]) => {
      const cell = document.createElement("div");
      cell.className = "metric-cell";
      cell.innerHTML = `<span class="metric-key">${key}</span><span class="metric-val">${val ?? "-"}</span>`;
      el.metricsBar.appendChild(cell);
    });

    if (Array.isArray(metrics.warnings) && metrics.warnings.length > 0) {
      el.warningsBar.hidden = false;
      el.warningsBar.textContent = metrics.warnings.join(" | ");
    } else {
      el.warningsBar.hidden = true;
      el.warningsBar.textContent = "";
    }
  }

  function renderPinsOnCanvas(cand) {
    el.pinLayer.innerHTML = "";
    const activePins = state.pins.filter((p) => p.candidate_id === cand.id);
    activePins.forEach((pin) => {
      const { xPct, yPct } = gridToCanvasPercent(pin.x_grid, pin.y_grid, cand.meta);
      const marker = document.createElement("div");
      marker.className = "pin-marker";
      marker.style.left = `${xPct}%`;
      marker.style.top = `${yPct}%`;
      marker.textContent = String(pin.id);
      el.pinLayer.appendChild(marker);
    });
  }

  function renderPinList() {
    el.pinList.innerHTML = "";
    if (state.pins.length === 0) {
      const empty = document.createElement("div");
      empty.className = "hint-text";
      empty.textContent = "No pinned notes yet.";
      el.pinList.appendChild(empty);
      return;
    }
    state.pins.forEach((pin) => {
      const item = document.createElement("div");
      item.className = "pin-item";
      const head = document.createElement("div");
      head.className = "pin-item-head";
      head.innerHTML = `<span>#${pin.id} ${pin.candidate_id} (${pin.x_grid}, ${pin.y_grid})</span>`;
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "pin-remove";
      removeBtn.textContent = "Remove";
      removeBtn.addEventListener("click", () => {
        state.pins = state.pins.filter((p) => p.id !== pin.id);
        renderAll();
      });
      head.appendChild(removeBtn);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "pin-comment-input";
      input.value = pin.comment;
      input.placeholder = "Describe geometric change at this coordinate";
      input.addEventListener("input", (evt) => {
        pin.comment = evt.target.value;
      });

      item.appendChild(head);
      item.appendChild(input);
      el.pinList.appendChild(item);
    });
  }

  function renderHistory() {
    if (!state.session) return;
    const rounds = [];
    if (Array.isArray(state.session.history)) {
      rounds.push(...state.session.history);
    }
    if (state.session.latest_review) {
      rounds.push(state.session.latest_review);
    }
    if (rounds.length === 0) {
      el.historyBlock.hidden = true;
      return;
    }
    el.historyBlock.hidden = false;
    el.historyList.innerHTML = "";
    rounds.forEach((item) => {
      const row = document.createElement("div");
      row.className = "history-item";
      const pinsCount = Array.isArray(item.pins) ? item.pins.length : 0;
      row.textContent = `Round ${item.round}: ${item.status} (${pinsCount} pins) ${item.summary || ""}`.trim();
      el.historyList.appendChild(row);
    });
  }

  function renderMockups() {
    const hasMockups = Boolean(state.session && (state.session.tokens || state.session.kit));
    el.modeTabs.hidden = !hasMockups;
    if (!hasMockups) {
      state.tab = "review";
    }
    const showMockups = hasMockups && state.tab === "mockups";
    el.mockupsPanel.hidden = !showMockups;
    el.reviewStage.hidden = showMockups;
    if (!showMockups) return;

    el.mockupsGrid.innerHTML = "";
    const kit = state.session.kit || {};
    const tokens = state.session.tokens || {};
    const cand = activeCandidate();
    const markSrc = kit["logo-light.svg"] || (cand && cand.files.logo_svg) || "";

    const navCard = document.createElement("div");
    navCard.className = "mockup-card";
    const navTitle = document.createElement("div");
    navTitle.className = "mockup-title";
    navTitle.textContent = "Navbar and Favicon Tab";
    const tabBar = document.createElement("div");
    tabBar.className = "mockup-tab";
    if (kit["favicon.ico"]) {
      const fav = document.createElement("img");
      fav.src = kit["favicon.ico"];
      fav.width = 16;
      fav.height = 16;
      fav.alt = "Favicon";
      tabBar.appendChild(fav);
    }
    const tabText = document.createElement("span");
    tabText.textContent = tokens.name || "BrandSpec";
    tabBar.appendChild(tabText);

    const navbar = document.createElement("div");
    navbar.className = "mockup-navbar";
    navbar.style.background = tokens.bg_surface || "#121316";
    navbar.style.color = tokens.text_primary || "#f3f4f6";
    if (markSrc) {
      const logo = document.createElement("img");
      logo.src = markSrc;
      logo.width = 24;
      logo.height = 24;
      logo.alt = "Navbar mark";
      navbar.appendChild(logo);
    }
    const navLinks = document.createElement("span");
    navLinks.textContent = "Docs   Releases   Studio";
    navbar.appendChild(navLinks);
    navCard.appendChild(navTitle);
    navCard.appendChild(tabBar);
    navCard.appendChild(navbar);
    el.mockupsGrid.appendChild(navCard);

    if (kit["icon-192.png"] || kit["icon-maskable-512.png"]) {
      const iconCard = document.createElement("div");
      iconCard.className = "mockup-card";
      const iconTitle = document.createElement("div");
      iconTitle.className = "mockup-title";
      iconTitle.textContent = "PWA and App Icons";
      const row = document.createElement("div");
      row.className = "mockup-icons-row";
      [
        ["icon-192.png", 64, "12px"],
        ["icon-maskable-512.png", 64, "999px"],
        ["apple-touch-icon.png", 56, "14px"],
      ].forEach(([key, size, radius]) => {
        if (!kit[key]) return;
        const img = document.createElement("img");
        img.src = kit[key];
        img.width = size;
        img.height = size;
        img.style.borderRadius = radius;
        img.alt = key;
        row.appendChild(img);
      });
      iconCard.appendChild(iconTitle);
      iconCard.appendChild(row);
      el.mockupsGrid.appendChild(iconCard);
    }

    if (kit["og-card.png"]) {
      const ogCard = document.createElement("div");
      ogCard.className = "mockup-card";
      const ogTitle = document.createElement("div");
      ogTitle.className = "mockup-title";
      ogTitle.textContent = "Open Graph Card";
      const ogImg = document.createElement("img");
      ogImg.className = "mockup-og";
      ogImg.src = kit["og-card.png"];
      ogImg.alt = "OG card preview";
      ogCard.appendChild(ogTitle);
      ogCard.appendChild(ogImg);
      el.mockupsGrid.appendChild(ogCard);
    }
  }

  function renderAll() {
    renderCandidateStrip();
    renderStage();
    renderPinList();
    renderHistory();
    renderMockups();
  }

  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      renderMockups();
    });
  });

  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      document.querySelectorAll("[data-view]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      renderStage();
    });
  });

  document.querySelectorAll(".decision-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.status = btn.dataset.status;
      document.querySelectorAll(".decision-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
    });
  });

  el.surfaceHex.addEventListener("input", (evt) => {
    state.surfaceHex = evt.target.value.trim();
    renderStage();
  });

  el.canvasFrame.addEventListener("click", (evt) => {
    const cand = activeCandidate();
    if (!cand) return;
    const rect = el.canvasFrame.getBoundingClientRect();
    const px = evt.clientX - rect.left;
    const py = evt.clientY - rect.top;
    const { xGrid, yGrid } = pixelToGrid(px, py, rect.width, rect.height, cand.meta);
    state.pins.push({
      id: state.nextPinId++,
      candidate_id: cand.id,
      x_grid: xGrid,
      y_grid: yGrid,
      comment: "",
    });
    renderAll();
  });

  el.submitBtn.addEventListener("click", async () => {
    el.submitBtn.disabled = true;
    el.submitStatus.textContent = "Saving review...";
    const cand = activeCandidate();
    try {
      const resp = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: state.status,
          selected_candidate: cand ? cand.id : null,
          summary: el.reviewSummary.value.trim(),
          pins: state.pins,
        }),
      });
      const body = await resp.json();
      if (!resp.ok) {
        el.submitStatus.textContent = body.error || "Failed to save review.";
        el.submitBtn.disabled = false;
        return;
      }
      el.submitStatus.textContent = `Submitted Round ${body.round} (${body.status}).`;
      await loadSession();
    } catch (err) {
      el.submitStatus.textContent = `Error: ${err.message}`;
    } finally {
      el.submitBtn.disabled = false;
    }
  });

  async function loadSession() {
    const resp = await fetch("/api/session");
    const data = await resp.json();
    state.session = data;
    if (!state.activeId && data.candidates.length > 0) {
      state.activeId = data.candidates[0].id;
    }
    el.sessionDir.textContent = data.dir || "";
    el.roundLabel.textContent = `Round ${data.round || 1}`;
    el.candidateCount.textContent = `${data.candidates.length} candidate${data.candidates.length === 1 ? "" : "s"}`;
    renderAll();
  }

  loadSession();
})();
