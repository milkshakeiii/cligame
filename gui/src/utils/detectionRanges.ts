import type { Ship } from "../api/types";

const DETECTOR_TYPES = new Set([
  "passive_detector",
  "starter_passive_detector",
]);

const SCANNER_TYPES = new Set(["scanner"]);

export interface ShipDetectionInfo {
  detectionRange: number;
  scanRange: number;
  maxRange: number;
}

const DEFAULT_DETECTION = 1000; // 1km base visibility

export function getShipDetectionInfo(ship: Ship): ShipDetectionInfo {
  let detectionRange = 0;
  let scanRange = 0;

  for (const m of ship.modules) {
    // Detection range counts whether active or not (passive capability)
    if (DETECTOR_TYPES.has(m.module_type) && m.detection_range) {
      detectionRange = Math.max(detectionRange, m.detection_range);
    }
    // Scanners only count when active
    if (m.active && SCANNER_TYPES.has(m.module_type) && m.scan_range) {
      scanRange = Math.max(scanRange, m.scan_range);
    }
  }

  if (detectionRange === 0) detectionRange = DEFAULT_DETECTION;
  const maxRange = Math.max(detectionRange, scanRange);

  return { detectionRange, scanRange, maxRange };
}
