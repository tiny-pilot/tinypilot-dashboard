/** Browser Cache Storage for the last live preview per device (origin-scoped). */

export const PREVIEW_CACHE_NAME = 'tinypilot-dashboard-previews-v1';

function previewRequest(deviceId) {
  return new Request(`/device-preview/${deviceId}`);
}

export async function putPreview(deviceId, response) {
  if (!('caches' in window)) {
    return;
  }
  const cache = await caches.open(PREVIEW_CACHE_NAME);
  await cache.put(previewRequest(deviceId), response);
}

export async function getPreview(deviceId) {
  if (!('caches' in window)) {
    return null;
  }
  const cache = await caches.open(PREVIEW_CACHE_NAME);
  return cache.match(previewRequest(deviceId));
}

export async function clearPreviewCache() {
  if (!('caches' in window)) {
    return false;
  }
  return caches.delete(PREVIEW_CACHE_NAME);
}

window.tinypilotPreviewCache = { PREVIEW_CACHE_NAME, clearPreviewCache };
