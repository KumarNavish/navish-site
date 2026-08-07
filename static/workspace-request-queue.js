(() => {
  "use strict";

  const nativeFetch = window.fetch.bind(window);
  const serializedPaths = new Set([
    "/api/workspace/applications",
    "/api/workspace/summary",
  ]);
  let queue = Promise.resolve();

  window.fetch = (input, init) => {
    const rawUrl = typeof input === "string" ? input : input?.url;
    let pathname = "";
    try {
      pathname = new URL(rawUrl, window.location.origin).pathname;
    } catch (_) {
      return nativeFetch(input, init);
    }

    if (!serializedPaths.has(pathname)) return nativeFetch(input, init);

    const execute = () => nativeFetch(input, init);
    const response = queue.then(execute, execute);
    queue = response.then(() => undefined, () => undefined);
    return response;
  };
})();
