(() => {
  "use strict";

  const ROUTE_SUBTITLES = {
    today: "Next best move",
    opportunities: "High-conviction roles",
    applications: "Active hiring pipeline",
    interviews: "Role-specific preparation",
    network: "Verified access paths",
    assets: "Résumé and evidence",
    profile: "Candidate constraints",
  };

  const MORE_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>`;
  const CHEVRON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>`;
  const SYSTEM_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0"/><path d="M12 8v4l2.5 1.5"/></svg>`;

  let scheduled = false;

  function currentRoute() {
    const hash = window.location.hash.replace(/^#/, "");
    return ROUTE_SUBTITLES[hash] ? hash : "today";
  }

  function setRouteMetadata() {
    const route = currentRoute();
    document.body.dataset.route = route;
    const subtitle = document.querySelector("#route-subtitle");
    if (subtitle) subtitle.textContent = ROUTE_SUBTITLES[route];
    document.querySelectorAll("[data-route]").forEach((control) => {
      const active = control.dataset.route === route;
      if (active) control.setAttribute("aria-current", "page");
      else control.removeAttribute("aria-current");
    });
  }

  function organizeSidebar() {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav) return;
    let disclosure = nav.querySelector(".nav-more");
    if (!disclosure) {
      const secondary = [...nav.querySelectorAll(":scope > button[data-route]")]
        .filter((button) => ["network", "assets"].includes(button.dataset.route));
      if (!secondary.length) return;
      disclosure = document.createElement("details");
      disclosure.className = "nav-more";
      const summary = document.createElement("summary");
      summary.innerHTML = `<span class="nav-icon">${MORE_ICON}</span><span><strong>More</strong><small>Network and assets</small></span><span class="nav-more-chevron">${CHEVRON}</span>`;
      const body = document.createElement("div");
      body.className = "nav-more-body";
      secondary.forEach((button) => body.appendChild(button));
      disclosure.append(summary, body);
      nav.appendChild(disclosure);
    }
    const hasActive = Boolean(disclosure.querySelector("button.active"));
    disclosure.classList.toggle("has-active", hasActive);
    if (hasActive) disclosure.open = true;
  }

  function refineToday() {
    const layout = document.querySelector(".today-layout");
    if (!layout || layout.dataset.uxRefined === "true") return;
    layout.dataset.uxRefined = "true";

    const sections = [...layout.querySelectorAll(".today-main > .workspace-section")];
    const actionSection = sections.find((section) => section.querySelector("h2")?.textContent.trim() === "Action queue");
    if (actionSection) {
      actionSection.classList.add("next-actions-panel");
      const heading = actionSection.querySelector("h2");
      const copy = actionSection.querySelector(".section-heading p");
      if (heading) heading.textContent = "Next actions";
      if (copy) copy.textContent = "Only what follows today’s priority.";
      const rows = [...actionSection.querySelectorAll(".action-row")];
      if (rows.length) rows[0].remove();
      const remaining = [...actionSection.querySelectorAll(".action-row")];
      remaining.slice(2).forEach((row) => row.remove());
      if (!remaining.length) actionSection.hidden = true;
      const counter = actionSection.querySelector(".section-heading .status-badge");
      if (counter) counter.textContent = `${remaining.length} next`;
    }

    const progressSection = sections.find((section) => section.querySelector("h2")?.textContent.trim() === "Hiring progress");
    progressSection?.classList.add("progress-panel");

    const railPanels = [...layout.querySelectorAll(".today-rail > .rail-panel")];
    const blockerPanel = railPanels.find((panel) => panel.querySelector("h2")?.textContent.trim() === "Blockers");
    if (blockerPanel?.querySelector(".inline-empty")) blockerPanel.hidden = true;

    const systemPanel = railPanels.find((panel) => panel.classList.contains("system-panel"));
    if (systemPanel && !systemPanel.closest(".system-disclosure")) {
      const disclosure = document.createElement("details");
      disclosure.className = "system-disclosure";
      const summary = document.createElement("summary");
      summary.innerHTML = `<span>${SYSTEM_ICON}<strong>System status</strong></span><small>Discovery and source health</small><span class="system-chevron">${CHEVRON}</span>`;
      systemPanel.replaceWith(disclosure);
      systemPanel.classList.remove("rail-panel");
      disclosure.append(summary, systemPanel);
    }
  }

  function refineDataLists() {
    document.querySelectorAll(".table-shell").forEach((shell) => {
      if (shell.querySelector(".opportunity-table")) shell.classList.add("ux-card-list", "ux-opportunity-list");
      if (shell.querySelector(".application-table")) shell.classList.add("ux-card-list", "ux-application-list");
    });
  }

  function refineDetailTabs() {
    const tabs = document.querySelector(".detail-tabs");
    if (!tabs || tabs.dataset.uxRefined === "true") return;
    const controls = [...tabs.querySelectorAll(":scope > .detail-tab")];
    if (controls.length < 5) return;
    tabs.dataset.uxRefined = "true";

    const primaryNames = new Set(["overview", "application", "preparation", "evidence"]);
    const primary = document.createElement("div");
    primary.className = "detail-tab-primary";
    const more = document.createElement("details");
    more.className = "detail-tab-more";
    const summary = document.createElement("summary");
    summary.innerHTML = `More ${CHEVRON}`;
    const body = document.createElement("div");
    body.className = "detail-tab-more-body";

    controls.forEach((control) => {
      if (primaryNames.has(control.dataset.detailTab)) primary.appendChild(control);
      else body.appendChild(control);
    });
    more.append(summary, body);
    tabs.append(primary, more);
  }

  function syncDetailMoreState() {
    const more = document.querySelector(".detail-tab-more");
    if (!more) return;
    const hasActive = Boolean(more.querySelector(".detail-tab.active"));
    more.classList.toggle("has-active", hasActive);
    if (hasActive) more.open = true;
  }

  function refineView() {
    scheduled = false;
    document.body.classList.add("ux-live10");
    setRouteMetadata();
    organizeSidebar();
    refineToday();
    refineDataLists();
    refineDetailTabs();
    syncDetailMoreState();
  }

  function scheduleRefine() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(refineView);
  }

  const observer = new MutationObserver(scheduleRefine);
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "hidden"] });
  window.addEventListener("hashchange", scheduleRefine);
  window.addEventListener("DOMContentLoaded", scheduleRefine, { once: true });
  scheduleRefine();
})();
