import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyLanMonitorPoll,
  dismissLanMonitorAlert,
} from '../app/static/js/lib/lan-monitor.js';

const firewall = { id: 'fw', displayLabel: 'Firewall' };
const line = { deviceId: 'fw', displayLabel: 'Firewall', offlineAt: 't5' };

function poll(state, events, monitored = [firewall]) {
  return applyLanMonitorPoll(state, { ok: true, events, monitored });
}

test('first success records the mark and does not alert', () => {
  const next = poll({ watermark: null, alerts: [] }, [
    { id: 4, type: 'DEVICE_OFFLINE', deviceId: 'fw', timestamp: 't' },
  ]);
  assert.equal(next.watermark, 4);
  assert.deepEqual(next.alerts, []);
});

test('a later monitored offline adds one line', () => {
  const next = poll({ watermark: 4, alerts: [] }, [
    { id: 5, type: 'DEVICE_OFFLINE', deviceId: 'fw', timestamp: 't5' },
    { id: 6, type: 'DEVICE_DISCOVERED', deviceId: 'other', timestamp: 't6' },
  ]);
  assert.equal(next.watermark, 6);
  assert.deepEqual(next.alerts, [line]);
});

test('an unmonitored offline is ignored', () => {
  const next = poll({ watermark: 1, alerts: [] }, [
    { id: 2, type: 'DEVICE_OFFLINE', deviceId: 'guest', timestamp: 't' },
  ]);
  assert.deepEqual(next.alerts, []);
});

test('coming back online removes the line', () => {
  const next = poll({ watermark: 5, alerts: [line] }, [
    { id: 7, type: 'DEVICE_ONLINE', deviceId: 'fw', timestamp: 't7' },
  ]);
  assert.deepEqual(next.alerts, []);
  assert.equal(next.watermark, 7);
});

test('a failed poll leaves the mark and the lines', () => {
  const state = { watermark: 5, alerts: [line] };
  assert.equal(applyLanMonitorPoll(state, { ok: false }), state);
});

test('an event at the watermark does not alert again', () => {
  const next = poll({ watermark: 5, alerts: [] }, [
    { id: 5, type: 'DEVICE_OFFLINE', deviceId: 'fw', timestamp: 't5' },
  ]);
  assert.deepEqual(next.alerts, []);
  assert.equal(next.watermark, 5);
});

test('dismiss removes one line and leaves the mark', () => {
  const next = dismissLanMonitorAlert({
    watermark: 9,
    alerts: [line, { deviceId: 'nas', displayLabel: 'NAS', offlineAt: 't' }],
  }, 'fw');
  assert.equal(next.watermark, 9);
  assert.deepEqual(next.alerts, [
    { deviceId: 'nas', displayLabel: 'NAS', offlineAt: 't' },
  ]);
});
