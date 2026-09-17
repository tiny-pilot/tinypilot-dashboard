/** Pure helpers for device software-update banner copy/state. */

export const LICENSE_UPDATE_REASONS = {
  EXPIRED: 'your license has expired',
  UNLICENSED:
    'you need to attach a valid TinyPilot Pro license to this device to retrieve updates',
  INVALID: 'there is an issue with your license',
};

export function licenseReason(licenseCheckStatus) {
  return (
    LICENSE_UPDATE_REASONS[licenseCheckStatus] || LICENSE_UPDATE_REASONS.INVALID
  );
}

/**
 * @returns {'hidden'|'updating'|'available'|'license-blocked'|'error'|null}
 */
export function updateBannerKind(softwareUpdate, currentVersion) {
  if (!softwareUpdate) {
    return null;
  }
  const jobStatus = softwareUpdate.job?.status;
  if (jobStatus === 'IN_PROGRESS') {
    return 'updating';
  }
  if (softwareUpdate.latest_error && !softwareUpdate.latest) {
    return 'error';
  }
  if (!softwareUpdate.update_available) {
    return 'hidden';
  }
  if (softwareUpdate.can_start) {
    return 'available';
  }
  return 'license-blocked';
}

export function latestVersionFrom(softwareUpdate) {
  return softwareUpdate?.latest?.version || '';
}

export function licenseStatusFrom(softwareUpdate) {
  return softwareUpdate?.latest?.licenseCheckStatus || '';
}
