function httpErrorMessage(data, response) {
  if (typeof data.error === 'string' && data.error) {
    return data.error;
  }
  if (typeof data.message === 'string' && data.message) {
    return data.message;
  }
  const fallback = `${response.status} ${response.statusText}`.trim();
  return fallback || 'request failed';
}

async function fetchJson(path, { method = 'GET', body } = {}) {
  const init = {
    method,
    credentials: 'same-origin',
    headers: {},
    signal: AbortSignal.timeout(30_000),
  };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  try {
    const response = await fetch(path, init);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { error: httpErrorMessage(data, response), code: data.code };
    }
    return data;
  } catch {
    return { error: 'Could not reach the dashboard.' };
  }
}

async function postJson(path, payload = {}) {
  return fetchJson(path, { method: 'POST', body: payload });
}

async function getJson(path) {
  return fetchJson(path);
}

async function putJson(path, body = {}) {
  return fetchJson(path, { method: 'PUT', body });
}

async function deleteJson(path) {
  return fetchJson(path, { method: 'DELETE' });
}

async function postScreenshot(path) {
  try {
    const response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      signal: AbortSignal.timeout(30_000),
    });
    const contentType = response.headers.get('Content-Type') || '';
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return { error: httpErrorMessage(data, response), code: data.code };
    }
    if (!contentType.includes('image/jpeg')) {
      return { error: 'Unexpected screenshot response' };
    }
    const capturedAt =
      response.headers.get('X-Captured-At') || new Date().toISOString();
    const cacheCopy = response.clone();
    const blob = await response.blob();
    return { blob, capturedAt, cacheCopy };
  } catch {
    return { error: 'Could not reach the dashboard.' };
  }
}

window.dashboardApi = {
  deleteJson,
  getJson,
  postJson,
  postScreenshot,
  putJson,
};
