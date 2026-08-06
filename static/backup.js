(() => {
  "use strict";

  const LOCAL_KEY = "scios_structured_backup_v1";
  const LAST_KEY = "scios_structured_backup_time_v1";
  const DAY = 24 * 60 * 60 * 1000;
  let snapshotInFlight = false;
  let cachedCost = null;

  function notify(message) {
    const toast = document.querySelector("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 3600);
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(payload?.detail || `${url} failed (${response.status})`);
    return payload;
  }

  function fetchBackup() {
    return fetchJson("/api/backup/export");
  }

  async function fetchCost() {
    try {
      cachedCost = await fetchJson("/ops/cost");
      return cachedCost;
    } catch (_) {
      return cachedCost;
    }
  }

  function parseLocalBackup() {
    try {
      const stored = localStorage.getItem(LOCAL_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch (_) {
      return null;
    }
  }

  function payloadWeight(payload) {
    if (!payload || typeof payload !== "object") return 0;
    const profile = payload.profile || {};
    return (
      (Array.isArray(profile.evidence) ? profile.evidence.length : 0)
      + (Array.isArray(payload.jobs) ? payload.jobs.length * 4 : 0)
      + (Array.isArray(payload.applications) ? payload.applications.length * 3 : 0)
      + (Array.isArray(payload.practice) ? payload.practice.length : 0)
      + (Array.isArray(payload.actions) ? payload.actions.length : 0)
      + (profile.active ? 2 : 0)
    );
  }

  function saveLocally(payload) {
    const text = JSON.stringify(payload);
    localStorage.setItem(LOCAL_KEY, text);
    localStorage.setItem(LAST_KEY, new Date().toISOString());
    return text;
  }

  function download(text) {
    const stamp = new Date().toISOString().slice(0, 10);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `swiss-career-intelligence-backup-${stamp}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function createBackup(downloadFile = true) {
    const payload = await fetchBackup();
    const text = saveLocally(payload);
    if (downloadFile) download(text);
    notify(downloadFile ? "Private structured backup downloaded" : "Private browser backup refreshed");
    await updateBadge();
  }

  async function restorePayload(payload, { automatic = false } = {}) {
    const result = await fetchJson("/api/backup/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (result.external_actions_executed !== false || result.cost_chf !== 0) {
      throw new Error("Restore safety boundary was not confirmed");
    }
    saveLocally(payload);
    notify(
      automatic
        ? "Free database continuity restored automatically; no external action was performed"
        : "Structured hiring state restored; no external action was performed",
    );
    window.setTimeout(() => location.reload(), 1000);
  }

  function expiryText(cost) {
    const value = cost?.database_free_tier_expires_at;
    if (!value) return "";
    const parsed = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(parsed.getTime())) return "";
    const days = Math.ceil((parsed.getTime() - Date.now()) / DAY);
    if (days < 0) return "Free database period ended; continuity mode is active.";
    if (days <= 7) return `Free database changes in ${days} day${days === 1 ? "" : "s"}; keep the portable backup.`;
    return `Current free database expires ${parsed.toLocaleDateString("en-CH")}.`;
  }

  async function openDialog() {
    const dialog = document.querySelector("#dialog");
    const body = document.querySelector("#dialog-body");
    if (!dialog || !body) return;
    const last = localStorage.getItem(LAST_KEY);
    const cost = await fetchCost();
    const databaseNote = expiryText(cost);
    body.innerHTML = `<div class="dialog-card">
      <h2>Free continuity backup</h2>
      <p>This preserves structured profile evidence, verified roles, application state, preparation and Today actions. Raw CV files, passwords, sessions and private access tokens are excluded.</p>
      <div class="notice info"><strong>CHF 0 protection</strong><p>No paid model or hosting upgrade is allowed. The same-device browser copy is refreshed automatically, a portable JSON file gives you an independent restore path, and an empty fallback database is recovered automatically when possible.</p></div>
      ${databaseNote ? `<div class="notice warning"><strong>Free-tier continuity</strong><p>${databaseNote}</p></div>` : ""}
      <p class="meta">Database mode: ${cost?.database_plan || "Free mode"}</p>
      <p class="meta">Last browser copy: ${last ? new Date(last).toLocaleString("en-CH") : "Not created yet"}</p>
      <div class="actions">
        <button class="primary" id="backup-download">Download current backup</button>
        <button class="secondary" id="backup-restore-browser" ${parseLocalBackup() ? "" : "disabled"}>Restore browser copy</button>
        <label class="secondary" style="display:inline-flex;align-items:center;cursor:pointer">Restore JSON file<input id="backup-file" type="file" accept="application/json,.json" hidden></label>
        <button class="secondary" id="backup-close">Close</button>
      </div>
    </div>`;
    dialog.showModal();
    document.querySelector("#backup-close").onclick = () => dialog.close();
    document.querySelector("#backup-download").onclick = async () => {
      try { await createBackup(true); } catch (error) { notify(error.message || "Backup failed"); }
    };
    const browserButton = document.querySelector("#backup-restore-browser");
    if (browserButton) browserButton.onclick = async () => {
      try {
        const stored = parseLocalBackup();
        if (!stored) throw new Error("No browser backup is available");
        await restorePayload(stored);
      } catch (error) { notify(error.message || "Restore failed"); }
    };
    document.querySelector("#backup-file").onchange = async (event) => {
      try {
        const file = event.target.files?.[0];
        if (!file) return;
        if (file.size > 8 * 1024 * 1024) throw new Error("Backup exceeds 8 MB");
        await restorePayload(JSON.parse(await file.text()));
      } catch (error) { notify(error.message || "Restore failed"); }
    };
  }

  async function updateBadge() {
    const badge = document.querySelector("#zero-cost-continuity");
    if (!badge) return;
    const cost = await fetchCost();
    const last = localStorage.getItem(LAST_KEY);
    const fallback = cost?.database_fallback_active ? " · continuity mode" : "";
    badge.textContent = last ? `CHF 0 · backup protected${fallback}` : `CHF 0 · create backup${fallback}`;
    badge.title = expiryText(cost) || "No paid service or API is enabled";
  }

  function installControls() {
    const topbar = document.querySelector(".topbar");
    if (!topbar || document.querySelector("#zero-cost-continuity")) return;
    const button = document.createElement("button");
    button.id = "zero-cost-continuity";
    button.className = "quiet";
    button.type = "button";
    button.onclick = openDialog;
    topbar.appendChild(button);
    updateBadge();
  }

  async function reconcileContinuity() {
    if (snapshotInFlight) return;
    snapshotInFlight = true;
    try {
      const [remote, cost] = await Promise.all([fetchBackup(), fetchCost()]);
      const local = parseLocalBackup();
      const remoteWeight = payloadWeight(remote);
      const localWeight = payloadWeight(local);
      const remoteEmpty = remoteWeight <= 2 && (remote.jobs || []).length === 0 && (remote.applications || []).length === 0;
      const shouldRecover = local && localWeight >= 5 && localWeight > remoteWeight && (remoteEmpty || cost?.database_fallback_active);
      if (shouldRecover) {
        await restorePayload(local, { automatic: true });
        return;
      }
      const last = Date.parse(localStorage.getItem(LAST_KEY) || "0");
      if (!local || Date.now() - last >= DAY || remoteWeight > localWeight) {
        saveLocally(remote);
        await updateBadge();
      }
    } catch (_) {
      // The next authenticated load retries. Existing local state is retained.
    } finally {
      snapshotInFlight = false;
    }
  }

  const observer = new MutationObserver(() => {
    const app = document.querySelector("#app");
    if (!app || app.hidden) return;
    installControls();
    reconcileContinuity();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  window.addEventListener("load", () => {
    installControls();
    reconcileContinuity();
  });
})();
