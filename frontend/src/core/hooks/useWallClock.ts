/**
 * A coarse clock that re-renders subscribers on an interval — for "updated 3s ago" labels
 * and for re-evaluating price staleness when no new tick has arrived. One shared interval
 * per distinct period.
 */

import { useEffect, useState } from "react";

export function useWallClock(periodMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), periodMs);
    return () => clearInterval(id);
  }, [periodMs]);
  return now;
}
