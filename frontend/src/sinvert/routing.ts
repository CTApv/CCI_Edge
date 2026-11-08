export function sinvertDeviceUrl(deviceId: string): string {
  return `/sinvert.html?device=${encodeURIComponent(deviceId)}`;
}

export function requestedSinvertDevice(search: string): string | null {
  return new URLSearchParams(search).get("device");
}
