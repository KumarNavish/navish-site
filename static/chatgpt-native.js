(() => {
  "use strict";

  const state = { currentRoleId: null, status: null, connection: null };
  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response.status === 204 ? null : response.json();
  }

  function toast(message, tone = "info") {
    const target = document.querySelector("#toast");
    if (!target) return;
    target.textContent = message; target.dataset.tone = tone; target.classList.add("show");
    window.setTimeout(() => target.classList.remove("show"), 4200);
  }

  function dialog(title, body) {
    const node = document.querySelector("#dialog");
    const content = document.querySelector("#dialog-body");
    if (!node || !content) return;
    content.innerHTML = `<div class="chatgpt-dialog"><div class="chatgpt-dialog-head"><div><span>ChatGPT-native reasoning</span><h2>${escapeHtml(title)}</h2></div><button class="icon-button" data-close-chatgpt aria-label="Close">×</button></div>${body}</div>`;
    content.querySelector("[data-close-chatgpt]")?.addEventListener("click", () => node.close());
    node.showModal();
  }

  async function copyText(value) {
    try { await navigator.clipboard.writeText(value); return true; }
    catch (_) {
      const area = document.createElement("textarea");
      area.value = value; area.setAttribute("readonly", ""); area.style.position = "fixed"; area.style.opacity = "0";
      document.body.appendChild(area); area.select(); const copied = document.execCommand("copy"); area.remove(); return copied;
    }
  }

  async function openAnalysis(jobId) {
    window.open("https://chatgpt.com/", "_blank", "noopener,noreferrer");
    try {
      const packet = await api(`/api/chatgpt/jobs/${jobId}/packet`);
      sessionStorage.setItem(`scios-chatgpt-packet-${jobId}`, packet.prompt);
      const copied = await copyText(packet.prompt);
      dialog("Analyze this role with your Pro model", `<div class="chatgpt-flow">
        <div class="chatgpt-step complete"><strong>1</strong><div><b>Role context prepared</b><span>Verified evidence, source facts, deterministic gates, package and preparation are included.</span></div></div>
        <div class="chatgpt-step ${copied ? "complete" : "warning"}"><strong>2</strong><div><b>${copied ? "Prompt copied" : "Clipboard permission was blocked"}</b><span>${copied ? "ChatGPT opened in a new tab." : "Use Copy packet below, then open ChatGPT."}</span></div></div>
        <div class="chatgpt-step"><strong>3</strong><div><b>Select the strongest Pro model</b><span>Paste once and send. The packet requires raw validated JSON only.</span></div></div>
        <div class="chatgpt-step"><strong>4</strong><div><b>Return and import</b><span>Copy ChatGPT's JSON result, then use Import copied result.</span></div></div>
        <div class="chatgpt-actions"><button class="primary" data-copy-packet>Copy packet</button><button class="secondary" data-import-clipboard>Import copied result</button></div>
        <p class="chatgpt-boundary">No OpenAI API is called. API cost: CHF 0. An imported result cannot submit an application or contact anyone.</p>
      </div>`);
      document.querySelector("[data-copy-packet]")?.addEventListener("click", async () => { await copyText(packet.prompt); toast("ChatGPT role packet copied", "success"); });
      document.querySelector("[data-import-clipboard]")?.addEventListener("click", () => importClipboard(jobId));
    } catch (error) {
      toast(error.message || "Unable to prepare the ChatGPT role packet", "error");
    }
  }

  async function importClipboard(jobId) {
    try {
      const text = await navigator.clipboard.readText();
      if (!text.trim()) throw new Error("Clipboard is empty");
      const cleaned = text.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
      const result = await api(`/api/chatgpt/jobs/${jobId}/results`, { method: "POST", body: JSON.stringify(JSON.parse(cleaned)) });
      document.querySelector("#dialog")?.close();
      toast(`ChatGPT analysis imported: ${result.recommendation}`, "success");
      injectRoleAction();
    } catch (error) {
      dialog("Import ChatGPT result", `<p class="chatgpt-copy-help">Copy the complete JSON object produced by ChatGPT, then try the clipboard import again.</p>
        <textarea id="chatgpt-result-text" rows="14" placeholder='Paste the JSON object here'></textarea>
        <div class="chatgpt-actions"><button class="primary" data-submit-result>Validate and import</button></div>
        <p class="chatgpt-error">${escapeHtml(error.message || "The result could not be imported")}</p>`);
      document.querySelector("[data-submit-result]")?.addEventListener("click", async () => {
        try {
          const raw = document.querySelector("#chatgpt-result-text")?.value || "";
          const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
          const result = await api(`/api/chatgpt/jobs/${jobId}/results`, { method: "POST", body: JSON.stringify(JSON.parse(cleaned)) });
          document.querySelector("#dialog")?.close(); toast(`ChatGPT analysis imported: ${result.recommendation}`, "success"); injectRoleAction();
        } catch (inner) { toast(inner.message || "Result validation failed", "error"); }
      });
    }
  }

  async function rolePanel(jobId) {
    let latest = null;
    try { latest = (await api(`/api/chatgpt/jobs/${jobId}/latest-result`)).result; } catch (_) {}
    return `<section class="chatgpt-role-panel" data-chatgpt-role-panel>
      <div class="chatgpt-role-copy"><span>Use your ChatGPT Pro subscription</span><h3>Deepen this role analysis without API charges</h3><p>The app assembles one evidence-bounded packet. ChatGPT performs the consequential reasoning; deterministic gates remain authoritative.</p></div>
      <div class="chatgpt-role-actions"><button class="primary" data-chatgpt-analyze="${jobId}">Analyze in ChatGPT Pro</button><button class="secondary" data-chatgpt-import="${jobId}">Import copied result</button></div>
      ${latest ? `<div class="chatgpt-latest"><span>Latest imported result</span><strong>${escapeHtml(latest.result.recommendation)}</strong><small>${escapeHtml(latest.model_label)} · ${escapeHtml(latest.confidence)} confidence</small></div>` : ""}
      <small class="chatgpt-role-boundary">API disabled · CHF 0 · no external action</small>
    </section>`;
  }

  async function injectRoleAction() {
    const container = document.querySelector("#detail-content");
    if (!container || !state.currentRoleId || container.querySelector("[data-chatgpt-role-panel]")) return;
    const wrapper = document.createElement("div"); wrapper.innerHTML = await rolePanel(state.currentRoleId);
    const panel = wrapper.firstElementChild; if (!panel) return;
    const firstSection = container.querySelector("section");
    if (firstSection?.parentNode) firstSection.parentNode.insertBefore(panel, firstSection.nextSibling); else container.prepend(panel);
    panel.querySelector("[data-chatgpt-analyze]")?.addEventListener("click", () => openAnalysis(state.currentRoleId));
    panel.querySelector("[data-chatgpt-import]")?.addEventListener("click", () => importClipboard(state.currentRoleId));
  }

  async function showHub() {
    try {
      const [roles, status, connection] = await Promise.all([api("/api/live/roles"), api("/api/chatgpt/status"), api("/api/chatgpt/connection")]);
      state.status = status; state.connection = connection;
      const serious = roles.filter((role) => ["Strongly pursue", "Pursue", "Investigate one blocker"].includes(role.decision)).slice(0, 8);
      dialog("ChatGPT Pro reasoning", `<div class="chatgpt-hub-summary">
        <div><span>Execution surface</span><strong>${escapeHtml(status.execution_surface)}</strong></div><div><span>Reasoning tier</span><strong>${escapeHtml(status.reasoning_tier)}</strong></div>
        <div><span>API cost</span><strong>CHF 0</strong></div><div><span>Imported analyses</span><strong>${escapeHtml(status.imported_results)}</strong></div></div>
        <p class="chatgpt-hub-copy">Choose a role. The app copies one complete evidence-grounded prompt and opens ChatGPT. Select your strongest Pro model there.</p>
        <div class="chatgpt-role-list">${serious.map((role) => `<button data-hub-role="${role.id}"><span><strong>${escapeHtml(role.company)} · ${escapeHtml(role.title)}</strong><small>${escapeHtml(role.location)} · ${escapeHtml(role.decision)}</small></span><b>Analyze</b></button>`).join("") || "<p>No serious current role is available. Automatic discovery remains active.</p>"}</div>
        <div class="chatgpt-actions"><button class="secondary" data-copy-mcp>Copy read-only ChatGPT app URL</button></div>
        <p class="chatgpt-boundary">The custom ChatGPT app is intentionally read-only. Consequential state changes remain one-tap actions in this private PWA.</p>`);
      document.querySelectorAll("[data-hub-role]").forEach((button) => button.addEventListener("click", () => { document.querySelector("#dialog")?.close(); openAnalysis(Number(button.dataset.hubRole)); }));
      document.querySelector("[data-copy-mcp]")?.addEventListener("click", async () => { await copyText(connection.mcp_url); toast("Read-only ChatGPT app URL copied", "success"); });
    } catch (error) { toast(error.message || "ChatGPT-native tools are unavailable", "error"); }
  }

  function addTopbarButton() {
    if (document.querySelector("#chatgpt-pro-button")) return;
    const actions = document.querySelector(".topbar-actions"); if (!actions) return;
    const button = document.createElement("button"); button.id = "chatgpt-pro-button"; button.className = "chatgpt-topbar-button"; button.type = "button";
    button.innerHTML = `<span class="chatgpt-mark">AI</span><span><strong>ChatGPT Pro</strong><small>Interactive · CHF 0 API</small></span>`;
    button.addEventListener("click", showHub); actions.prepend(button);
  }

  function trackRoleClicks(event) {
    const opener = event.target.closest?.("[data-open-role]");
    if (opener?.dataset.openRole) { state.currentRoleId = Number(opener.dataset.openRole); window.setTimeout(injectRoleAction, 180); window.setTimeout(injectRoleAction, 700); }
  }

  function start() {
    addTopbarButton(); document.addEventListener("click", trackRoleClicks, true);
    new MutationObserver(() => { addTopbarButton(); injectRoleAction(); }).observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
