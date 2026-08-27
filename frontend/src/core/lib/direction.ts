export type Dir = "up" | "down" | "flat";

export function dirOf(n: number): Dir {
  return n > 0 ? "up" : n < 0 ? "down" : "flat";
}
