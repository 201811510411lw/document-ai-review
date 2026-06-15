export const NAVIGATION_EVENT = "web-console:navigate";

export function navigateTo(path: string, options: { replace?: boolean } = {}) {
  if (options.replace) {
    window.history.replaceState({}, "", path);
  } else {
    window.history.pushState({}, "", path);
  }
  window.dispatchEvent(new Event(NAVIGATION_EVENT));
}
