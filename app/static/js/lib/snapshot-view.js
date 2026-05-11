import { escapeHtml, stringValue, yesNoUnknown } from './strings.js';

function snapshotRow(label, valueText) {
  return `<div class="snapshot-row"><span>${escapeHtml(label)}</span><strong class="snapshot-row__value">${escapeHtml(valueText)}</strong></div>`;
}

function normalizeNetworkInterface(entry) {
  if (!entry || typeof entry !== 'object') {
    return null;
  }
  const name =
    stringValue(entry.name)
    || stringValue(entry.interface)
    || stringValue(entry.device)
    || 'unknown';
  const ip =
    stringValue(entry.ipAddress)
    || stringValue(entry.ip_address)
    || stringValue(entry.ip)
    || 'no ip';
  let connected = entry.isConnected;
  if (connected === undefined) {
    connected = entry.is_connected;
  }
  if (connected === undefined) {
    connected = entry.connected;
  }
  return { name, ip, connected };
}

function interfaceLinkLabel(connected) {
  if (connected === true) {
    return 'connected';
  }
  if (connected === false) {
    return 'disconnected';
  }
  return 'unknown';
}

function formatInterfaces(interfaces) {
  if (!Array.isArray(interfaces) || interfaces.length === 0) {
    return snapshotRow('Interfaces', 'None reported');
  }
  const normalized = interfaces
    .map(normalizeNetworkInterface)
    .filter(Boolean)
    .sort((a, b) => String(a.name).localeCompare(String(b.name), undefined, { sensitivity: 'base' }));
  return normalized.map((entry) => {
    const link = interfaceLinkLabel(entry.connected);
    const value = `${entry.ip} (${link})`;
    return snapshotRow(entry.name, value);
  }).join('');
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

// TinyPilot exposes different tuning knobs per streaming mode:
//   * H.264  -> bitrate (kbps) and frame rate (fps)
//   * MJPEG  -> quality (0-100) and frame rate (fps)
// Pick the right rows so the expanded panel reflects what the device is
// actually running.
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

  const frameRate = firstDefinedNumber([
    video.mjpegFrameRate,
    video.mjpeg_frame_rate,
    video.h264FrameRate,
    video.h264_frame_rate,
    video.frameRate,
    video.framesPerSecond,
    status.mjpegFrameRate,
    status.h264FrameRate,
    status.frameRate,
    status.framesPerSecond,
  ]);

  if (modeLabel === 'MJPEG') {
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

  // Default to H.264-style rows when the mode is H.264 or unknown.
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
  if (frameRate !== null) {
    lines.push(snapshotRow('Frame rate', `${frameRate} fps`));
  }
  return lines;
}

export function formatExpandedSnapshot(snapshot) {
  const expanded = snapshot.expanded || {};
  const status = expanded.reachability?.status || {};
  const version = expanded.version?.status || {};
  const https = expanded.https_requirement?.status || {};
  const video = expanded.video_settings?.status || {};

  const interfaces = expanded.network?.interfaces || [];
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
        ${snapshotRow('Requires HTTPS', yesNoUnknown(https.requiresHttps))}
      </div>
      <div class="snapshot-section">
        <h4 class="snapshot-section-title">Network interfaces</h4>
        ${formatInterfaces(interfaces)}
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
