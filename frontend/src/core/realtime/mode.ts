/**
 * Dev / screenshot mode flags, read from the URL once. `?mock` runs the app on the
 * deterministic mock feed with the auth gate bypassed — no backend needed. `?frozen`
 * additionally holds the feed on one deterministic frame for stable screenshots.
 */

const params =
  typeof window !== "undefined"
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams();

export const IS_FROZEN = params.has("frozen");
export const IS_MOCK_MODE = IS_FROZEN || params.has("mock");
/** `?bankrupt` fires one fake `bankruptcy_reset` on load so the modal can be previewed. */
export const IS_BANKRUPT_PREVIEW = params.has("bankrupt");
