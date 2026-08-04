(() => {
  "use strict";

  const canvas = document.getElementById("network-canvas");
  const shell = document.getElementById("graph-shell");
  const context = canvas.getContext("2d");
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("node-search");
  const searchOptions = document.getElementById("node-options");
  const minimumYears = document.getElementById("minimum-years");
  const graphDensity = document.getElementById("graph-density");
  const nsfStatus = document.getElementById("nsf-status");
  const verifiedOnly = document.getElementById("verified-only");
  const criticalOnly = document.getElementById("critical-only");
  const fundingFilters = [...document.querySelectorAll(".funding-filter")];
  const resetButton = document.getElementById("reset-view");
  const summary = document.getElementById("visible-summary");
  const tooltip = document.getElementById("graph-tooltip");
  const message = document.getElementById("graph-message");
  const emptyDetail = document.getElementById("empty-detail");
  const selectedDetail = document.getElementById("selected-detail");
  const detailTier = document.getElementById("detail-tier");
  const detailName = document.getElementById("detail-name");
  const detailId = document.getElementById("detail-id");
  const detailMetrics = document.getElementById("detail-metrics");
  const screeningBlock = document.getElementById("screening-block");
  const screeningStatus = document.getElementById("screening-status");
  const relationshipList = document.getElementById("relationship-list");
  const focusButton = document.getElementById("focus-node");
  const guardrailText = document.getElementById("guardrail-text");
  const downloadLinks = document.getElementById("download-links");

  const state = {
    payload: null,
    nodesById: new Map(),
    adjacency: new Map(),
    visibleNodes: [],
    visibleEdges: [],
    positions: new Map(),
    selectedNodeId: null,
    focusedNodeId: null,
    hoveredNodeId: null,
    width: 0,
    height: 0,
    worldWidth: 0,
    worldHeight: 0,
    transform: { x: 0, y: 0, scale: 1 },
    pointer: null,
  };

  const densityLimits = {
    overview: 500,
    expanded: 1800,
    all: Number.POSITIVE_INFINITY,
  };

  const kindDefinitions = {
    agency: { label: "Agency", column: 0.07, shape: "square", color: "agency" },
    nsf_award: { label: "NSF award", column: 0.25, shape: "roundRect", color: "nsfAward" },
    technology: { label: "CET area", column: 0.43, shape: "diamond", color: "technology" },
    legal_entity: { label: "Legal entity", column: 0.61, shape: "circle", color: "entity" },
    dod_award: { label: "DoD award", column: 0.86, shape: "roundRect", color: "dodAward" },
    prime: { label: "Tier 1 prime family", column: 0.22, shape: "square", color: "dodAward" },
    supplier: { label: "Tier 2 SBIR awardee", column: 0.78, shape: "circle", color: "entity" },
  };

  const numberFormatter = new Intl.NumberFormat("en-US");
  const moneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  });

  function resolveColor(variableName) {
    const probe = document.createElement("span");
    probe.style.color = `var(${variableName})`;
    probe.hidden = true;
    document.body.appendChild(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  }

  function colors() {
    return {
      agency: resolveColor("--agency"),
      nsfAward: resolveColor("--nsf-award"),
      technology: resolveColor("--technology"),
      entity: resolveColor("--entity"),
      dodAward: resolveColor("--dod-award"),
      edge: resolveColor("--edge"),
      candidate: resolveColor("--candidate"),
      text: resolveColor("--text"),
      surface: resolveColor("--surface"),
      focus: resolveColor("--focus"),
      critical: resolveColor("--critical"),
    };
  }

  let palette = colors();

  function formatMoney(value) {
    return moneyFormatter.format(Number(value || 0));
  }

  function nodeKind(node) {
    return kindDefinitions[node.kind] || {
      label: String(node.kind || "Record").replaceAll("_", " "),
      column: 0.5,
      shape: "circle",
      color: "entity",
    };
  }

  function edgeAmount(edge) {
    return Number(
      edge.signed_obligation_total ??
        edge.reported_subaward_amount ??
        edge.award_amount ??
        0,
    );
  }

  function isCandidate(edge) {
    return (
      Boolean(edge.candidate) ||
      String(edge.evidence_grade || "").includes("candidate") ||
      edge.match_confidence === "candidate_name"
    );
  }

  function edgeScore(edge) {
    const relationshipWeights = {
      received_dod_prime_funding: 7,
      received_reported_dod_subaward: 7,
      candidate_temporal_association: 5,
      received_nsf_award: 4,
      classified_as_cet: 3,
      issued_nsf_award: 2,
      dod_funding_authority: 1,
    };
    const relationshipWeight = relationshipWeights[edge.relationship_type] || 1;
    const amount = Math.max(0, Math.abs(edgeAmount(edge)));
    return (
      relationshipWeight * 1_000_000_000 +
      Number(edge.fiscal_years || 1) * 1_000_000 +
      Math.log10(amount + 1) * 10_000
    );
  }

  function buildIndexes(payload) {
    state.nodesById = new Map(payload.nodes.map((node) => [node.id, node]));
    state.adjacency = new Map(payload.nodes.map((node) => [node.id, []]));
    payload.edges.forEach((edge) => {
      if (!state.nodesById.has(edge.source) || !state.nodesById.has(edge.target)) return;
      state.adjacency.get(edge.source).push(edge);
      state.adjacency.get(edge.target).push(edge);
    });
    state.adjacency.forEach((edges) => edges.sort((a, b) => edgeScore(b) - edgeScore(a)));
  }

  function populateSearchOptions() {
    const fragment = document.createDocumentFragment();
    [...state.nodesById.values()]
      .sort((a, b) => String(a.label).localeCompare(String(b.label)))
      .forEach((node) => {
        const option = document.createElement("option");
        option.value = node.label;
        option.label = nodeKind(node).label;
        fragment.appendChild(option);
      });
    searchOptions.replaceChildren(fragment);
  }

  function selectedInstruments() {
    return new Set(fundingFilters.filter((input) => input.checked).map((input) => input.value));
  }

  function edgePassesFilters(edge) {
    const threshold = Number(minimumYears.value);
    if (Number(edge.fiscal_years || 1) < threshold) return false;
    if (verifiedOnly.checked && isCandidate(edge)) return false;
    const instruments = selectedInstruments();
    if (edge.instrument_group && !instruments.has(edge.instrument_group)) return false;
    if (
      nsfStatus.value !== "all" &&
      String(edge.nsf_awardee_status || "indeterminate") !== nsfStatus.value
    ) {
      return false;
    }
    if (criticalOnly.checked) {
      const source = state.nodesById.get(edge.source);
      const target = state.nodesById.get(edge.target);
      if (
        !edge.critical_supply_chain_review_candidate &&
        !source?.critical_supply_chain_review_candidate &&
        !target?.critical_supply_chain_review_candidate
      ) {
        return false;
      }
    }
    return true;
  }

  function filteredEdges() {
    const eligible = state.payload.edges.filter(edgePassesFilters);
    if (state.focusedNodeId) {
      return eligible.filter(
        (edge) => edge.source === state.focusedNodeId || edge.target === state.focusedNodeId,
      );
    }
    return eligible
      .slice()
      .sort((a, b) => edgeScore(b) - edgeScore(a))
      .slice(0, densityLimits[graphDensity.value]);
  }

  function rebuildVisibleGraph({ fit = true } = {}) {
    if (!state.payload) return;
    state.visibleEdges = filteredEdges();
    const ids = new Set();
    state.visibleEdges.forEach((edge) => {
      ids.add(edge.source);
      ids.add(edge.target);
    });
    if (state.focusedNodeId && state.nodesById.has(state.focusedNodeId)) {
      ids.add(state.focusedNodeId);
    }
    state.visibleNodes = [...ids].map((id) => state.nodesById.get(id)).filter(Boolean);
    layoutVisibleGraph();
    if (fit) fitGraph();
    updateSummary();
    if (state.selectedNodeId) updateDetail(state.selectedNodeId);
    render();
  }

  function layoutVisibleGraph() {
    const degree = new Map(state.visibleNodes.map((node) => [node.id, 0]));
    state.visibleEdges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    });
    const groups = new Map();
    state.visibleNodes.forEach((node) => {
      if (!groups.has(node.kind)) groups.set(node.kind, []);
      groups.get(node.kind).push(node);
    });
    groups.forEach((nodes) => {
      nodes.sort(
        (a, b) =>
          (degree.get(b.id) || 0) - (degree.get(a.id) || 0) ||
          String(a.label).localeCompare(String(b.label)),
      );
    });
    const largestColumn = Math.max(1, ...[...groups.values()].map((nodes) => nodes.length));
    const spacing =
      largestColumn > 800 ? 8 : largestColumn > 300 ? 11 : largestColumn > 100 ? 16 : 28;
    state.worldWidth = Math.max(state.width, state.payload.schema_version === "2.0" ? 1480 : 980);
    state.worldHeight = Math.max(state.height, Math.min(11000, 120 + largestColumn * spacing));
    groups.forEach((nodes, kind) => {
      const x = state.worldWidth * nodeKind({ kind }).column;
      const available = state.worldHeight - 100;
      nodes.forEach((node, index) => {
        const y = 50 + ((index + 0.5) / Math.max(nodes.length, 1)) * available;
        const previous = state.positions.get(node.id);
        state.positions.set(node.id, {
          x: previous?.pinned ? previous.x : x,
          y: previous?.pinned ? previous.y : y,
          pinned: previous?.pinned || false,
        });
      });
    });
  }

  function fitGraph() {
    if (!state.visibleNodes.length) {
      state.transform = { x: 0, y: 0, scale: 1 };
      return;
    }
    const padding = 42;
    const scale = Math.min(
      1.15,
      (state.width - padding * 2) / state.worldWidth,
      (state.height - padding * 2) / state.worldHeight,
    );
    state.transform = {
      scale,
      x: (state.width - state.worldWidth * scale) / 2,
      y: (state.height - state.worldHeight * scale) / 2,
    };
  }

  function screenToWorld(x, y) {
    return {
      x: (x - state.transform.x) / state.transform.scale,
      y: (y - state.transform.y) / state.transform.scale,
    };
  }

  function nodeRadius(node) {
    const degree = state.adjacency.get(node.id)?.length || 1;
    const base = node.kind === "agency" ? 7 : node.kind.includes("award") ? 6 : 5;
    return base + Math.min(6, Math.log2(degree + 1));
  }

  function drawNodeShape(node, position, radius) {
    const definition = nodeKind(node);
    context.beginPath();
    if (definition.shape === "square") {
      context.rect(position.x - radius, position.y - radius, radius * 2, radius * 2);
    } else if (definition.shape === "roundRect") {
      context.roundRect(position.x - radius * 1.2, position.y - radius, radius * 2.4, radius * 2, 3);
    } else if (definition.shape === "diamond") {
      context.moveTo(position.x, position.y - radius * 1.25);
      context.lineTo(position.x + radius * 1.25, position.y);
      context.lineTo(position.x, position.y + radius * 1.25);
      context.lineTo(position.x - radius * 1.25, position.y);
      context.closePath();
    } else {
      context.arc(position.x, position.y, radius, 0, Math.PI * 2);
    }
  }

  function render() {
    if (!state.width || !state.height) return;
    context.clearRect(0, 0, state.width, state.height);
    context.save();
    context.translate(state.transform.x, state.transform.y);
    context.scale(state.transform.scale, state.transform.scale);
    const selectedNeighbors = new Set();
    if (state.selectedNodeId) {
      (state.adjacency.get(state.selectedNodeId) || []).forEach((edge) => {
        selectedNeighbors.add(edge.source);
        selectedNeighbors.add(edge.target);
      });
    }
    state.visibleEdges.forEach((edge) => {
      const source = state.positions.get(edge.source);
      const target = state.positions.get(edge.target);
      if (!source || !target) return;
      const highlighted =
        !state.selectedNodeId ||
        edge.source === state.selectedNodeId ||
        edge.target === state.selectedNodeId;
      const amount = Math.abs(edgeAmount(edge));
      context.beginPath();
      context.moveTo(source.x, source.y);
      const horizontalDistance = target.x - source.x;
      const controlOffset = Math.max(45, Math.abs(horizontalDistance) * 0.42);
      const direction = Math.sign(horizontalDistance || 1);
      context.bezierCurveTo(
        source.x + controlOffset * direction,
        source.y,
        target.x - controlOffset * direction,
        target.y,
        target.x,
        target.y,
      );
      context.strokeStyle = isCandidate(edge) ? palette.candidate : palette.edge;
      context.globalAlpha = highlighted ? 0.34 + Math.min(0.36, Number(edge.fiscal_years || 1) * 0.07) : 0.08;
      context.lineWidth = Math.max(0.8, Math.min(5, 0.8 + Math.log10(amount + 1) / 3));
      context.setLineDash(isCandidate(edge) ? [7, 5] : []);
      context.stroke();
    });
    context.setLineDash([]);
    context.globalAlpha = 1;

    state.visibleNodes.forEach((node) => {
      const position = state.positions.get(node.id);
      if (!position) return;
      const radius = nodeRadius(node);
      const selected = node.id === state.selectedNodeId;
      const related = !state.selectedNodeId || selected || selectedNeighbors.has(node.id);
      const definition = nodeKind(node);
      context.globalAlpha = related ? 1 : 0.16;
      drawNodeShape(node, position, radius);
      context.fillStyle = palette[definition.color] || palette.entity;
      context.fill();
      if (node.critical_supply_chain_review_candidate) {
        context.strokeStyle = palette.critical;
        context.lineWidth = 3 / state.transform.scale;
        context.stroke();
      }
      if (selected || node.id === state.hoveredNodeId) {
        context.strokeStyle = selected ? palette.focus : palette.text;
        context.lineWidth = 2.5 / state.transform.scale;
        context.stroke();
      }
      const labelEligible =
        selected ||
        node.id === state.hoveredNodeId ||
        (state.visibleNodes.length < 150 && state.transform.scale > 0.42);
      if (labelEligible) {
        context.globalAlpha = 1;
        context.fillStyle = palette.text;
        context.font = `${Math.max(10, 12 / state.transform.scale)}px Inter, system-ui, sans-serif`;
        context.textBaseline = "middle";
        const placeLeft = definition.column > 0.72;
        context.textAlign = placeLeft ? "right" : "left";
        const offset = radius + 6 / state.transform.scale;
        context.fillText(
          node.label,
          position.x + (placeLeft ? -offset : offset),
          position.y,
          280 / state.transform.scale,
        );
      }
    });
    context.globalAlpha = 1;
    context.restore();
  }

  function nodeAt(screenX, screenY) {
    const world = screenToWorld(screenX, screenY);
    let match = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    state.visibleNodes.forEach((node) => {
      const position = state.positions.get(node.id);
      if (!position) return;
      const distance = Math.hypot(position.x - world.x, position.y - world.y);
      const tolerance = nodeRadius(node) * 1.4 + 7 / state.transform.scale;
      if (distance <= tolerance && distance < bestDistance) {
        match = node;
        bestDistance = distance;
      }
    });
    return match;
  }

  function updateSummary() {
    const counts = new Map();
    state.visibleNodes.forEach((node) => counts.set(node.kind, (counts.get(node.kind) || 0) + 1));
    const nodeSummary = [...counts.entries()]
      .sort((a, b) => (kindDefinitions[a[0]]?.column || 0.5) - (kindDefinitions[b[0]]?.column || 0.5))
      .map(([kind, count]) => `${numberFormatter.format(count)} ${nodeKind({ kind }).label.toLowerCase()}${count === 1 ? "" : "s"}`)
      .join(" · ");
    const focus = state.focusedNodeId ? " · focused neighborhood" : "";
    const candidate = verifiedOnly.checked ? " · verified only" : " · candidates visible";
    summary.textContent = `${nodeSummary || "0 nodes"} · ${numberFormatter.format(
      state.visibleEdges.length,
    )} relationships${candidate}${focus}`;
    if (!state.visibleEdges.length) {
      showMessage("No relationships meet the current filters.");
    } else {
      hideMessage();
    }
  }

  function showMessage(text) {
    message.textContent = text;
    message.hidden = false;
  }

  function hideMessage() {
    message.hidden = true;
  }

  function metric(label, value) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value;
    wrapper.append(term, description);
    return wrapper;
  }

  function detailValue(label, value) {
    if (value === null || value === undefined || value === "") return "Unknown";
    const normalizedLabel = label.toLocaleLowerCase();
    if (
      typeof value === "number" &&
      ["amount", "funding", "obligation"].some((token) => normalizedLabel.includes(token))
    ) {
      return formatMoney(value);
    }
    if (typeof value === "number") return numberFormatter.format(value);
    if (Array.isArray(value)) return value.join(", ");
    return String(value).replaceAll("_", " ");
  }

  function updateDetail(nodeId) {
    const node = state.nodesById.get(nodeId);
    if (!node) return;
    emptyDetail.hidden = true;
    selectedDetail.hidden = false;
    detailTier.textContent = nodeKind(node).label;
    detailName.textContent = node.label;
    detailId.textContent = node.record_id || node.organization_id || node.id;
    const metrics = [metric("Visible relationships", numberFormatter.format(node.edge_count || 0))];
    Object.entries(node.details || {}).forEach(([label, value]) => {
      metrics.push(metric(label, detailValue(label, value)));
    });
    detailMetrics.replaceChildren(...metrics);

    const interpretationParts = [];
    if (node.match_method) interpretationParts.push(`Match method: ${node.match_method}.`);
    if (node.match_confidence) interpretationParts.push(`Confidence: ${node.match_confidence}.`);
    if (node.critical_supply_chain_review_candidate) {
      interpretationParts.push("This record meets the CET review screen; criticality is not assessed.");
    }
    if (node.specific_award_usage_status === "not_established") {
      interpretationParts.push("Use of a specific NSF-funded capability is not established.");
    }
    if (node.source_url) interpretationParts.push(`Direct source: ${node.source_url}`);
    screeningBlock.hidden = interpretationParts.length === 0;
    screeningStatus.textContent = interpretationParts.join(" ");

    const visibleEdgeIds = new Set(state.visibleEdges.map((edge) => edge.id));
    const relationships = (state.adjacency.get(nodeId) || [])
      .filter((edge) => visibleEdgeIds.has(edge.id))
      .slice(0, 20);
    const fragment = document.createDocumentFragment();
    relationships.forEach((edge) => {
      const otherId = edge.source === nodeId ? edge.target : edge.source;
      const other = state.nodesById.get(otherId);
      if (!other) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `relationship-button${isCandidate(edge) ? " candidate" : ""}`;
      button.addEventListener("click", () => selectNode(otherId, { ensureVisible: true }));
      const name = document.createElement("span");
      name.className = "relationship-name";
      name.textContent = other.label;
      const meta = document.createElement("span");
      meta.className = "relationship-meta";
      const amount = edgeAmount(edge);
      const amountLabel = amount ? ` · ${formatMoney(amount)}` : "";
      meta.textContent = `${edge.label || edge.relationship_type}${amountLabel}`;
      const sourceIds = edge.source_record_ids || [];
      if (sourceIds.length) button.title = `Source IDs: ${sourceIds.join(", ")}`;
      button.append(name, meta);
      fragment.appendChild(button);
    });
    relationshipList.replaceChildren(fragment);
    focusButton.textContent = state.focusedNodeId === nodeId ? "Show overview" : "Focus neighborhood";
  }

  function selectNode(nodeId, { ensureVisible = false } = {}) {
    const node = state.nodesById.get(nodeId);
    if (!node) return;
    if (ensureVisible && !state.visibleNodes.some((visible) => visible.id === nodeId)) {
      state.focusedNodeId = nodeId;
      rebuildVisibleGraph();
    }
    state.selectedNodeId = nodeId;
    updateDetail(nodeId);
    render();
  }

  function findNode(query) {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return null;
    return (
      [...state.nodesById.values()]
        .filter((node) =>
          [node.label, node.record_id, node.organization_id, node.id]
            .filter(Boolean)
            .some((value) => String(value).toLocaleLowerCase().includes(normalized)),
        )
        .sort((a, b) => {
          const aLabel = String(a.label).toLocaleLowerCase();
          const bLabel = String(b.label).toLocaleLowerCase();
          const aExact = aLabel === normalized ? 1 : 0;
          const bExact = bLabel === normalized ? 1 : 0;
          const aStarts = aLabel.startsWith(normalized) ? 1 : 0;
          const bStarts = bLabel.startsWith(normalized) ? 1 : 0;
          return bExact - aExact || bStarts - aStarts || (b.edge_count || 0) - (a.edge_count || 0);
        })[0] || null
    );
  }

  function resetExplorer() {
    state.focusedNodeId = null;
    state.selectedNodeId = null;
    state.hoveredNodeId = null;
    state.positions.clear();
    emptyDetail.hidden = false;
    selectedDetail.hidden = true;
    searchInput.value = "";
    minimumYears.value = "1";
    graphDensity.value = "overview";
    nsfStatus.value = "all";
    verifiedOnly.checked = true;
    criticalOnly.checked = false;
    fundingFilters.forEach((input) => {
      input.checked = true;
    });
    rebuildVisibleGraph();
  }

  function csvCell(value) {
    const rendered =
      value !== null && typeof value === "object" ? JSON.stringify(value) : String(value ?? "");
    return `"${rendered.replaceAll('"', '""')}"`;
  }

  function downloadVisibleRelationships() {
    const priority = [
      "id",
      "relationship_type",
      "label",
      "source",
      "target",
      "funding_mode",
      "instrument_group",
      "signed_obligation_total",
      "fiscal_years",
      "match_method",
      "match_confidence",
      "specific_award_usage_status",
      "critical_supply_chain_status",
      "source_record_ids",
      "source_paths",
      "source_sha256s",
      "source_urls",
    ];
    const available = new Set(state.visibleEdges.flatMap((edge) => Object.keys(edge)));
    const fields = [
      ...priority.filter((field) => available.has(field)),
      ...[...available].filter((field) => !priority.includes(field)).sort(),
    ];
    const rows = [fields.map(csvCell).join(",")];
    state.visibleEdges.forEach((edge) => {
      rows.push(fields.map((field) => csvCell(edge[field])).join(","));
    });
    const blob = new Blob([`${rows.join("\r\n")}\r\n`], { type: "text/csv;charset=utf-8" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `nsf-dod-visible-relationships-${state.payload.analysis_date || "undated"}.csv`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(href), 0);
  }

  function populateDownloads(downloads) {
    const entries = Object.entries(downloads || {});
    const label = document.createElement("strong");
    label.textContent = "Download evidence:";
    const links = entries.map(([name, href]) => {
      const link = document.createElement("a");
      link.href = href;
      link.download = "";
      link.textContent = name;
      return link;
    });
    const filteredDownload = document.createElement("button");
    filteredDownload.type = "button";
    filteredDownload.className = "download-filtered-button";
    filteredDownload.textContent = "Visible relationships CSV";
    filteredDownload.addEventListener("click", downloadVisibleRelationships);
    downloadLinks.replaceChildren(label, filteredDownload, ...links);
    downloadLinks.hidden = false;
  }

  function pointerCoordinates(event) {
    const bounds = canvas.getBoundingClientRect();
    return { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  }

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    const point = pointerCoordinates(event);
    const node = nodeAt(point.x, point.y);
    state.pointer = {
      id: event.pointerId,
      startX: point.x,
      startY: point.y,
      lastX: point.x,
      lastY: point.y,
      nodeId: node?.id || null,
      moved: false,
    };
    canvas.classList.add("is-dragging");
  });

  canvas.addEventListener("pointermove", (event) => {
    const point = pointerCoordinates(event);
    if (state.pointer?.id === event.pointerId) {
      const dx = point.x - state.pointer.lastX;
      const dy = point.y - state.pointer.lastY;
      state.pointer.moved ||=
        Math.hypot(point.x - state.pointer.startX, point.y - state.pointer.startY) > 3;
      if (state.pointer.nodeId) {
        const position = state.positions.get(state.pointer.nodeId);
        if (position) {
          position.x += dx / state.transform.scale;
          position.y += dy / state.transform.scale;
          position.pinned = true;
        }
      } else {
        state.transform.x += dx;
        state.transform.y += dy;
      }
      state.pointer.lastX = point.x;
      state.pointer.lastY = point.y;
      tooltip.hidden = true;
      render();
      return;
    }
    const node = nodeAt(point.x, point.y);
    state.hoveredNodeId = node?.id || null;
    if (node) {
      tooltip.textContent = `${node.label} · ${nodeKind(node).label}`;
      tooltip.style.left = `${Math.min(state.width - 270, Math.max(8, point.x + 12))}px`;
      tooltip.style.top = `${Math.max(8, point.y - 18)}px`;
      tooltip.hidden = false;
    } else {
      tooltip.hidden = true;
    }
    render();
  });

  function finishPointer(event) {
    if (!state.pointer || state.pointer.id !== event.pointerId) return;
    const point = pointerCoordinates(event);
    const clickedNode = !state.pointer.moved ? nodeAt(point.x, point.y) : null;
    if (clickedNode) selectNode(clickedNode.id);
    state.pointer = null;
    canvas.classList.remove("is-dragging");
  }

  canvas.addEventListener("pointerup", finishPointer);
  canvas.addEventListener("pointercancel", finishPointer);
  canvas.addEventListener("pointerleave", () => {
    if (!state.pointer) {
      state.hoveredNodeId = null;
      tooltip.hidden = true;
      render();
    }
  });
  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const point = pointerCoordinates(event);
      const before = screenToWorld(point.x, point.y);
      const factor = Math.exp(-event.deltaY * 0.0012);
      state.transform.scale = Math.max(0.035, Math.min(4, state.transform.scale * factor));
      state.transform.x = point.x - before.x * state.transform.scale;
      state.transform.y = point.y - before.y * state.transform.scale;
      render();
    },
    { passive: false },
  );

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const node = findNode(searchInput.value);
    if (!node) {
      showMessage(`No graph record matched “${searchInput.value.trim()}”.`);
      return;
    }
    hideMessage();
    if (node.kind === "legal_entity" && nsfStatus.value !== "all") {
      nsfStatus.value = node.nsf_awardee_status;
    }
    if (!node.critical_supply_chain_review_candidate) criticalOnly.checked = false;
    state.focusedNodeId = node.id;
    rebuildVisibleGraph();
    selectNode(node.id);
  });

  [minimumYears, graphDensity, nsfStatus, verifiedOnly, criticalOnly, ...fundingFilters].forEach(
    (control) => control.addEventListener("change", () => rebuildVisibleGraph()),
  );
  resetButton.addEventListener("click", resetExplorer);
  focusButton.addEventListener("click", () => {
    if (!state.selectedNodeId) return;
    state.focusedNodeId = state.focusedNodeId === state.selectedNodeId ? null : state.selectedNodeId;
    rebuildVisibleGraph();
    selectNode(state.selectedNodeId);
  });

  function resizeCanvas() {
    const bounds = shell.getBoundingClientRect();
    const devicePixelRatio = window.devicePixelRatio || 1;
    state.width = Math.max(320, Math.round(bounds.width));
    state.height = Math.max(420, Math.round(bounds.height));
    canvas.width = Math.round(state.width * devicePixelRatio);
    canvas.height = Math.round(state.height * devicePixelRatio);
    canvas.style.width = `${state.width}px`;
    canvas.style.height = `${state.height}px`;
    context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    if (state.payload) rebuildVisibleGraph();
  }

  async function loadNetwork() {
    try {
      const response = await fetch("data/network.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (!Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
        throw new Error("invalid graph payload");
      }
      state.payload = payload;
      buildIndexes(payload);
      populateSearchOptions();
      populateDownloads(payload.downloads);
      guardrailText.textContent = payload.guardrails?.[0] || guardrailText.textContent;
      rebuildVisibleGraph();
    } catch (error) {
      summary.textContent = "Network data unavailable";
      showMessage(
        "Generate data/network.json with: uv run python scripts/data/export_sbir_dib_network_web.py",
      );
      console.error("Unable to load supply network", error);
    }
  }

  const resizeObserver = new ResizeObserver(resizeCanvas);
  resizeObserver.observe(shell);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    palette = colors();
    render();
  });
  resizeCanvas();
  loadNetwork();
})();
