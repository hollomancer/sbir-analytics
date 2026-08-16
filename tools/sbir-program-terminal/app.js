(() => {
  "use strict";

  const elements = {
    dataCut: document.getElementById("data-cut"),
    interpretation: document.getElementById("interpretation"),
    message: document.getElementById("terminal-message"),
    content: document.getElementById("terminal-content"),
    datasetLabel: document.getElementById("dataset-label"),
    metricGrid: document.getElementById("metric-grid"),
    metricTemplate: document.getElementById("metric-template"),
    firmCount: document.getElementById("firm-count"),
    firmList: document.getElementById("firm-list"),
    emptyDossier: document.getElementById("empty-dossier"),
    selectedDossier: document.getElementById("selected-dossier"),
    firmName: document.getElementById("firm-name"),
    firmMetrics: document.getElementById("firm-metrics"),
    eventFilter: document.getElementById("event-filter"),
    firmTimeline: document.getElementById("firm-timeline"),
    provenanceList: document.getElementById("provenance-list"),
    tierBadge: document.getElementById("tier-badge"),
    searchForm: document.getElementById("search-form"),
    searchInput: document.getElementById("global-search"),
    searchResults: document.getElementById("search-results"),
  };

  const state = {
    payload: null,
    selectedFirmId: null,
  };

  const numberFormatter = new Intl.NumberFormat("en-US");
  const moneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  });

  const eventLabels = {
    sbir_award: "SBIR award",
    form_d_filing: "Form D filing",
    ma_event: "M&A event",
    usaspending_contract: "Federal contract",
    patent_grant: "Patent grant",
    ucc_filing: "UCC filing",
  };

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatMoney(value) {
    return moneyFormatter.format(Number(value || 0));
  }

  function formatMetric(metric) {
    return metric.format === "currency"
      ? formatMoney(metric.value)
      : numberFormatter.format(metric.value);
  }

  function formatDate(value) {
    if (!value) return "Date unavailable";
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${String(value).slice(0, 10)}T00:00:00Z`));
  }

  function renderMetrics() {
    const cards = state.payload.metrics.map((metric) => {
      const card = elements.metricTemplate.content.firstElementChild.cloneNode(true);
      card.querySelector(".metric-label").textContent = metric.label;
      card.querySelector(".metric-status").textContent = metric.status;
      card.querySelector(".metric-value").textContent = formatMetric(metric);
      card.querySelector(".metric-change").textContent =
        metric.status === "lower bound" ? "Public-disclosure lower bound" : "Observed in snapshot";
      const source = card.querySelector(".source-button");
      source.textContent = `Source · ${metric.source}`;
      source.title = `Latest observed event ${state.payload.dataset.as_of || "undated"}`;
      return card;
    });
    elements.metricGrid.replaceChildren(...cards);
  }

  function firmButton(firm) {
    const button = createElement("button", "firm-index-button");
    button.type = "button";
    button.dataset.firmId = firm.id;
    button.setAttribute("aria-pressed", String(firm.id === state.selectedFirmId));
    button.append(
      createElement("strong", null, firm.name),
      createElement(
        "span",
        null,
        `${numberFormatter.format(firm.event_count)} observed events · ${
          firm.latest_activity ? formatDate(firm.latest_activity) : "no dated events"
        }`,
      ),
    );
    button.addEventListener("click", () => selectFirm(firm.id));
    return button;
  }

  function renderFirmList() {
    elements.firmCount.textContent = numberFormatter.format(state.payload.firms.length);
    elements.firmList.replaceChildren(
      ...state.payload.firms.map((firm) => firmButton(firm)),
    );
  }

  function profileMetric(label, value, status) {
    const metric = createElement("div", "profile-metric");
    metric.append(
      createElement("span", null, label),
      createElement("strong", null, value),
      createElement("small", null, status),
    );
    return metric;
  }

  function observedCount(value) {
    return Number(value || 0) === 0 ? "None observed" : numberFormatter.format(value);
  }

  function observedMoney(value) {
    return Number(value || 0) === 0 ? "None observed" : formatMoney(value);
  }

  function eventDescription(event) {
    const parts = [];
    if (event.subtype) parts.push(String(event.subtype).replaceAll("_", " "));
    if (event.amount !== null && event.amount !== undefined) {
      parts.push(formatMoney(event.amount));
    }
    if (event.counterparty) parts.push(String(event.counterparty));
    return parts.join(" · ") || "No additional structured detail";
  }

  function renderTimeline(firm) {
    const eventType = elements.eventFilter.value;
    const events = firm.events.filter(
      (event) => eventType === "all" || event.type === eventType,
    );
    if (!events.length) {
      elements.firmTimeline.replaceChildren(
        createElement("p", "empty-row", "No observed events match this filter."),
      );
      return;
    }
    const rows = events.map((event) => {
      const row = createElement("div", "profile-event");
      const time = createElement("time", null, formatDate(event.date));
      if (event.date) time.dateTime = String(event.date);
      const copy = createElement("div");
      copy.append(
        createElement("strong", null, eventLabels[event.type] || event.type),
        createElement("small", null, eventDescription(event)),
      );
      if (event.source_id) {
        copy.append(createElement("code", "source-id", `Source · ${event.source_id}`));
      }
      row.append(time, copy);
      return row;
    });
    elements.firmTimeline.replaceChildren(...rows);
  }

  function populateEventFilter(firm) {
    const current = elements.eventFilter.value;
    const types = [...new Set(firm.events.map((event) => event.type))].sort();
    const options = [createElement("option", null, "All observed events")];
    options[0].value = "all";
    types.forEach((type) => {
      const option = createElement("option", null, eventLabels[type] || type);
      option.value = type;
      options.push(option);
    });
    elements.eventFilter.replaceChildren(...options);
    elements.eventFilter.value = types.includes(current) ? current : "all";
  }

  function selectedFirm() {
    return state.payload?.firms.find((firm) => firm.id === state.selectedFirmId) || null;
  }

  function selectFirm(firmId) {
    const firm = state.payload.firms.find((candidate) => candidate.id === firmId);
    if (!firm) return;
    state.selectedFirmId = firmId;
    elements.emptyDossier.hidden = true;
    elements.selectedDossier.hidden = false;
    elements.firmName.textContent = firm.name;
    elements.firmMetrics.replaceChildren(
      profileMetric(
        "SBIR awards",
        observedCount(firm.sbir_award_count),
        firm.statuses.sbir_awards,
      ),
      profileMetric(
        "SBIR amount",
        observedMoney(firm.total_sbir_amount),
        firm.statuses.sbir_awards,
      ),
      profileMetric(
        "Disclosed capital",
        observedMoney(firm.total_form_d_raised),
        firm.statuses.private_capital,
      ),
      profileMetric(
        "Observed contracts",
        observedCount(firm.usaspending_contract_count),
        firm.statuses.contracts,
      ),
      profileMetric(
        "Patents",
        observedCount(firm.patent_count),
        firm.statuses.patents,
      ),
      profileMetric(
        "M&A records",
        observedCount(firm.ma_event_count),
        firm.statuses.ma_events,
      ),
    );
    populateEventFilter(firm);
    renderTimeline(firm);
    elements.firmList.querySelectorAll(".firm-index-button").forEach((button) => {
      const active = button.dataset.firmId === firmId;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function renderProvenance() {
    const dataset = state.payload.dataset;
    const rows = [
      ["Research question", dataset.research_question],
      ["Latest observed event", dataset.as_of || "No dated events"],
      ["Generated", dataset.generated_at],
      ["Evidence status", `${dataset.tier} · non-citable`],
      ...dataset.sources.map((source) => [
        source.role,
        `${source.path} · SHA-256 ${source.sha256}`,
      ]),
    ].map(([label, value]) => {
      const row = document.createElement("div");
      row.append(createElement("dt", null, label), createElement("dd", null, value));
      return row;
    });
    elements.provenanceList.replaceChildren(...rows);
  }

  function closeSearchResults() {
    elements.searchResults.hidden = true;
    elements.searchResults.replaceChildren();
  }

  function renderSearchResults() {
    const query = elements.searchInput.value.trim().toLocaleLowerCase();
    if (!query || !state.payload) {
      closeSearchResults();
      return;
    }
    const matches = state.payload.firms
      .filter((firm) =>
        [firm.name, ...firm.source_ids]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase().includes(query)),
      )
      .slice(0, 8);
    if (!matches.length) {
      const empty = createElement("div", "search-result");
      empty.append(
        createElement("span", "search-result-icon", "—"),
        createElement("span", null, "No firm or source record matched"),
      );
      elements.searchResults.replaceChildren(empty);
      elements.searchResults.hidden = false;
      return;
    }
    const results = matches.map((firm) => {
      const button = createElement("button", "search-result");
      button.type = "button";
      const copy = createElement("span");
      copy.append(
        createElement("strong", null, firm.name),
        createElement(
          "small",
          null,
          `${numberFormatter.format(firm.event_count)} observed events`,
        ),
      );
      button.append(
        createElement("span", "search-result-icon", "F"),
        copy,
        createElement("span", "search-result-type", "firm"),
      );
      button.addEventListener("click", () => {
        selectFirm(firm.id);
        elements.searchInput.value = firm.name;
        closeSearchResults();
        document.getElementById("dossiers").scrollIntoView({ behavior: "smooth" });
      });
      return button;
    });
    elements.searchResults.replaceChildren(...results);
    elements.searchResults.hidden = false;
  }

  function syncNavigation() {
    const hash = window.location.hash || "#overview";
    document.querySelectorAll(".nav-item").forEach((link) => {
      const active = link.getAttribute("href") === hash;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function bindEvents() {
    window.addEventListener("hashchange", syncNavigation);
    syncNavigation();
    elements.eventFilter.addEventListener("change", () => {
      const firm = selectedFirm();
      if (firm) renderTimeline(firm);
    });
    elements.searchInput.addEventListener("input", renderSearchResults);
    elements.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const first = elements.searchResults.querySelector("button");
      if (first) first.click();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && document.activeElement !== elements.searchInput) {
        event.preventDefault();
        elements.searchInput.focus();
      }
      if (event.key === "Escape") closeSearchResults();
    });
    document.addEventListener("click", (event) => {
      if (!elements.searchForm.contains(event.target)) closeSearchResults();
    });
  }

  function showUnavailable(error) {
    elements.dataCut.textContent = "UNAVAILABLE";
    const title = createElement("h2", null, "No local snapshot is available");
    const explanation = createElement(
      "p",
      null,
      "The terminal fails closed and displays no metrics until canonical capital-event artifacts are exported.",
    );
    const command = createElement(
      "code",
      "materialization-command",
      "uv run python scripts/data/build_capital_events.py\nuv run python scripts/data/export_sbir_program_terminal.py",
    );
    const detail = createElement(
      "p",
      "load-detail",
      `Load detail: ${error instanceof Error ? error.message : "unknown error"}`,
    );
    elements.message.replaceChildren(
      createElement("p", "eyebrow", "Local snapshot required"),
      title,
      explanation,
      command,
      detail,
    );
    elements.message.hidden = false;
    elements.content.hidden = true;
  }

  function render() {
    const dataset = state.payload.dataset;
    elements.dataCut.textContent = dataset.as_of || "UNDATED";
    elements.interpretation.textContent = dataset.interpretation;
    elements.datasetLabel.textContent = dataset.label;
    elements.tierBadge.textContent = dataset.tier;
    renderMetrics();
    renderFirmList();
    renderProvenance();
    elements.message.hidden = true;
    elements.content.hidden = false;
  }

  async function loadTerminal() {
    bindEvents();
    try {
      const response = await fetch("data/terminal.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`data/terminal.json returned HTTP ${response.status}`);
      const payload = await response.json();
      if (
        payload.dataset?.tier !== "exploratory" ||
        payload.dataset?.citable !== false ||
        !Array.isArray(payload.metrics) ||
        !Array.isArray(payload.firms)
      ) {
        throw new Error("snapshot contract is invalid or does not declare its evidence boundary");
      }
      state.payload = payload;
      render();
    } catch (error) {
      showUnavailable(error);
      console.info("SBIR terminal snapshot unavailable", error);
    }
  }

  loadTerminal();
})();
