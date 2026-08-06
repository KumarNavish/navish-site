"use strict";

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export const state = {
  route: "today",
  status: null,
  roles: [],
  applications: [],
  preparation: [],
  network: [],
  assets: null,
  profile: null,
  summary: null,
  detail: null,
};

export const ROUTES = {
  today: { label: "Today", subtitle: "Your hiring command center", icon: "home" },
  opportunities: { label: "Opportunities", subtitle: "Ranked, evidence-backed roles", icon: "search" },
  applications: { label: "Applications", subtitle: "Pipeline, follow-ups and deadlines", icon: "briefcase" },
  interviews: { label: "Interviews", subtitle: "Role-specific preparation", icon: "target" },
  network: { label: "Network", subtitle: "Contacts, outreach and referrals", icon: "users" },
  assets: { label: "Assets", subtitle: "Résumé versions and evidence", icon: "folder" },
  profile: { label: "Profile", subtitle: "Candidate evidence and constraints", icon: "user" },
};

const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-7h6v7"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  briefcase: '<rect width="20" height="14" x="2" y="7" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M2 12h20"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  folder: '<path d="M3 5h6l2 2h10v12H3z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  alert: '<path d="M12 3 2.5 20h19z"/><path d="M12 9v4m0 3h.01"/>',
  external: '<path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v6H4V3h6"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  filter: '<path d="M4 5h16l-6 7v5l-4 2v-7z"/>',
  sort: '<path d="M8 6h12M8 12h8M8 18h4M4 4v16m0 0-2-2m2 2 2-2"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  columns: '<rect x="3" y="4" width="7" height="16" rx="1"/><rect x="14" y="4" width="7" height="16" rx="1"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1-1"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h4"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  spark: '<path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
};

export function icon(name, size = 18, label = "") {
  const body = ICONS[name] || ICONS.more;
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${label ? `role="img" aria-label="${escapeHtml(label)}"` : 'aria-hidden="true"'}>${body}</svg>`;
}

export function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

export async function api(path, options = {}) {
  const headers = options.body instanceof FormData
    ? { ...(options.headers || {}) }
    : { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers,
  });
  let payload = null;
  try { payload = await response.json(); } catch (_) { payload = null; }
  if (response.status === 401) {
    location.reload();
    throw new Error("Private session expired. Reopen the private access link once.");
  }
  if (!response.ok) {
    const error = new Error(payload?.detail || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

export function formatDate(value, includeTime = false) {
  if (!value) return "Unconfirmed";
  try {
    return new Intl.DateTimeFormat("en-CH", includeTime
      ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Zurich" }
      : { day: "numeric", month: "short", year: "numeric", timeZone: "Europe/Zurich" }).format(new Date(value));
  } catch (_) {
    return String(value);
  }
}

export function formatRelative(value) {
  if (!value) return "Unconfirmed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const minutes = Math.round((date.getTime() - Date.now()) / 60000);
  const absolute = Math.abs(minutes);
  if (absolute < 60) return minutes >= 0 ? `in ${absolute} min` : `${absolute} min ago`;
  const hours = Math.round(absolute / 60);
  if (hours < 48) return minutes >= 0 ? `in ${hours} hr` : `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return minutes >= 0 ? `in ${days} day${days === 1 ? "" : "s"}` : `${days} day${days === 1 ? "" : "s"} ago`;
}

export function range(values, suffix = "%") {
  return Array.isArray(values) && values.length === 2
    ? `${escapeHtml(values[0])}–${escapeHtml(values[1])}${suffix}`
    : "Unconfirmed";
}

export function statusTone(value = "") {
  const low = String(value).toLowerCase();
  if (low.includes("strong") || low.includes("ready") || low.includes("success") || low.includes("active") || low.includes("offer")) return "positive";
  if (low.includes("reject") || low.includes("closed") || low.includes("withdraw") || low.includes("failed") || low.includes("overdue")) return "negative";
  if (low.includes("investigat") || low.includes("build") || low.includes("suggest") || low.includes("unconfirmed") || low.includes("attention")) return "warning";
  return "neutral";
}

export function badge(text, tone = "neutral", extra = "") {
  return `<span class="status-badge ${tone} ${extra}">${escapeHtml(text)}</span>`;
}

export function toast(message) {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 2800);
}

export function loading(message = "Loading hiring intelligence…") {
  return `<div class="loading-state"><div class="spinner" aria-hidden="true"></div><p>${escapeHtml(message)}</p></div>`;
}

export function emptyState(title, message, action = "") {
  return `<div class="empty-state"><div class="empty-icon">${icon("spark", 22)}</div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p>${action}</div>`;
}

export function errorState(error, retry = true) {
  return `<div class="error-state"><div>${icon("alert", 22)}</div><div><h2>Unable to load this view</h2><p>${escapeHtml(error.message || error)}</p>${retry ? '<button class="button secondary" data-retry-view>Retry</button>' : ""}</div></div>`;
}

export function pageHeader(title, description, action = "") {
  return `<header class="page-header"><div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>${action ? `<div class="page-actions">${action}</div>` : ""}</header>`;
}

export function button(label, { tone = "primary", iconName = "", attrs = "", compact = false } = {}) {
  return `<button class="button ${tone}${compact ? " compact" : ""}" ${attrs}>${iconName ? icon(iconName, 17) : ""}<span>${escapeHtml(label)}</span></button>`;
}

export function progress(value, label = "") {
  const safe = Math.max(0, Math.min(100, Number(value) || 0));
  return `<div class="progress" ${label ? `aria-label="${escapeHtml(label)}"` : ""}><span style="width:${safe}%"></span></div>`;
}

export function setTopbar(routeName) {
  const route = ROUTES[routeName] || ROUTES.today;
  const title = $("#route-title");
  const subtitle = $("#route-subtitle");
  if (title) title.textContent = route.label;
  if (subtitle) subtitle.textContent = route.subtitle;
  document.title = `${route.label} · Swiss Career Intelligence OS`;
}

export function showDialog(content, { className = "" } = {}) {
  const dialog = $("#dialog");
  const body = $("#dialog-body");
  body.className = className;
  body.innerHTML = content;
  dialog.showModal();
  const close = () => dialog.close();
  $$('[data-close-dialog]', body).forEach((control) => control.addEventListener("click", close));
  return { dialog, body, close };
}

export function openDetail(content) {
  const backdrop = $("#detail-backdrop");
  const drawer = $("#detail-drawer");
  const contentRoot = $("#detail-content");
  contentRoot.innerHTML = content;
  backdrop.hidden = false;
  drawer.hidden = false;
  document.body.classList.add("drawer-open");
  const closeButton = $("#detail-close");
  if (closeButton) closeButton.focus();
}

export function closeDetail() {
  const backdrop = $("#detail-backdrop");
  const drawer = $("#detail-drawer");
  if (backdrop) backdrop.hidden = true;
  if (drawer) drawer.hidden = true;
  document.body.classList.remove("drawer-open");
}

export function getPreference(key, fallback) {
  try {
    const raw = localStorage.getItem(`scios_view_${key}`);
    return raw === null ? fallback : JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}

export function setPreference(key, value) {
  try { localStorage.setItem(`scios_view_${key}`, JSON.stringify(value)); } catch (_) {}
}

export function copyText(value, successMessage = "Copied") {
  return navigator.clipboard.writeText(String(value || "")).then(() => toast(successMessage));
}

export function dateTimeLocalValue(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export function bindGlobalUI() {
  $("#detail-backdrop")?.addEventListener("click", closeDetail);
  $("#detail-close")?.addEventListener("click", closeDetail);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!$("#dialog")?.open) closeDetail();
      $("#mobile-panel")?.setAttribute("data-open", "false");
    }
  });
}
