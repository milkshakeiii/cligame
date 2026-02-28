/** Format a distance in meters for display (e.g. "2.4 km", "340 m") */
export function formatDistance(meters: number): string {
  if (meters >= 10_000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  if (meters >= 1_000) {
    return `${(meters / 1000).toFixed(2)} km`;
  }
  return `${Math.round(meters)} m`;
}

/** Format speed in m/s */
export function formatSpeed(mps: number): string {
  return `${Math.round(mps)} m/s`;
}

/** Compute speed from velocity components */
export function speed(vx: number, vy: number, vz: number): number {
  return Math.sqrt(vx * vx + vy * vy + vz * vz);
}

/** Ship class display name */
export function shipClassName(cls: string): string {
  return cls
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
