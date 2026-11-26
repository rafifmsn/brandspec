(() => {
  const COS_30 = Math.cos(Math.PI / 6);
  const SVG_NS = "http://www.w3.org/2000/svg";

  const state = {
    session: null,
    activeId: null,
    tab: "review",
    sidebarMode: "candidates",
    view: "positive",
    scale: "fit",
    zoom: 1.0,
    surfaceHex: "",
    status: "revise",
    pins: [],
    focusedPinIndex: -1,
    leftCollapsed: false,
    fullscreen: false,
    pollHandle: null,
  };

  const el = {
    studioShell: document.getElementById("studio-shell"),
    sessionDir: document.getElementById("session-dir"),
    roundPill: document.getElementById("round-pill"),
    modeTabs: document.getElementById("mode-tabs"),
    reviewWorkspace: document.getElementById("review-workspace"),
    mockupsPanel: document.getElementById("mockups-panel"),
    mockupsGrid: document.getElementById("mockups-grid"),
    sidebarHeading: document.getElementById("sidebar-heading"),
    candidatesPanelBody: document.getElementById("candidates-panel-body"),
    historyPanelBody: document.getElementById("history-panel-body"),
    historyLogList: document.getElementById("history-log-list"),
    artboardWrap: document.getElementById("artboard-wrap"),
    canvasFrame: document.getElementById("canvas-frame"),
    markImage: document.getElementById("mark-image"),
    pinLayer: document.getElementById("pin-layer"),
    hoverCoords: document.getElementById("hover-coords"),
    metricsDock: document.getElementById("metrics-dock"),
    zoomReset: document.getElementById("zoom-reset"),
    surfaceHex: document.getElementById("surface-hex"),
    hexSwatch: document.getElementById("hex-swatch"),
    candidateTitle: document.getElementById("candidate-title"),
    candidateSubtitle: document.getElementById("candidate-subtitle"),
    pinCount: document.getElementById("pin-count"),
    clearPins: document.getElementById("clear-pins"),
    pinList: document.getElementById("pin-list"),
    reviewSummary: document.getElementById("review-summary"),
    submitBtn: document.getElementById("submit-review"),
    submitError: document.getElementById("submit-error"),
    warningsAccordion: document.getElementById("warnings-accordion"),
    warningsCount: document.getElementById("warnings-count"),
    warningsList: document.getElementById("warnings-list"),
    railToggleLeft: document.getElementById("rail-toggle-left"),
    railFullscreen: document.getElementById("rail-fullscreen"),
    zoomIn: document.getElementById("zoom-in"),
    zoomOut: document.getElementById("zoom-out"),
  };

  function isAwaitingAgent() {
    return Boolean(state.session && state.session.awaiting_agent);
  }

  function renumberPins() {
    state.pins.forEach((pin, idx) => {
      pin.id = idx + 1;
    });
    if (state.focusedPinIndex >= state.pins.length) {
      state.focusedPinIndex = state.pins.length - 1;
    }
  }

  function autoResizeTextarea(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  function createStatusIcon(status) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("width", "14");
    svg.setAttribute("height", "14");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.7");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    if (status === "approve") {
      path.setAttribute("d", "M3.2 8.4L6.4 11.5L12.8 4.8");
    } else if (status === "reject") {
      path.setAttribute("d", "M4 4L12 12M12 4L4 12");
    } else {
      path.setAttribute("d", "M8 3.2V9.2M8 12.2V12.5");
    }
    svg.appendChild(path);
    return svg;
  }

  function allSelectableCandidates() {
    if (!state.session) return [];
    const list = [...(state.session.candidates || [])];
    if (Array.isArray(state.session.round_groups)) {
      state.session.round_groups.forEach((group) => {
        if (Array.isArray(group.candidates)) {
          list.push(...group.candidates);
        }
      });
    }
    return list;
  }

  function activeCandidate() {
    const all = allSelectableCandidates();
    if (!all.length) return null;
    return all.find((c) => c.id === state.activeId) || all[0];
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

  function collectRounds() {
    if (!state.session) return [];
    const awaiting = isAwaitingAgent();
    const rounds = [];
    if (Array.isArray(state.session.history)) {
      state.session.history.forEach((item) => {
        rounds.push({ item, resolved: true });
      });
    }
    if (state.session.latest_review) {
      rounds.push({ item: state.session.latest_review, resolved: !awaiting });
    }
    return rounds;
  }

  function renderCandidateCard(cand) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "candidate-card" + (cand.id === state.activeId ? " is-selected" : "");

    const thumbBox = document.createElement("div");
    thumbBox.className = "candidate-thumb-box";
    const img = document.createElement("img");
    img.src = cand.files.logo_svg;
    img.alt = cand.label || cand.id;
    thumbBox.appendChild(img);

    const metaRow = document.createElement("div");
    metaRow.className = "candidate-card-meta tabular";
    const idSpan = document.createElement("span");
    idSpan.textContent = cand.label || cand.id;
    const statusSpan = document.createElement("span");
    statusSpan.textContent = cand.metrics && cand.metrics.passed ? "PASS" : "WARN";
    metaRow.appendChild(idSpan);
    metaRow.appendChild(statusSpan);

    btn.appendChild(thumbBox);
    btn.appendChild(metaRow);

    btn.addEventListener("click", () => {
      state.activeId = cand.id;
      renderAll();
    });
    return btn;
  }

  function renderLeftSidebar() {
    const awaiting = isAwaitingAgent();
    const latestRound =
      state.session && state.session.latest_review
        ? Number(state.session.latest_review.round || 1)
        : 1;
    const roundNum = awaiting ? latestRound : (state.session && state.session.round) || 1;
    const rounds = collectRounds();
    const isHistory = state.sidebarMode === "history";

    el.sidebarHeading.textContent = isHistory ? "Round History" : "Candidates";
    el.roundPill.textContent = isHistory ? `${rounds.length} logged` : `Round ${roundNum}`;
    el.candidatesPanelBody.hidden = isHistory;
    el.historyPanelBody.hidden = !isHistory;

    document.querySelectorAll("[data-sidebar]").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.sidebar === state.sidebarMode);
    });

    if (!isHistory) {
      el.candidatesPanelBody.innerHTML = "";
      const currentCandidates = state.session ? state.session.candidates : [];
      const currentGroup = document.createElement("div");
      currentGroup.className = "round-group";
      const curHead = document.createElement("div");
      curHead.className = "round-group-head";
      const curTitle = document.createElement("span");
      curTitle.className = "round-group-title tabular";
      curTitle.textContent = `Round ${roundNum}`;
      curHead.appendChild(curTitle);
      const curGrid = document.createElement("div");
      curGrid.className = "candidate-grid";
      currentCandidates.forEach((cand) => {
        curGrid.appendChild(renderCandidateCard(cand));
      });
      currentGroup.appendChild(curHead);
      currentGroup.appendChild(curGrid);
      el.candidatesPanelBody.appendChild(currentGroup);

      const archivedGroups =
        state.session && Array.isArray(state.session.round_groups)
          ? state.session.round_groups
          : [];
      archivedGroups.forEach((group) => {
        if (group.round === roundNum) {
          return;
        }
        const wrap = document.createElement("div");
        wrap.className = "round-group";
        const head = document.createElement("div");
        head.className = "round-group-head";
        const title = document.createElement("span");
        title.className = "round-group-title tabular";
        title.textContent = `Round ${group.round}`;
        head.appendChild(title);
        const grid = document.createElement("div");
        grid.className = "candidate-grid";
        group.candidates.forEach((cand) => {
          grid.appendChild(renderCandidateCard(cand));
        });
        wrap.appendChild(head);
        wrap.appendChild(grid);
        el.candidatesPanelBody.appendChild(wrap);
      });
      return;
    }

    el.historyLogList.innerHTML = "";
    if (rounds.length === 0) {
      const empty = document.createElement("div");
      empty.className = "history-log-empty";
      empty.textContent = "No submitted rounds yet.";
      el.historyLogList.appendChild(empty);
      return;
    }

    rounds
      .slice()
      .reverse()
      .forEach(({ item, resolved }) => {
        const row = document.createElement("div");
        row.className = "history-row" + (resolved ? " is-resolved" : "");

        const iconWrap = document.createElement("span");
        iconWrap.className = "history-icon";
        iconWrap.appendChild(createStatusIcon(item.status));

        const content = document.createElement("div");
        content.className = "history-content";

        const title = document.createElement("div");
        title.className = "history-title";
        const pinsCount = Array.isArray(item.pins) ? item.pins.length : 0;
        const target = item.selected_candidate ? ` · ${item.selected_candidate}` : "";
        title.textContent = `Round ${item.round}${target} (${pinsCount} pins)`;
        content.appendChild(title);

        if (item.summary) {
          const sum = document.createElement("div");
          sum.className = "history-summary";
          sum.textContent = item.summary;
          content.appendChild(sum);
        }

        row.appendChild(iconWrap);
        row.appendChild(content);
        el.historyLogList.appendChild(row);
      });
  }

  function renderStage() {
    const cand = activeCandidate();
    if (!cand) {
      el.candidateTitle.textContent = "No candidates";
      el.candidateSubtitle.textContent = "Compile a mark or sweep first.";
      el.markImage.removeAttribute("src");
      el.metricsDock.innerHTML = "";
      return;
    }

    const name = (cand.meta && cand.meta.name) || cand.label || cand.id;
    const concept = (cand.meta && cand.meta.concept) || "";
    el.candidateTitle.textContent = `${cand.id}: ${name}`;
    el.candidateSubtitle.textContent = concept;

    el.artboardWrap.style.transform = `scale(${state.zoom})`;
    el.zoomReset.textContent = `${Math.round(state.zoom * 100)}%`;

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
    const locked = isAwaitingAgent();
    el.pinCount.textContent = `(${state.pins.length})`;
    el.clearPins.hidden = locked || state.pins.length === 0;
    el.pinList.innerHTML = "";

    if (state.pins.length === 0) {
      const empty = document.createElement("div");
      empty.className = "pin-empty";
      empty.textContent = locked
        ? "Review submitted. Waiting for agent update."
        : "Click anywhere on the artboard to comment.";
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
      removeBtn.disabled = locked;
      removeBtn.addEventListener("click", (evt) => {
        evt.stopPropagation();
        if (isAwaitingAgent()) return;
        state.pins.splice(idx, 1);
        renumberPins();
        renderAll();
      });

      head.appendChild(title);
      head.appendChild(removeBtn);

      const textarea = document.createElement("textarea");
      textarea.rows = 1;
      textarea.className = "pin-textarea";
      textarea.value = pin.comment;
      textarea.disabled = locked;
      textarea.placeholder = "Describe geometric change at this coordinate";
      textarea.addEventListener("focus", () => {
        state.focusedPinIndex = idx;
        renderPinsOnCanvas(activeCandidate());
      });
      textarea.addEventListener("input", (evt) => {
        pin.comment = evt.target.value;
        autoResizeTextarea(textarea);
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
      card.appendChild(textarea);
      el.pinList.appendChild(card);
      autoResizeTextarea(textarea);

      if (focusNewInput && idx === state.pins.length - 1) {
        textarea.focus();
      }
    });
  }

  function renderReviewControls() {
    const locked = isAwaitingAgent();
    el.reviewSummary.disabled = locked;
    document.querySelectorAll(".decision-btn").forEach((btn) => {
      btn.disabled = locked;
    });
    el.submitBtn.disabled = locked;
    el.submitBtn.textContent = locked ? "Waiting for agent update" : "Submit Review";
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
    tabText.textContent = tokens.name || "Brandspec";
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
  }

  function renderAll(focusNewInput = false) {
    syncViewButtons();
    renderLeftSidebar();
    renderStage();
    renderPinList(focusNewInput);
    renderReviewControls();
    renderMockups();
  }

  function setFullscreen(enabled) {
    state.fullscreen = enabled;
    el.studioShell.classList.toggle("is-fullscreen", enabled);
    el.railFullscreen.classList.toggle("is-active", enabled);
  }

  function ensureAgentPoll() {
    if (isAwaitingAgent() && !state.pollHandle) {
      state.pollHandle = window.setInterval(() => {
        loadSession();
      }, 2500);
    } else if (!isAwaitingAgent() && state.pollHandle) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
    }
  }

  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      renderMockups();
    });
  });

  document.querySelectorAll("[data-sidebar]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.sidebarMode = btn.dataset.sidebar;
      if (state.fullscreen) {
        setFullscreen(false);
      }
      if (state.leftCollapsed) {
        state.leftCollapsed = false;
        el.reviewWorkspace.classList.remove("is-left-collapsed");
      }
      renderLeftSidebar();
    });
  });

  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
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
      if (isAwaitingAgent()) return;
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

  el.zoomReset.addEventListener("click", () => {
    state.zoom = 1.0;
    renderStage();
  });

  el.railToggleLeft.addEventListener("click", () => {
    if (state.fullscreen) {
      setFullscreen(false);
      state.leftCollapsed = false;
      el.reviewWorkspace.classList.remove("is-left-collapsed");
      return;
    }
    state.leftCollapsed = !state.leftCollapsed;
    el.reviewWorkspace.classList.toggle("is-left-collapsed", state.leftCollapsed);
  });

  el.railFullscreen.addEventListener("click", () => {
    setFullscreen(!state.fullscreen);
  });

  window.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && state.fullscreen) {
      setFullscreen(false);
    }
  });

  el.surfaceHex.addEventListener("input", (evt) => {
    state.surfaceHex = evt.target.value.trim();
    renderStage();
  });

  el.clearPins.addEventListener("click", () => {
    if (isAwaitingAgent()) return;
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
    if (!cand || state.view === "sheet" || state.scale !== "fit" || isAwaitingAgent()) return;
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
    if (isAwaitingAgent()) return;
    el.submitBtn.disabled = true;
    el.submitError.hidden = true;
    el.submitError.textContent = "";
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
        el.submitError.hidden = false;
        el.submitError.textContent = body.error || "Failed to save review.";
        el.submitBtn.disabled = false;
        return;
      }
      state.pins = [];
      state.focusedPinIndex = -1;
      el.reviewSummary.value = "";
      await loadSession();
    } catch (err) {
      el.submitError.hidden = false;
      el.submitError.textContent = `Error: ${err.message}`;
      el.submitBtn.disabled = false;
    }
  });

  async function loadSession() {
    const resp = await fetch("/api/session");
    const data = await resp.json();
    state.session = data;
    const all = allSelectableCandidates();
    if (!state.activeId || !all.some((c) => c.id === state.activeId)) {
      state.activeId = all.length > 0 ? all[0].id : null;
    }
    const dirName = (data.dir || "").split("/").filter(Boolean).pop() || data.dir || "";
    el.sessionDir.textContent = dirName;
    el.sessionDir.title = data.dir || "";
    renderAll();
    ensureAgentPoll();
  }

  loadSession();
})();
