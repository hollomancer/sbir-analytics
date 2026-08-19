(() => {
  "use strict";

  const elements = {
    dataCut: document.getElementById("data-cut"),
    metricGrid: document.getElementById("metric-grid"),
    metricTemplate: document.getElementById("metric-template"),
    technologyChart: document.getElementById("technology-chart"),
    technologyLens: document.getElementById("technology-lens"),
    signalList: document.getElementById("signal-list"),
    signalCount: document.getElementById("signal-count"),
    agencyFilter: document.getElementById("agency-filter"),
    technologyFilter: document.getElementById("technology-filter"),
    firmRows: document.getElementById("firm-rows"),
    activityList: document.getElementById("activity-list"),
    provenanceList: document.getElementById("provenance-list"),
    searchForm: document.getElementById("search-form"),
    searchInput: document.getElementById("global-search"),
    searchResults: document.getElementById("search-results"),
    firmDialog: document.getElementById("firm-dialog"),
    firmProfile: document.getElementById("firm-profile"),
    closeDialog: document.getElementById("close-dialog"),
  };

  const state = {
    payload: null,
    period: "5y",
  };

  const moneyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  });

  const numberFormatter = new Intl.NumberFormat("en-US");

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function formatMoney(value) {
    return moneyFormatter.format(Number(value || 0));
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(`${value}T00:00:00Z`));
  }

  function renderMetrics() {
    const cards = state.payload.metrics.map((metric) => {
      const card = elements.metricTemplate.content.firstElementChild.cloneNode(true);
      card.querySelector(".metric-label").textContent = metric.label;
      card.querySelector(".metric-status").textContent = metric.status;
      card.querySelector(".metric-value").textContent = metric.values[state.period];
      const change = card.querySelector(".metric-change");
      change.textContent = metric.changes[state.period];
      if (String(metric.changes[state.period]).startsWith("+")) change.classList.add("positive");
      const sparkline = card.querySelector(".sparkline");
      const maximum = Math.max(...metric.trend);
      metric.trend.forEach((value) => {
        const bar = document.createElement("i");
        bar.style.height = `${Math.max(10, (value / maximum) * 100)}%`;
        sparkline.appendChild(bar);
      });
      const source = card.querySelector(".source-button");
      source.textContent = `Source · ${metric.source}`;
      source.title = `As of ${state.payload.dataset.as_of}; ${metric.status}`;
      return card;
    });
    elements.metricGrid.replaceChildren(...cards);
  }

  function technologyValue(technology, lens) {
    if (lens === "obligations") return formatMoney(technology[lens]);
    if (lens === "transition_rate") return `${technology[lens].toFixed(1)}%`;
    return numberFormatter.format(technology[lens]);
  }

  function renderTechnologies() {
    const lens = elements.technologyLens.value;
    const technologies = state.payload.technologies
      .slice()
      .sort((left, right) => right[lens] - left[lens]);
    const maximum = Math.max(...technologies.map((technology) => technology[lens]));
    const rows = technologies.map((technology, index) => {
      const row = createElement("div", "technology-row");
      const label = createElement("div", "technology-label");
      label.append(
        createElement("strong", null, technology.label),
        createElement("small", null, `Rank ${index + 1} · synthetic portfolio`),
      );
      const track = createElement("div", "technology-track");
      const bar = createElement("div", "technology-bar");
      bar.style.width = `${(technology[lens] / maximum) * 100}%`;
      track.appendChild(bar);
      row.append(
        label,
        track,
        createElement("span", "technology-value", technologyValue(technology, lens)),
      );
      return row;
    });
    elements.technologyChart.replaceChildren(...rows);
  }

  function renderSignals() {
    elements.signalCount.textContent = state.payload.signals.length;
    const signals = state.payload.signals.map((signal) => {
      const row = createElement("div", `signal ${signal.severity}`);
      row.appendChild(createElement("span", "signal-icon", signal.severity === "high" ? "!" : "i"));
      const copy = createElement("div");
      copy.append(
        createElement("strong", null, signal.title),
        createElement("small", null, signal.detail),
      );
      row.appendChild(copy);
      return row;
    });
    elements.signalList.replaceChildren(...signals);
  }

  function appendOptions(select, values) {
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  function populateFilters() {
    const agencies = [...new Set(state.payload.firms.map((firm) => firm.agency))].sort();
    const technologies = [...new Set(state.payload.firms.map((firm) => firm.technology))].sort();
    appendOptions(elements.agencyFilter, agencies);
    appendOptions(elements.technologyFilter, technologies);
  }

  function transitionLabel(firm) {
    return firm.transition === "observed" ? "Observed" : "Not observed";
  }

  function filteredFirms() {
    return state.payload.firms.filter(
      (firm) =>
        (elements.agencyFilter.value === "all" ||
          firm.agency === elements.agencyFilter.value) &&
        (elements.technologyFilter.value === "all" ||
          firm.technology === elements.technologyFilter.value),
    );
  }

  function renderFirms() {
    const firms = filteredFirms();
    if (!firms.length) {
      const row = document.createElement("tr");
      const cell = createElement("td", "empty-row", "No synthetic firms match these filters.");
      cell.colSpan = 7;
      row.appendChild(cell);
      elements.firmRows.replaceChildren(row);
      return;
    }

    const rows = firms
      .slice()
      .sort((left, right) => right.obligations - left.obligations)
      .map((firm) => {
        const row = document.createElement("tr");
        row.tabIndex = 0;
        row.setAttribute("aria-label", `Open profile for ${firm.name}`);
        const firmCell = createElement("td", "firm-cell");
        firmCell.append(
          createElement("strong", null, firm.name),
          createElement("small", null, `${firm.uei} · ${firm.location}`),
        );
        const transitionCell = document.createElement("td");
        transitionCell.appendChild(
          createElement(
            "span",
            `transition-tag ${firm.transition === "observed" ? "" : "unobserved"}`,
            transitionLabel(firm),
          ),
        );
        [
          firmCell,
          createElement("td", null, firm.agency_short),
          createElement("td", null, firm.technology),
          createElement("td", null, numberFormatter.format(firm.awards)),
          createElement("td", null, formatMoney(firm.obligations)),
          transitionCell,
          createElement("td", null, formatDate(firm.latest_activity)),
        ].forEach((cell) => row.appendChild(cell));
        row.addEventListener("click", () => openFirm(firm.id));
        row.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openFirm(firm.id);
          }
        });
        return row;
      });
    elements.firmRows.replaceChildren(...rows);
  }

  function renderActivity() {
    const activity = state.payload.activity.map((event) => {
      const row = createElement("div", "activity");
      const time = createElement("time", null, formatDate(event.date));
      time.dateTime = event.date;
      const copy = createElement("p");
      copy.append(
        createElement("strong", null, event.title),
        document.createTextNode(event.detail),
      );
      row.append(time, createElement("span", "activity-dot"), copy);
      return row;
    });
    elements.activityList.replaceChildren(...activity);
  }

  function renderProvenance() {
    const rows = Object.entries(state.payload.provenance).map(([label, value]) => {
      const row = document.createElement("div");
      row.append(createElement("dt", null, label), createElement("dd", null, value));
      return row;
    });
    elements.provenanceList.replaceChildren(...rows);
  }

  function profileMetric(label, value) {
    const metric = createElement("div", "profile-metric");
    metric.append(createElement("span", null, label), createElement("strong", null, value));
    return metric;
  }

  function openFirm(firmId) {
    const firm = state.payload.firms.find((candidate) => candidate.id === firmId);
    if (!firm) return;

    const header = createElement("header", "profile-header");
    header.append(
      createElement("p", "eyebrow", "Synthetic organization profile"),
      createElement("h2", null, firm.name),
      createElement("p", null, `${firm.uei} · ${firm.location} · ${firm.agency}`),
    );

    const body = createElement("div", "profile-body");
    const metrics = createElement("div", "profile-metrics");
    metrics.append(
      profileMetric("SBIR awards", numberFormatter.format(firm.awards)),
      profileMetric("Obligations", formatMoney(firm.obligations)),
      profileMetric("Transition", transitionLabel(firm)),
    );
    body.append(metrics, createElement("p", null, firm.description));

    const technology = createElement("section", "profile-section");
    technology.append(
      createElement("h3", null, "Portfolio classification"),
      createElement("p", null, `${firm.technology} · primary agency ${firm.agency_short}`),
    );

    const timeline = createElement("section", "profile-section");
    timeline.appendChild(createElement("h3", null, "Observed event timeline"));
    const timelineRows = createElement("div", "profile-timeline");
    firm.events.forEach((event) => {
      const row = createElement("div", "profile-event");
      const time = createElement("time", null, formatDate(event.date));
      time.dateTime = event.date;
      const copy = createElement("div");
      copy.append(
        createElement("strong", null, event.title),
        createElement("small", null, event.detail),
      );
      row.append(time, copy);
      timelineRows.appendChild(row);
    });
    timeline.appendChild(timelineRows);

    const evidence = createElement("section", "profile-section");
    evidence.append(
      createElement("h3", null, "Evidence boundary"),
      createElement(
        "div",
        "evidence-note",
        "This profile contains invented demonstration records. In production, each event must link to a source record and carry match confidence, data cut, and permitted interpretation.",
      ),
    );

    body.append(technology, timeline, evidence);
    elements.firmProfile.replaceChildren(header, body);
    elements.firmDialog.showModal();
  }

  function searchIndex() {
    const firms = state.payload.firms.map((firm) => ({
      id: firm.id,
      type: "organization",
      label: firm.name,
      meta: `${firm.uei} · ${firm.technology}`,
      searchable: [firm.name, firm.uei, firm.agency, firm.technology, firm.location].join(" "),
      firmId: firm.id,
    }));
    const awards = state.payload.awards.map((award) => ({
      id: award.id,
      type: "award",
      label: award.title,
      meta: `${award.award_id} · ${award.agency}`,
      searchable: [award.title, award.award_id, award.agency, award.technology].join(" "),
      firmId: award.firm_id,
    }));
    const technologies = state.payload.technologies.map((technology) => ({
      id: technology.id,
      type: "technology",
      label: technology.label,
      meta: `${numberFormatter.format(technology.organizations)} synthetic organizations`,
      searchable: technology.label,
      technology: technology.label,
    }));
    return [...firms, ...awards, ...technologies];
  }

  function closeSearchResults() {
    elements.searchResults.hidden = true;
    elements.searchResults.replaceChildren();
  }

  function chooseSearchResult(result) {
    closeSearchResults();
    elements.searchInput.value = result.label;
    if (result.firmId) {
      openFirm(result.firmId);
      return;
    }
    if (result.technology) {
      elements.technologyFilter.value = result.technology;
      renderFirms();
      document.getElementById("organizations").scrollIntoView({ behavior: "smooth" });
    }
  }

  function renderSearchResults() {
    const query = elements.searchInput.value.trim().toLocaleLowerCase();
    if (!query) {
      closeSearchResults();
      return;
    }
    const results = searchIndex()
      .filter((entry) => entry.searchable.toLocaleLowerCase().includes(query))
      .slice(0, 6);
    if (!results.length) {
      const empty = createElement("div", "search-result");
      empty.append(
        createElement("span", "search-result-icon", "—"),
        createElement("span", null, "No synthetic records matched"),
      );
      elements.searchResults.replaceChildren(empty);
      elements.searchResults.hidden = false;
      return;
    }
    const buttons = results.map((result) => {
      const button = createElement("button", "search-result");
      button.type = "button";
      const copy = createElement("span");
      copy.append(
        createElement("strong", null, result.label),
        createElement("small", null, result.meta),
      );
      button.append(
        createElement("span", "search-result-icon", result.type.charAt(0).toUpperCase()),
        copy,
        createElement("span", "search-result-type", result.type),
      );
      button.addEventListener("click", () => chooseSearchResult(result));
      return button;
    });
    elements.searchResults.replaceChildren(...buttons);
    elements.searchResults.hidden = false;
  }

  function bindEvents() {
    document.querySelectorAll(".nav-item").forEach((link) => {
      link.addEventListener("click", () => {
        document.querySelectorAll(".nav-item").forEach((candidate) => {
          const active = candidate === link;
          candidate.classList.toggle("active", active);
          if (active) candidate.setAttribute("aria-current", "page");
          else candidate.removeAttribute("aria-current");
        });
      });
    });
    document.querySelectorAll("[data-period]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-period]").forEach((candidate) => {
          candidate.classList.toggle("active", candidate === button);
        });
        state.period = button.dataset.period;
        renderMetrics();
      });
    });
    elements.technologyLens.addEventListener("change", renderTechnologies);
    elements.agencyFilter.addEventListener("change", renderFirms);
    elements.technologyFilter.addEventListener("change", renderFirms);
    elements.searchInput.addEventListener("input", renderSearchResults);
    elements.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const first = elements.searchResults.querySelector("button");
      if (first) first.click();
    });
    elements.closeDialog.addEventListener("click", () => elements.firmDialog.close());
    elements.firmDialog.addEventListener("click", (event) => {
      if (event.target === elements.firmDialog) elements.firmDialog.close();
    });
    document.addEventListener("keydown", (event) => {
      if (
        event.key === "/" &&
        document.activeElement !== elements.searchInput &&
        !elements.firmDialog.open
      ) {
        event.preventDefault();
        elements.searchInput.focus();
      }
      if (event.key === "Escape") closeSearchResults();
    });
    document.addEventListener("click", (event) => {
      if (!elements.searchForm.contains(event.target)) closeSearchResults();
    });
  }

  function render() {
    elements.dataCut.textContent = state.payload.dataset.as_of;
    renderMetrics();
    renderTechnologies();
    renderSignals();
    populateFilters();
    renderFirms();
    renderActivity();
    renderProvenance();
  }

  async function loadTerminal() {
    try {
      const response = await fetch("data/demo.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (
        !payload.dataset ||
        !Array.isArray(payload.metrics) ||
        !Array.isArray(payload.firms)
      ) {
        throw new Error("Invalid terminal payload");
      }
      if (payload.dataset.citable !== false || payload.dataset.tier !== "exploratory") {
        throw new Error("Demo payload must remain explicitly exploratory and non-citable");
      }
      state.payload = payload;
      render();
      bindEvents();
    } catch (error) {
      elements.dataCut.textContent = "UNAVAILABLE";
      const failure = createElement(
        "p",
        "empty-row",
        "Demo data unavailable. Run this directory through a local HTTP server.",
      );
      elements.metricGrid.replaceChildren(failure);
      console.error("Unable to load SBIR terminal prototype", error);
    }
  }

  loadTerminal();
})();
