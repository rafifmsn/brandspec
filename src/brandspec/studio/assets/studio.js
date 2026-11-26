(() => {
  const COS_30 = Math.cos(Math.PI / 6);

  const state = {
    session: null,
    activeId: null,
    tab: "review",
    view: "positive",
    scale: "fit",
    zoom: 1.0,
    surfaceHex: "",
    status: "revise",
    pins: [],
    focusedPinIndex: -1,
    leftCollapsed: false,
  };

  const el = {
    sessionDir: document.getElementById("session-dir"),
    activeCrumb: document.getElementById("active-crumb"),
    roundPill: document.getElementById("round-pill"),
    modeTabs: document.getElementById("mode-tabs"),
    candidateCount: document.getElementById("candidate-count"),
    activeHealth: document.getElementById("active-health"),
    reviewWorkspace: document.getElementById("review-workspace"),
    mockupsPanel: document.getElementById("mockups-panel"),
    mockupsGrid: document.getElementById("mockups-grid"),
    sidebarCount: document.getElementById("sidebar-count"),
    candidateGrid: document.getElementById("candidate-grid"),
    artboardWrap: document.getElementById("artboard-wrap"),
    canvasFrame: document.getElementById("canvas-frame"),
    markImage: document.getElementById("mark-image"),
    pinLayer: document.getElementById("pin-layer"),
    hoverCoords: document.getElementById("hover-coords"),
    metricsDock: document.getElementById("metrics-dock"),
    zoomReadout: document.getElementById("zoom-readout"),
    surfaceHex: document.getElementById("surface-hex"),
    hexSwatch: document.getElementById("hex-swatch"),
    candidateTitle: document.getElementById("candidate-title"),
    candidateSubtitle: document.getElementById("candidate-subtitle"),
    variantParams: document.getElementById("variant-params"),
    pinCount: document.getElementById("pin-count"),
    clearPins: document.getElementById("clear-pins"),
    pinList: document.getElementById("pin-list"),
    reviewSummary: document.getElementById("review-summary"),
    submitBtn: document.getElementById("submit-review"),
    submitStatus: document.getElementById("submit-status"),
    warningsAccordion: document.getElementById("warnings-accordion"),
    warningsCount: document.getElementById("warnings-count"),
    warningsList: document.getElementById("warnings-list"),
    historyAccordion: document.getElementById("history-accordion"),
    historyCount: document.getElementById("history-count"),
    historyList: document.getElementById("history-list"),
    railToggleLeft: document.getElementById("rail-toggle-left"),
    railFit: document.getElementById("rail-fit"),
    zoomIn: document.getElementById("zoom-in"),
    zoomOut: document.getElementById("zoom-out"),
  };

  function renumberPins() {
    state.pins.forEach((pin, idx) => {
      pin.id = idx + 1;
    });
    if (state.focusedPinIndex >= state.pins.length) {
      state.focusedPinIndex = state.pins.length - 1;
    }
  }

  function activeCandidate() {
    if (!state.session || !state.session.candidates.length) return null;
    return (
      state.session.candidates.find((c) => c.id === state.activeId) ||
      state.session.candidates[0]
    );
  }

  function variantInfo(cid) {
    if (!state.session || !Array.isArray(state.session.variants)) return null;
    return state.session.variants.find((v) => v.id === cid) || null;
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

  function renderCandidateGrid() {
    const candidates = state.session ? state.session.candidates : [];
    el.sidebarCount.textContent = String(candidates.length);
    el.candidateGrid.innerHTML = "";

    candidates.forEach((cand) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "candidate-card" + (cand.id === state.activeId ? " is-selected" : "");

      const thumbBox = document.createElement("div");
      thumbBox.className = "candidate-thumb-box";
      const img = document.createElement("img");
      img.src = cand.files.logo_svg;
      img.alt = cand.id;
      thumbBox.appendChild(img);

      const metaRow = document.createElement("div");
      metaRow.className = "candidate-card-meta tabular";
      const idSpan = document.createElement("span");
      idSpan.textContent = cand.id;
      const statusSpan = document.createElement("span");
      statusSpan.textContent = cand.metrics && cand.metrics.passed ? "PASS" : "WARN";
      metaRow.appendChild(idSpan);
      metaRow.appendChild(statusSpan);

      btn.appendChild(thumbBox);
      btn.appendChild(metaRow);

      const vInfo = variantInfo(cand.id);
      if (vInfo && vInfo.params) {
        const paramRow = document.createElement("div");
        paramRow.className = "candidate-card-param tabular";
        paramRow.textContent = Object.entries(vInfo.params)
          .map(([k, v]) => `${k.split(".").pop()}=${v}`)
          .join(" ");
        btn.appendChild(paramRow);
      }

      btn.addEventListener("click", () => {
        state.activeId = cand.id;
        renderAll();
      });
      el.candidateGrid.appendChild(btn);
    });
  }

  function renderStage() {
    const cand = activeCandidate();
    if (!cand) {
      el.activeCrumb.textContent = "none";
      el.candidateTitle.textContent = "No candidates";
      el.candidateSubtitle.textContent = "Compile a mark or sweep first.";
      el.markImage.removeAttribute("src");
      el.metricsDock.innerHTML = "";
      return;
    }

    el.activeCrumb.textContent = cand.id;
    const passed = cand.metrics && cand.metrics.passed;
    el.activeHealth.textContent = passed ? "PASS" : "WARN";
    el.activeHealth.className = "pill-badge tabular" + (passed ? " is-pass" : "");

    const name = (cand.meta && cand.meta.name) || cand.id;
    const concept = (cand.meta && cand.meta.concept) || "";
    el.candidateTitle.textContent = `${cand.id}: ${name}`;
    el.candidateSubtitle.textContent = concept;

    const vInfo = variantInfo(cand.id);
    el.variantParams.innerHTML = "";
    if (vInfo && vInfo.params) {
      el.variantParams.hidden = false;
      Object.entries(vInfo.params).forEach(([k, v]) => {
        const chip = document.createElement("span");
        chip.className = "param-chip";
        chip.textContent = `${k}=${v}`;
        el.variantParams.appendChild(chip);
      });
    } else {
      el.variantParams.hidden = true;
    }

    el.artboardWrap.style.transform = `scale(${state.zoom})`;
    el.zoomReadout.textContent = `${Math.round(state.zoom * 100)}%`;

    el.canvasFrame.className = "canvas-frame";
    el.canvasFrame.style.background = "";
    if (state.view === "inverted") {
      el.canvasFrame.classList.add("is-inverted");
    } else if (state.view === "sheet") {
      el.canvasFrame.classList.add("is-sheet");
    }
    if (state.scale !== "fit" && state.view !== "sheet") {
      el.canvasFrame.classList.add(`is-scale-${state.scale}`);
    }

    if (state.surfaceHex && /^#[0-9a-fA-F]{6}$/.test(state.surfaceHex)) {
      el.canvasFrame.style.background = state.surfaceHex;
      el.hexSwatch.style.background = state.surfaceHex;
    } else {
      el.hexSwatch.style.background = state.view === "inverted" ? "#0b0c0e" : "#ffffff";
    }

    if (state.view === "sheet" && cand.files.sheet_png) {
      el.markImage.src = cand.files.sheet_png;
    } else if (state.view === "grid" && cand.files.overlay_svg) {
      el.markImage.src = cand.files.overlay_svg;
    } else {
      el.markImage.src = cand.files.logo_svg;
    }

    renderMetrics(cand.metrics);
    renderPinsOnCanvas(cand);
  }

  function renderMetrics(metrics) {
    el.metricsDock.innerHTML = "";
    if (!metrics) return;

    const items = [
      ["Ink", metrics.ink_ratio],
      ["24px", metrics.ink_ratio_24px],
      ["Aspect", metrics.bbox_aspect],
      ["Islands", metrics.island_count],
      ["Slivers", metrics.tiny_island_count],
      ["Drift", metrics.optical_drift_pct !== undefined ? `${metrics.optical_drift_pct}%` : "-"],
    ];
    items.forEach(([key, val]) => {
      const cell = document.createElement("div");
      cell.className = "telemetry-item";
      const kSpan = document.createElement("span");
      kSpan.className = "telemetry-key";
      kSpan.textContent = key;
      const vSpan = document.createElement("span");
      vSpan.className = "telemetry-val";
      vSpan.textContent = val ?? "-";
      cell.appendChild(kSpan);
      cell.appendChild(vSpan);
      el.metricsDock.appendChild(cell);
    });

    const warnings = Array.isArray(metrics.warnings) ? metrics.warnings : [];
    el.warningsAccordion.hidden = warnings.length === 0;
    el.warningsCount.textContent = String(warnings.length);
    el.warningsList.innerHTML = "";
    warnings.forEach((msg) => {
      const row = document.createElement("div");
      row.className = "warning-row";
      row.textContent = msg;
      el.warningsList.appendChild(row);
    });
  }

  function renderPinsOnCanvas(cand) {
    el.pinLayer.innerHTML = "";
    if (state.view === "sheet" || state.scale !== "fit") return;

    state.pins.forEach((pin, idx) => {
      if (pin.candidate_id !== cand.id) return;
      const { xPct, yPct } = gridToCanvasPercent(pin.x_grid, pin.y_grid, cand.meta);
      const marker = document.createElement("div");
      marker.className = "pin-marker" + (idx === state.focusedPinIndex ? " is-focused" : "");
      marker.style.left = `${xPct}%`;
      marker.style.top = `${yPct}%`;
      marker.textContent = String(pin.id);
      el.pinLayer.appendChild(marker);
    });
  }

  function renderPinList(focusNewInput = false) {
    el.pinCount.textContent = `(${state.pins.length})`;
    el.clearPins.hidden = state.pins.length === 0;
    el.pinList.innerHTML = "";

    if (state.pins.length === 0) {
      const empty = document.createElement("div");
      empty.className = "pin-empty";
      empty.textContent = "Click anywhere on the mark artboard to pin grid coordinates.";
      el.pinList.appendChild(empty);
      return;
    }

    state.pins.forEach((pin, idx) => {
      const card = document.createElement("div");
      card.className = "pin-card" + (idx === state.focusedPinIndex ? " is-focused" : "");

      const head = document.createElement("div");
      head.className = "pin-card-head";

      const title = document.createElement("span");
      title.className = "pin-card-title";
      title.textContent = `#${pin.id}  ${pin.candidate_id}  (${pin.x_grid}, ${pin.y_grid})`;

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "text-btn";
      removeBtn.textContent = "Remove";
      removeBtn.addEventListener("click", (evt) => {
        evt.stopPropagation();
        state.pins.splice(idx, 1);
        renumberPins();
        renderAll();
      });

      head.appendChild(title);
      head.appendChild(removeBtn);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "pin-input";
      input.value = pin.comment;
      input.placeholder = "Describe geometric change at this coordinate";
      input.addEventListener("focus", () => {
        state.focusedPinIndex = idx;
        renderPinsOnCanvas(activeCandidate());
      });
      input.addEventListener("input", (evt) => {
        pin.comment = evt.target.value;
      });

      card.addEventListener("click", () => {
        state.focusedPinIndex = idx;
        if (pin.candidate_id && pin.candidate_id !== state.activeId) {
          state.activeId = pin.candidate_id;
          renderAll();
        } else {
          renderPinsOnCanvas(activeCandidate());
        }
      });

      card.appendChild(head);
      card.appendChild(input);
      el.pinList.appendChild(card);

      if (focusNewInput && idx === state.pins.length - 1) {
        input.focus();
      }
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

    el.historyAccordion.hidden = rounds.length === 0;
    el.historyCount.textContent = String(rounds.length);
    el.historyList.innerHTML = "";
    rounds.forEach((item) => {
      const row = document.createElement("div");
      row.className = "history-row";
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
    el.reviewWorkspace.hidden = showMockups;
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

  function syncViewButtons() {
    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.view === state.view);
    });
    document.querySelectorAll("[data-rail-view]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.railView === state.view);
    });
  }

  function renderAll(focusNewInput = false) {
    syncViewButtons();
    renderCandidateGrid();
    renderStage();
    renderPinList(focusNewInput);
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

  document.querySelectorAll("[data-view], [data-rail-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view || btn.dataset.railView;
      syncViewButtons();
      renderStage();
    });
  });

  document.querySelectorAll("[data-scale]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.scale = btn.dataset.scale;
      document.querySelectorAll("[data-scale]").forEach((b) => b.classList.remove("is-active"));
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

  el.zoomIn.addEventListener("click", () => {
    state.zoom = Math.min(2.0, Number((state.zoom + 0.15).toFixed(2)));
    renderStage();
  });

  el.zoomOut.addEventListener("click", () => {
    state.zoom = Math.max(0.5, Number((state.zoom - 0.15).toFixed(2)));
    renderStage();
  });

  el.railFit.addEventListener("click", () => {
    state.zoom = 1.0;
    state.scale = "fit";
    document.querySelectorAll("[data-scale]").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.scale === "fit");
    });
    renderStage();
  });

  el.railToggleLeft.addEventListener("click", () => {
    state.leftCollapsed = !state.leftCollapsed;
    el.reviewWorkspace.classList.toggle("is-left-collapsed", state.leftCollapsed);
  });

  el.surfaceHex.addEventListener("input", (evt) => {
    state.surfaceHex = evt.target.value.trim();
    renderStage();
  });

  el.clearPins.addEventListener("click", () => {
    state.pins = [];
    state.focusedPinIndex = -1;
    renderAll();
  });

  el.canvasFrame.addEventListener("mousemove", (evt) => {
    const cand = activeCandidate();
    if (!cand || state.view === "sheet" || state.scale !== "fit") {
      el.hoverCoords.hidden = true;
      return;
    }
    const rect = el.canvasFrame.getBoundingClientRect();
    const px = evt.clientX - rect.left;
    const py = evt.clientY - rect.top;
    const { xGrid, yGrid } = pixelToGrid(px, py, rect.width, rect.height, cand.meta);
    el.hoverCoords.hidden = false;
    el.hoverCoords.textContent = `${xGrid.toFixed(2)}, ${yGrid.toFixed(2)}`;
  });

  el.canvasFrame.addEventListener("mouseleave", () => {
    el.hoverCoords.hidden = true;
  });

  el.canvasFrame.addEventListener("click", (evt) => {
    const cand = activeCandidate();
    if (!cand || state.view === "sheet" || state.scale !== "fit") return;
    const rect = el.canvasFrame.getBoundingClientRect();
    const px = evt.clientX - rect.left;
    const py = evt.clientY - rect.top;
    const { xGrid, yGrid } = pixelToGrid(px, py, rect.width, rect.height, cand.meta);
    state.pins.push({
      id: state.pins.length + 1,
      candidate_id: cand.id,
      x_grid: xGrid,
      y_grid: yGrid,
      comment: "",
    });
    renumberPins();
    state.focusedPinIndex = state.pins.length - 1;
    renderAll(true);
  });

  el.submitBtn.addEventListener("click", async () => {
    el.submitBtn.disabled = true;
    el.submitStatus.textContent = "Saving review...";
    const cand = activeCandidate();
    renumberPins();
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
      state.pins = [];
      state.focusedPinIndex = -1;
      el.reviewSummary.value = "";
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
    const dirName = (data.dir || "").split("/").filter(Boolean).pop() || data.dir || "";
    el.sessionDir.textContent = dirName;
    el.sessionDir.title = data.dir || "";
    el.roundPill.textContent = `Round ${data.round || 1}`;
    el.candidateCount.textContent = `${data.candidates.length} candidate${data.candidates.length === 1 ? "" : "s"}`;
    renderAll();
  }

  loadSession();
})();
