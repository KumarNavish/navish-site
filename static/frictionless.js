(() => {
  "use strict";

  const ROUTE_COPY = {
    today: ["Today", "One clear next move"],
    opportunities: ["Roles", "High-conviction only"],
    applications: ["Applications", "Packages and progress"],
    interviews: ["Prepare", "Role-specific sessions"],
    profile: ["Profile", "Evidence and constraints"],
  };

  let scheduled = false;

  function text(node, value) {
    if (node && node.textContent !== value) node.textContent = value;
  }

  function simplifyNavigation() {
    document.querySelectorAll('[data-route="network"], [data-route="assets"]').forEach((node) => node.classList.add("frictionless-hide"));

    const labels = {
      opportunities: ["Roles", "High-conviction only"],
      applications: ["Applications", "Packages and progress"],
      interviews: ["Prepare", "Role-specific"],
    };
    Object.entries(labels).forEach(([route, [title, subtitle]]) => {
      document.querySelectorAll(`[data-route="${route}"]`).forEach((button) => {
        if (button.closest(".mobile-nav")) text(button.querySelector(":scope > span"), title);
        text(button.querySelector("strong"), title);
        text(button.querySelector("small"), subtitle);
      });
    });

    const more = document.querySelector("#mobile-more");
    if (more && !more.dataset.frictionless) {
      const profile = more.cloneNode(true);
      profile.removeAttribute("id");
      profile.dataset.route = "profile";
      profile.dataset.frictionless = "true";
      profile.setAttribute("aria-label", "Profile");
      profile.innerHTML = "<span>Profile</span>";
      profile.addEventListener("click", (event) => {
        event.preventDefault();
        document.querySelector('.sidebar [data-route="profile"]')?.click();
      });
      more.replaceWith(profile);
    }
    document.querySelector("#mobile-panel")?.classList.add("frictionless-hide");
  }

  function simplifyToday(view) {
    const layout = view.querySelector(".today-layout");
    if (!layout) return;
    layout.classList.add("frictionless-today");

    view.querySelectorAll(".workspace-section").forEach((section) => {
      const heading = section.querySelector(".section-heading h2")?.textContent?.trim();
      if (heading === "Hiring progress") section.classList.add("frictionless-hide");
      if (heading === "Action queue") {
        text(section.querySelector(".section-heading h2"), "Next");
        text(section.querySelector(".section-heading p"), "Only remaining high-impact actions.");
        const remaining = Math.max(0, section.querySelectorAll(".action-row").length - 1);
        const count = section.querySelector(".section-heading .status-badge");
        if (count) text(count, `${remaining} remaining`);
      }
    });

    view.querySelectorAll(".today-rail .rail-panel").forEach((panel) => {
      const heading = panel.querySelector(".section-heading h2")?.textContent?.trim();
      if (heading === "System") panel.classList.add("frictionless-hide");
      if (heading === "Blockers" && panel.querySelector(".inline-empty")) panel.classList.add("frictionless-hide");
      if (heading === "Upcoming") {
        text(panel.querySelector(".section-heading p"), "Only deadlines and interviews");
        if (panel.querySelector(".inline-empty")) panel.classList.add("frictionless-hide");
      }
    });
  }

  function simplifyRouteCopy() {
    const route = location.hash.slice(1) || "today";
    const copy = ROUTE_COPY[route];
    if (!copy) return;
    text(document.querySelector("#route-title"), copy[0]);
    text(document.querySelector("#route-subtitle"), copy[1]);
    const header = document.querySelector("#view .page-header");
    if (!header) return;
    if (route === "opportunities") {
      text(header.querySelector("h1"), "Recommended roles");
      text(header.querySelector("p"), "Only roles with a credible interview case, an explicit blocker and one primary path.");
    } else if (route === "applications") {
      text(header.querySelector("h1"), "Applications");
      text(header.querySelector("p"), "Review truthful packages, next actions and stage changes without administrative clutter.");
    } else if (route === "interviews") {
      text(header.querySelector("h1"), "Preparation");
      text(header.querySelector("p"), "Short sessions tied to the most probable rejection point in an active role.");
    }
  }

  function enhance() {
    scheduled = false;
    document.documentElement.dataset.ux = "frictionless";
    simplifyNavigation();
    simplifyRouteCopy();
    simplifyToday(document.querySelector("#view"));
    document.querySelector("#zero-cost-continuity")?.classList.add("frictionless-hide");
  }

  function requestEnhance() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(enhance);
  }

  new MutationObserver(requestEnhance).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("hashchange", requestEnhance);
  document.addEventListener("DOMContentLoaded", requestEnhance);
  requestEnhance();
})();
