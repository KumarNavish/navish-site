"use strict";

(() => {
  const rationaleSelector = ".attention-reasons li, .opportunity-copy > p, .role-conversion-main li";
  const sourceSelector = ".impact-meta, .opportunity-tags, .source-line";

  function completeFirstClause(value) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    const contrast = normalized.search(/,\s+(?:and\s+)?while\b/i);
    if (contrast < 90) return normalized;
    return `${normalized.slice(0, contrast).replace(/[,:;\s]+$/, "")}.`;
  }

  function polishRationale(node) {
    if (!(node instanceof HTMLElement) || node.dataset.copyPolished === "true") return;
    const original = node.textContent || "";
    const revised = completeFirstClause(original);
    if (revised && revised !== original.trim()) {
      if (node.matches("li")) {
        const textNode = [...node.childNodes].find(
          (child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim(),
        );
        if (textNode) textNode.textContent = revised;
      } else {
        node.textContent = revised;
      }
    }
    node.dataset.copyPolished = "true";
  }

  function polishSourceRecency(node) {
    if (!(node instanceof Element)) return;
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let textNode = walker.nextNode();
    while (textNode) {
      textNode.textContent = textNode.textContent.replace(
        /\b(Verified|Retrieved|Posted) Due now\b/g,
        "$1 now",
      );
      textNode = walker.nextNode();
    }
  }

  function polish(root = document) {
    if (root instanceof Element && root.matches(rationaleSelector)) polishRationale(root);
    root.querySelectorAll?.(rationaleSelector).forEach(polishRationale);
    if (root instanceof Element && root.matches(sourceSelector)) polishSourceRecency(root);
    root.querySelectorAll?.(sourceSelector).forEach(polishSourceRecency);
  }

  const start = () => {
    const view = document.querySelector("#view");
    if (!view) return;
    polish(view);
    new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node instanceof Element) polish(node);
        }
      }
    }).observe(view, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
