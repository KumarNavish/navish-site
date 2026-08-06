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
  new MutationObserver(enhance).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("DOMContentLoaded", enhance);
})();
