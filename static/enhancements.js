(() => {
  "use strict";

  function enhance() {
    document.querySelectorAll("select.stage-select:not([aria-label])").forEach((control) => {
      const row = control.closest("tr,article");
      const role = row?.querySelector(".role-cell strong")?.textContent?.trim() || "application";
      control.setAttribute("aria-label", `Stage for ${role}`);
    });
    document.querySelectorAll("[data-open-role][tabindex='0']:not([role])").forEach((row) => row.setAttribute("role", "button"));
  }

  document.addEventListener("click", (event) => {
    const more = event.target.closest("#mobile-more");
    if (more) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const panel = document.querySelector("#mobile-panel");
      panel?.setAttribute("data-open", panel.getAttribute("data-open") === "true" ? "false" : "true");
      return;
    }
    const menu = event.target.closest("#menu-toggle");
    if (menu) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const sidebar = document.querySelector("#sidebar");
      const scrim = document.querySelector("#sidebar-scrim");
      sidebar?.classList.toggle("open");
      if (scrim) scrim.hidden = !sidebar?.classList.contains("open");
      return;
    }
    if (event.target.closest("#sidebar-scrim")) {
      event.preventDefault();
      event.stopImmediatePropagation();
      document.querySelector("#sidebar")?.classList.remove("open");
      const scrim = document.querySelector("#sidebar-scrim");
      if (scrim) scrim.hidden = true;
    }
  }, true);

  new MutationObserver(enhance).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", enhance);
})();
