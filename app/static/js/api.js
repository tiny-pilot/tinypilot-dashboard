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
  };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { error: httpErrorMessage(data, response) };
  }
  return data;
}

async function postJson(path, payload = {}) {
  return fetchJson(path, { method: 'POST', body: payload });
}

async function getJson(path) {
  return fetchJson(path);
}

async function deleteJson(path) {
  return fetchJson(path, { method: 'DELETE' });
}

window.dashboardApi = {
  deleteJson,
  getJson,
  postJson,
};
