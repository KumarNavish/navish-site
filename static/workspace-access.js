(() => {
  "use strict";
  const ACCESS_STORAGE_KEY = "scios_private_access";

  function showPrivateLinkMessage(message) {
    const app = document.querySelector("#app");
    const auth = document.querySelector("#auth");
    if (app) app.hidden = true;
    if (!auth) return;
    auth.hidden = false;
    auth.innerHTML = `<div class="auth-card"><div class="brand"><div class="mark">N</div><div><h1>Swiss Career Intelligence</h1><p>Private hiring workspace</p></div></div><div class="notice info"><strong>Private access</strong><p>${message}</p></div></div>`;
  }

  function revealApplicationShell() {
    const app = document.querySelector("#app");
    const auth = document.querySelector("#auth");
    if (auth) {
      auth.hidden = true;
      auth.replaceChildren();
    }
    if (app) app.hidden = false;
  }

  function loadApplication() {
    revealApplicationShell();
    const script = document.createElement("script");
    script.type = "module";
    script.src = "/assets/personal-workspace.js?v=focus10";
    script.onerror = () => showPrivateLinkMessage("The private workspace could not be loaded. Refresh once.");
    document.body.appendChild(script);
  }

  async function authenticationStatus() {
    const response = await fetch("/api/auth/status", { credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("Unable to check private access");
    return response.json();
  }

  async function exchangeAccessToken(token) {
    const response = await fetch("/api/auth/access", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) {
      let detail = "The private access link is invalid or expired.";
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
  }

  async function start() {
    try {
      const status = await authenticationStatus();
      if (status.authenticated) { loadApplication(); return; }
      const hash = window.location.hash.slice(1);
      let token = null;
      if (hash.startsWith("access=")) {
        token = decodeURIComponent(hash.slice("access=".length));
        localStorage.setItem(ACCESS_STORAGE_KEY, token);
        history.replaceState(null, "", `${window.location.pathname}#today`);
      } else {
        token = localStorage.getItem(ACCESS_STORAGE_KEY);
      }
      if (!token) {
        showPrivateLinkMessage("Open the private one-click app link on this device once. A secure session is then remembered automatically.");
        return;
      }
      await exchangeAccessToken(token);
      loadApplication();
    } catch (error) {
      localStorage.removeItem(ACCESS_STORAGE_KEY);
      showPrivateLinkMessage(error.message || "Private access could not be established.");
    }
  }

  start();
})();
