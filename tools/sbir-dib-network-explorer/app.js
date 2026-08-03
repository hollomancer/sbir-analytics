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
  const nsfOnly = document.getElementById("nsf-only");
  const criticalOnly = document.getElementById("critical-only");
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
    overview: 320,
    expanded: 1200,
    all: Number.POSITIVE_INFINITY,
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
      prime: resolveColor("--prime"),
      supplier: resolveColor("--supplier"),
      edge: resolveColor("--edge"),
      text: resolveColor("--text"),
      surface: resolveColor("--surface"),
      focus: resolveColor("--focus"),
      nsf: resolveColor("--nsf"),
      critical: resolveColor("--critical"),
    };
  }

  let palette = colors();

  function formatMoney(value) {
    return moneyFormatter.format(Number(value || 0));
  }

  function formatPercent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    return `${Math.round(Number(value) * 100)}%`;
  }

  function screeningLabel(status) {
    const labels = {
      single_observed_prime: "Only one prime family is visible in this public-data slice.",
      high_observed_customer_concentration:
        "At least 75% of positive net observed amount is associated with one prime family.",
      multiple_observed_primes: "Observed customer relationships are distributed across prime families.",
      nonpositive_reported_total:
        "No positive net edge remains after reported corrections in this slice.",
      not_screened: "No supplier exposure screen is available.",
    };
    return labels[status] || String(status).replaceAll("_", " ");
  }

  function edgeScore(edge) {
    const amount = Math.max(0, Number(edge.reported_subaward_amount || 0));
    return Number(edge.fiscal_years || 0) * 1_000_000 + Math.log10(amount + 1) * 10_000;
  }

  function buildIndexes(payload) {
    state.nodesById = new Map(payload.nodes.map((node) => [node.id, node]));
    state.adjacency = new Map(payload.nodes.map((node) => [node.id, []]));
    payload.edges.forEach((edge) => {
      if (!state.adjacency.has(edge.source)) state.adjacency.set(edge.source, []);
      if (!state.adjacency.has(edge.target)) state.adjacency.set(edge.target, []);
      state.adjacency.get(edge.source).push(edge);
      state.adjacency.get(edge.target).push(edge);
    });
    state.adjacency.forEach((edges) => edges.sort((a, b) => edgeScore(b) - edgeScore(a)));
  }

  function populateSearchOptions() {
    const fragment = document.createDocumentFragment();
    [...state.nodesById.values()]
      .sort((a, b) => a.label.localeCompare(b.label))
      .forEach((node) => {
        const option = document.createElement("option");
        option.value = node.label;
        option.label = node.kind === "prime" ? "Tier 1 prime family" : "Tier 2 SBIR awardee";
        fragment.appendChild(option);
      });
    searchOptions.replaceChildren(fragment);
  }

  function filteredEdges() {
    const threshold = Number(minimumYears.value);
    const eligible = state.payload.edges.filter((edge) => {
      const source = state.nodesById.get(edge.source);
      return (
        Number(edge.fiscal_years) >= threshold &&
        (!nsfOnly.checked || Boolean(source?.nsf_sbir_awardee)) &&
        (!criticalOnly.checked || Boolean(source?.critical_supply_chain_review_candidate))
      );
    });
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
    if (state.focusedNodeId && state.nodesById.has(state.focusedNodeId)) ids.add(state.focusedNodeId);
    state.visibleNodes = [...ids].map((id) => state.nodesById.get(id)).filter(Boolean);
    layoutVisibleGraph();
    if (fit) fitGraph();
    updateSummary();
    render();
  }

  function layoutVisibleGraph() {
    const primes = state.visibleNodes.filter((node) => node.kind === "prime");
    const suppliers = state.visibleNodes.filter((node) => node.kind === "supplier");
    const degree = new Map(state.visibleNodes.map((node) => [node.id, 0]));
    state.visibleEdges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    });
    primes.sort(
      (a, b) =>
        (degree.get(b.id) || 0) - (degree.get(a.id) || 0) ||
        Number(b.reported_subaward_amount || 0) - Number(a.reported_subaward_amount || 0),
    );
    const primeOrder = new Map(primes.map((node, index) => [node.id, index]));
    const supplierPrimeOrders = new Map(suppliers.map((node) => [node.id, []]));
    state.visibleEdges.forEach((edge) => {
      const orders = supplierPrimeOrders.get(edge.source);
      if (orders) orders.push(primeOrder.get(edge.target) || 0);
    });
    const barycenter = (node) => {
      const orders = supplierPrimeOrders.get(node.id) || [];
      if (!orders.length) return Number.MAX_SAFE_INTEGER;
      return orders.reduce((total, order) => total + order, 0) / orders.length;
    };
    suppliers.sort((a, b) => {
      return barycenter(a) - barycenter(b) || (degree.get(b.id) || 0) - (degree.get(a.id) || 0);
    });

    const largestTier = Math.max(primes.length, suppliers.length, 1);
    const spacing = largestTier > 800 ? 7 : largestTier > 300 ? 10 : largestTier > 100 ? 14 : 24;
    state.worldWidth = Math.max(state.width, 960);
    state.worldHeight = Math.max(state.height, Math.min(9200, 100 + largestTier * spacing));

    const placeTier = (nodes, x) => {
      const available = state.worldHeight - 90;
      nodes.forEach((node, index) => {
        const y = 45 + ((index + 0.5) / Math.max(nodes.length, 1)) * available;
        const previous = state.positions.get(node.id);
        state.positions.set(node.id, {
          x: previous?.pinned ? previous.x : x,
          y: previous?.pinned ? previous.y : y,
          pinned: previous?.pinned || false,
        });
      });
    };
    placeTier(primes, state.worldWidth * 0.22);
    placeTier(suppliers, state.worldWidth * 0.78);
  }

  function fitGraph() {
    if (!state.visibleNodes.length) {
      state.transform = { x: 0, y: 0, scale: 1 };
      return;
    }
    const padding = 42;
    const scale = Math.min(
      1.2,
      (state.width - padding * 2) / state.worldWidth,
      (state.height - padding * 2) / state.worldHeight,
    );
    state.transform = {
      scale,
      x: (state.width - state.worldWidth * scale) / 2,
      y: (state.height - state.worldHeight * scale) / 2,
    };
  }

  function worldToScreen(position) {
    return {
      x: position.x * state.transform.scale + state.transform.x,
      y: position.y * state.transform.scale + state.transform.y,
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
    return (node.kind === "prime" ? 6.5 : 4.5) + Math.min(6, Math.log2(degree + 1));
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
        !state.selectedNodeId || edge.source === state.selectedNodeId || edge.target === state.selectedNodeId;
      context.beginPath();
      context.moveTo(source.x, source.y);
      const bend = Math.min(90, Math.abs(target.y - source.y) * 0.18);
      context.bezierCurveTo(source.x + 170, source.y + bend, target.x - 170, target.y - bend, target.x, target.y);
      context.strokeStyle = palette.edge;
      context.globalAlpha = highlighted ? 0.22 + Number(edge.fiscal_years) * 0.1 : 0.08;
      context.lineWidth = Math.max(
        0.7,
        Math.min(4.5, 0.7 + Math.log10(Math.max(1, Number(edge.reported_subaward_amount))) / 3),
      );
      context.stroke();
    });
    context.globalAlpha = 1;

    state.visibleNodes.forEach((node) => {
      const position = state.positions.get(node.id);
      if (!position) return;
      const radius = nodeRadius(node);
      const selected = node.id === state.selectedNodeId;
      const related = !state.selectedNodeId || selected || selectedNeighbors.has(node.id);
      context.globalAlpha = related ? 1 : 0.16;
      context.beginPath();
      if (node.kind === "prime") {
        context.roundRect(position.x - radius, position.y - radius, radius * 2, radius * 2, 2.5);
      } else {
        context.arc(position.x, position.y, radius, 0, Math.PI * 2);
      }
      context.fillStyle = node.kind === "prime" ? palette.prime : palette.supplier;
      context.fill();
      if (node.kind === "supplier" && node.nsf_sbir_awardee) {
        context.strokeStyle = node.critical_supply_chain_review_candidate
          ? palette.critical
          : palette.nsf;
        context.lineWidth = (node.critical_supply_chain_review_candidate ? 3 : 2) / state.transform.scale;
        context.stroke();
      }
      if (selected || node.id === state.hoveredNodeId) {
        context.strokeStyle = selected ? palette.focus : palette.text;
        context.lineWidth = 2.5 / state.transform.scale;
        context.stroke();
      }
      if (
        selected ||
        node.id === state.hoveredNodeId ||
        (node.kind === "prime" && state.visibleNodes.length < 130 && state.transform.scale > 0.5)
      ) {
        context.globalAlpha = 1;
        context.fillStyle = palette.text;
        context.font = `${Math.max(10, 12 / state.transform.scale)}px Inter, system-ui, sans-serif`;
        context.textBaseline = "middle";
        context.textAlign = node.kind === "prime" ? "right" : "left";
        const offset = radius + 5 / state.transform.scale;
        context.fillText(
          node.label,
          position.x + (node.kind === "prime" ? -offset : offset),
          position.y,
          260 / state.transform.scale,
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
      const tolerance = nodeRadius(node) + 7 / state.transform.scale;
      if (distance <= tolerance && distance < bestDistance) {
        match = node;
        bestDistance = distance;
      }
    });
    return match;
  }

  function updateSummary() {
    const primes = state.visibleNodes.filter((node) => node.kind === "prime").length;
    const suppliers = state.visibleNodes.length - primes;
    const focus = state.focusedNodeId ? " · focused neighborhood" : "";
    const nsf = nsfOnly.checked ? " · NSF SBIR awardees only" : "";
    const critical = criticalOnly.checked ? " · CET supply-chain screen only" : "";
    summary.textContent = `${numberFormatter.format(suppliers)} suppliers · ${numberFormatter.format(
      primes,
    )} prime families · ${numberFormatter.format(
      state.visibleEdges.length,
    )} relationships${nsf}${critical}${focus}`;
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

  function selectNode(nodeId, { ensureVisible = false } = {}) {
    const node = state.nodesById.get(nodeId);
    if (!node) return;
    if (ensureVisible && !state.visibleNodes.some((visible) => visible.id === nodeId)) {
      state.focusedNodeId = nodeId;
      rebuildVisibleGraph();
    }
    state.selectedNodeId = nodeId;
    emptyDetail.hidden = true;
    selectedDetail.hidden = false;
    detailTier.textContent = node.kind === "prime" ? "Tier 1 prime family" : "Tier 2 SBIR awardee";
    detailName.textContent = node.label;
    detailId.textContent = node.organization_id;
    const metrics = [
      metric("Observed amount", formatMoney(node.reported_subaward_amount)),
      metric("Relationships", numberFormatter.format(node.edge_count || 0)),
      metric("Maximum persistence", `${node.max_fiscal_years || 0} FY`),
      metric(
        node.kind === "prime" ? "SBIR suppliers" : "Prime families",
        numberFormatter.format(
          node.kind === "prime" ? node.supplier_count || 0 : node.prime_family_count || 0,
        ),
      ),
    ];
    if (node.kind === "supplier" && node.nsf_sbir_awardee) {
      metrics.push(
        metric("NSF SBIR awards", numberFormatter.format(node.nsf_sbir_award_count || 0)),
        metric("NSF SBIR funding", formatMoney(node.nsf_sbir_award_amount)),
      );
    }
    if (node.kind === "supplier" && node.critical_supply_chain_review_candidate) {
      metrics.push(
        metric(
          "CET-screened awards",
          numberFormatter.format(node.critical_supply_chain_candidate_award_count || 0),
        ),
      );
    }
    detailMetrics.replaceChildren(...metrics);

    if (node.kind === "supplier") {
      screeningBlock.hidden = false;
      const exposure = `${screeningLabel(node.screening_status)} HHI ${Number(
        node.observed_customer_hhi || 0,
      ).toFixed(2)}; top observed share ${formatPercent(node.top_observed_prime_share)}.`;
      if (node.nsf_sbir_awardee) {
        const topics = String(node.nsf_sbir_topic_codes || "")
          .split("|")
          .filter(Boolean)
          .slice(0, 8)
          .join(", ");
        const firstYear = Number(node.nsf_sbir_first_award_year || 0);
        const latestYear = Number(node.nsf_sbir_latest_award_year || 0);
        const years = firstYear && latestYear ? ` (${firstYear}–${latestYear})` : "";
        const topicText = topics ? ` Topics: ${topics}.` : "";
        screeningStatus.textContent = `${exposure} NSF SBIR review candidate with ${numberFormatter.format(
          node.nsf_sbir_award_count || 0,
        )} award(s)${years}.${topicText} This does not establish supply-chain criticality.`;
        if (node.critical_supply_chain_review_candidate) {
          const cets = String(node.primary_cets || "").replaceAll("|", ", ");
          const categories = String(node.dod_supply_chain_categories || "").replaceAll(
            "|",
            ", ",
          );
          screeningStatus.textContent += ` CET supply-chain screen: ${categories || "mapped"}; primary CET evidence: ${cets || "classified"}.`;
        }
      } else {
        screeningStatus.textContent = exposure;
      }
    } else {
      screeningBlock.hidden = true;
    }

    const relationships = (state.adjacency.get(nodeId) || [])
      .filter((edge) => {
        const source = state.nodesById.get(edge.source);
        return (
          (!nsfOnly.checked || Boolean(source?.nsf_sbir_awardee)) &&
          (!criticalOnly.checked || Boolean(source?.critical_supply_chain_review_candidate))
        );
      })
      .slice(0, 12);
    const fragment = document.createDocumentFragment();
    relationships.forEach((edge) => {
      const otherId = edge.source === nodeId ? edge.target : edge.source;
      const other = state.nodesById.get(otherId);
      if (!other) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "relationship-button";
      button.addEventListener("click", () => selectNode(otherId, { ensureVisible: true }));
      const name = document.createElement("span");
      name.className = "relationship-name";
      name.textContent = other.label;
      const meta = document.createElement("span");
      meta.className = "relationship-meta";
      meta.textContent = `${edge.fiscal_years} FY · ${formatMoney(edge.reported_subaward_amount)}`;
      button.append(name, meta);
      fragment.appendChild(button);
    });
    relationshipList.replaceChildren(fragment);
    focusButton.textContent = state.focusedNodeId === nodeId ? "Show overview" : "Focus neighborhood";
    render();
  }

  function findNode(query) {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return null;
    const candidates = [...state.nodesById.values()]
      .filter(
        (node) =>
          node.label.toLocaleLowerCase().includes(normalized) ||
          node.organization_id.toLocaleLowerCase().includes(normalized),
      )
      .sort((a, b) => {
        const aExact = a.label.toLocaleLowerCase() === normalized ? 1 : 0;
        const bExact = b.label.toLocaleLowerCase() === normalized ? 1 : 0;
        const aStarts = a.label.toLocaleLowerCase().startsWith(normalized) ? 1 : 0;
        const bStarts = b.label.toLocaleLowerCase().startsWith(normalized) ? 1 : 0;
        return bExact - aExact || bStarts - aStarts || (b.edge_count || 0) - (a.edge_count || 0);
      });
    return candidates[0] || null;
  }

  function resetExplorer() {
    state.focusedNodeId = null;
    state.selectedNodeId = null;
    state.hoveredNodeId = null;
    state.positions.clear();
    emptyDetail.hidden = false;
    selectedDetail.hidden = true;
    searchInput.value = "";
    rebuildVisibleGraph();
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
      state.pointer.moved ||= Math.hypot(point.x - state.pointer.startX, point.y - state.pointer.startY) > 3;
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
      tooltip.textContent = `${node.label} · ${node.kind === "prime" ? "Tier 1 prime" : "Tier 2 supplier"}`;
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
      showMessage(`No supplier or prime matched “${searchInput.value.trim()}”.`);
      return;
    }
    hideMessage();
    if (node.kind === "supplier" && !node.nsf_sbir_awardee) nsfOnly.checked = false;
    if (node.kind === "supplier" && !node.critical_supply_chain_review_candidate) {
      criticalOnly.checked = false;
    }
    state.focusedNodeId = node.id;
    rebuildVisibleGraph();
    selectNode(node.id);
  });

  minimumYears.addEventListener("change", () => rebuildVisibleGraph());
  graphDensity.addEventListener("change", () => rebuildVisibleGraph());
  nsfOnly.addEventListener("change", () => rebuildVisibleGraph());
  criticalOnly.addEventListener("change", () => rebuildVisibleGraph());
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
