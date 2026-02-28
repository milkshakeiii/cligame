// Scene uses 1 unit = 1000 meters
export const SCALE = 1 / 1000;

export function scalePos(x: number, y: number, z: number): [number, number, number] {
  return [x * SCALE, y * SCALE, z * SCALE];
}

export function scalePosTuple(p: [number, number, number]): [number, number, number] {
  return [p[0] * SCALE, p[1] * SCALE, p[2] * SCALE];
}

export function scaleDistance(d: number): number {
  return d * SCALE;
}
