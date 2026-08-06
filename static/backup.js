(() => {
  "use strict";

  const LOCAL_KEY = "scios_structured_backup_v1";
  const LAST_KEY = "scios_structured_backup_time_v1";
  const DAY = 24 * 60 * 60 * 1000;

  function notify(message) {
    const toast = document.querySelector("#toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 3200);
  }

  async function fetchBackup() {
    const response = await fetch("/api/backup/export", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Backup export failed (${response.status})`);
    return response.json();
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
    updateBadge();
  }

  async function restorePayload(payload) {
    const response = await fetch("/api/backup/import", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    let result = null;
    try { result = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(result?.detail || `Backup restore failed (${response.status})`);
    saveLocally(payload);
    notify("Structured hiring state restored; no external action was performed");
    window.setTimeout(() => location.reload(), 900);
  }

  function openDialog() {
    const dialog = document.querySelector("#dialog");
    const body = document.querySelector("#dialog-body");
    if (!dialog || !body) return;
    const last = localStorage.getItem(LAST_KEY);
    body.innerHTML = `<div class="dialog-card">
      <h2>Free continuity backup</h2>
      <p>This preserves structured profile evidence, verified roles, application state, preparation and Today actions. Raw CV files, passwords, sessions and private access tokens are excluded.</p>
      <div class="notice info"><strong>CHF 0 protection</strong><p>The app uses a temporary free database. A same-device browser copy is refreshed automatically, and a portable JSON file gives you an independent restore path.</p></div>
      <p class="meta">Last browser copy: ${last ? new Date(last).toLocaleString("en-CH") : "Not created yet"}</p>
      <div class="actions">
        <button class="primary" id="backup-download">Download current backup</button>
        <button class="secondary" id="backup-restore-browser" ${localStorage.getItem(LOCAL_KEY) ? "" : "disabled"}>Restore browser copy</button>
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
        const stored = localStorage.getItem(LOCAL_KEY);
        if (!stored) throw new Error("No browser backup is available");
        await restorePayload(JSON.parse(stored));
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

  function updateBadge() {
    const badge = document.querySelector("#zero-cost-continuity");
    if (!badge) return;
    const last = localStorage.getItem(LAST_KEY);
    badge.textContent = last ? "CHF 0 · backup protected" : "CHF 0 · create backup";
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

  async function automaticSnapshot() {
    const last = Date.parse(localStorage.getItem(LAST_KEY) || "0");
    if (Date.now() - last < DAY) return;
    try { await createBackup(false); } catch (_) { /* next authenticated load retries */ }
  }

  const observer = new MutationObserver(() => {
    const app = document.querySelector("#app");
    if (!app || app.hidden) return;
    installControls();
    automaticSnapshot();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  window.addEventListener("load", () => {
    installControls();
    automaticSnapshot();
  });
})();
