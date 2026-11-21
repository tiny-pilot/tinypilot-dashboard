// ponytail: proxy sends int ids. A non-numeric id makes the watermark NaN.
function maxEventId(events) {
  return events.length ? Math.max(...events.map((event) => event.id)) : null;
}

export function applyLanMonitorPoll(state, payload) {
  if (!payload || payload.ok !== true) {
    return state;
  }
  const events = Array.isArray(payload.events) ? payload.events : [];
  const monitored = new Map((payload.monitored || []).map((row) => [
    String(row.id),
    String(row.displayLabel || ''),
  ]));
  const highest = maxEventId(events);
  if (state.watermark === null) {
    return {
      watermark: highest === null ? 0 : highest,
      alerts: state.alerts.slice(),
    };
  }
  const open = new Map(state.alerts.map((alert) => [alert.deviceId, alert]));
  const ordered = events.slice().sort((a, b) => Number(a.id) - Number(b.id));
  for (const event of ordered) {
    const id = Number(event.id);
    if (!Number.isFinite(id) || id <= state.watermark) {
      continue;
    }
    const hostId = event.deviceId == null ? '' : String(event.deviceId);
    if (event.type === 'DEVICE_OFFLINE' && monitored.has(hostId)) {
      open.set(hostId, {
        deviceId: hostId,
        displayLabel: monitored.get(hostId),
        offlineAt: event.timestamp || '',
      });
    } else if (event.type === 'DEVICE_ONLINE') {
      open.delete(hostId);
    }
  }
  return {
    watermark: highest === null ? state.watermark : Math.max(state.watermark, highest),
    alerts: [...open.values()],
  };
}

export function dismissLanMonitorAlert(state, deviceId) {
  return {
    watermark: state.watermark,
    alerts: state.alerts.filter((alert) => alert.deviceId !== deviceId),
  };
}
