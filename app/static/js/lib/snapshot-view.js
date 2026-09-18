import { escapeHtml, stringValue } from './strings.js';

function snapshotRow(label, valueText) {
  return `<div class="snapshot-row"><span>${escapeHtml(label)}</span><strong class="snapshot-row__value">${escapeHtml(valueText)}</strong></div>`;
}

function friendlyInterfaceName(name) {
  const raw = stringValue(name);
  if (raw === 'eth0') {
    return 'LAN1';
  }
  if (raw === 'eth1') {
    return 'LAN2';
  }
  if (raw === 'wlan0') {
    return 'Wi-Fi';
  }
  return raw || 'Interface';
}

function interfaceConnected(iface) {
  let connected = iface.isConnected;
  if (connected === undefined) {
    connected = iface.is_connected;
  }
  if (connected === undefined) {
    connected = iface.connected;
  }
  return connected;
}

function formatNetworkInterface(iface) {
  if (!iface || typeof iface !== 'object') {
    return '';
  }
  const label = friendlyInterfaceName(iface.name);
  const ip =
    stringValue(iface.ipAddress)
    || stringValue(iface.ip_address)
    || stringValue(iface.ip);
  const mac =
    stringValue(iface.macAddress)
    || stringValue(iface.mac_address)
    || stringValue(iface.mac);
  const connected = interfaceConnected(iface);

  // One primary line: IP when present, otherwise link state (IP + status are
  // usually redundant for a glanceable dashboard).
  let primary = ip;
  if (!primary) {
    if (connected === true) {
      primary = 'No IP';
    } else if (connected === false) {
      primary = 'No link';
    } else {
      primary = 'unknown';
    }
  }

  const rows = [snapshotRow(label, primary)];
  if (mac) {
    rows.push(snapshotRow('MAC', mac));
  }
  return `<div class="snapshot-iface">${rows.join('')}</div>`;
}

function formatNetworkData(data) {
  if (!data || typeof data !== 'object') {
    return snapshotRow('Network', 'None reported');
  }
  // Pro 3.2.0+: { interfaces: [{ name, ipAddress, macAddress, isConnected }, ...] }
  if (Array.isArray(data.interfaces)) {
    const parts = data.interfaces
      .map((iface) => formatNetworkInterface(iface))
      .filter(Boolean);
    if (parts.length === 0) {
      return snapshotRow('Network', 'None reported');
    }
    return `<div class="snapshot-iface-list">${parts.join('')}</div>`;
  }
  // Legacy ethernet/wifi shape (pre-3.2.0).
  const parts = [];
  if (data.ethernet) {
    parts.push(formatNetworkInterface({ ...data.ethernet, name: 'eth0' }));
  }
  if (data.wifi) {
    parts.push(formatNetworkInterface({ ...data.wifi, name: 'wlan0' }));
  }
  if (parts.length === 0) {
    return snapshotRow('Network', 'None reported');
  }
  return `<div class="snapshot-iface-list">${parts.join('')}</div>`;
}

// TinyPilot ships two streaming modes today: H.264 and MJPEG. Normalize the
// various string forms TinyPilot has used over time ("H264", "h.264",
// "h-264", "MJPEG", "mjpeg", etc.) into the two canonical labels. Anything
// else is passed through verbatim so unexpected values stay visible.
function formatStreamingModeDisplay(raw) {
  const asString = typeof raw === 'string' ? raw : raw != null ? String(raw) : '';
  const trimmed = stringValue(asString);
  if (!trimmed) {
    return '';
  }
  const compact = trimmed.toUpperCase().replace(/[.\-_\s]/g, '');
  if (compact === 'MJPEG') {
    return 'MJPEG';
  }
  if (compact === 'H264') {
    return 'H.264';
  }
  return trimmed;
}

function firstDefinedNumber(values) {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

// TinyPilot exposes different tuning knobs per streaming mode (same as the
 // device Web UI video settings dialog):
 //   * H.264  -> bitrate (kbps) and high-performance mode (not MJPEG fps)
 //   * MJPEG  -> frame rate (fps) and quality (0-100)
 // Do not surface the other mode's dormant settings — e.g. mjpegFrameRate
 // stays populated while streaming H.264 and is not the active frame rate.
function formatVideoTuning(videoSettings, statusSettings) {
  const video = videoSettings && typeof videoSettings === 'object' ? videoSettings : {};
  const status = statusSettings && typeof statusSettings === 'object' ? statusSettings : {};
  const lines = [];

  const modeRaw =
    video.streamingMode
    ?? video.streaming_mode
    ?? status.streamingMode
    ?? status.streaming_mode;
  const modeLabel = formatStreamingModeDisplay(modeRaw);
  if (modeLabel) {
    lines.push(snapshotRow('Streaming mode', modeLabel));
  }

  if (modeLabel === 'MJPEG') {
    const frameRate = firstDefinedNumber([
      video.mjpegFrameRate,
      video.mjpeg_frame_rate,
      status.mjpegFrameRate,
    ]);
    const quality = firstDefinedNumber([
      video.mjpegQuality,
      video.mjpeg_quality,
      video.quality,
      status.mjpegQuality,
      status.quality,
    ]);
    if (frameRate !== null) {
      lines.push(snapshotRow('Frame rate', `${frameRate} fps`));
    }
    if (quality !== null) {
      lines.push(snapshotRow('Quality', `${quality}`));
    }
    return lines;
  }

  // H.264 (canonical) — also used when mode is missing but bitrate is present.
  const bitrate = firstDefinedNumber([
    video.h264Bitrate,
    video.h264_bitrate,
    video.bitrate,
    status.h264Bitrate,
    status.bitrate,
  ]);
  if (bitrate !== null) {
    lines.push(snapshotRow('Bitrate', `${bitrate} kbps`));
  }

  let highPerformance = video.h264HighPerformance;
  if (highPerformance === undefined) {
    highPerformance = video.h264_high_performance;
  }
  if (highPerformance === undefined) {
    highPerformance = status.h264HighPerformance;
  }
  if (typeof highPerformance === 'boolean') {
    lines.push(
      snapshotRow('High-performance mode', highPerformance ? 'On' : 'Off'),
    );
  }
  return lines;
}

export function formatExpandedSnapshot(snapshot) {
  const expanded = snapshot.expanded || {};
  const status = expanded.reachability?.status || {};
  const version = expanded.version?.status || {};
  const video = expanded.video_settings?.status || {};

  const networkData = expanded.network?.data || {};
  const videoTuning = formatVideoTuning(video, status);
  const resolutionRow = snapshotRow(
    'Connected device resolution',
    expanded.connected_device_resolution || 'unknown',
  );
  const videoRows = [resolutionRow, ...videoTuning];

  return `
    <div class="snapshot-expanded-stack">
      <div class="snapshot-section">
        <h4 class="snapshot-section-title">Overview</h4>
        ${snapshotRow('Target URL', snapshot.source_base_url || 'unknown')}
        ${snapshotRow('Software version', version.version || 'unknown')}
        ${snapshotRow('Reachability', expanded.reachability?.error ? 'Error' : 'OK')}
      </div>
      <div class="snapshot-section">
        <h4 class="snapshot-section-title">Network status</h4>
        ${formatNetworkData(networkData)}
      </div>
      <div class="snapshot-section">
        <h4 class="snapshot-section-title">Video</h4>
        ${videoRows.join('')}
      </div>
      ${
        expanded.last_management_error
          ? `<div class="snapshot-section snapshot-section--error"><h4 class="snapshot-section-title">Last management error</h4><p class="snapshot-section-error-text">${escapeHtml(expanded.last_management_error)}</p></div>`
          : ''
      }
    </div>
  `;
}
