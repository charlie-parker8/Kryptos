/**
 * The net-worth signature. Renders a formatted money string as split-flap cells; a digit
 * whose value changed remounts (new key) and replays the flip keyframe, the rest hold
 * still. No timers, no rAF — the hero updates a couple of times a second and re-rendering
 * ~12 cells that cheaply is fine.
 */

import { clsx } from "clsx";

interface SplitFlapNumberProps {
  /** decimal string from the wire */
  value: string;
  format: (n: number) => string;
  className?: string;
}

function classOf(char: string): string {
  if (char >= "0" && char <= "9") return "digit";
  if (char === "$") return "cur";
  if (char === "−" || char === "-") return "sign";
  return "punct"; // , .
}

export function SplitFlapNumber({
  value,
  format,
  className,
}: SplitFlapNumberProps) {
  const text = format(Number(value));
  return (
    <span className={clsx("flap", className)}>
      <span className="sr-only">{text}</span>
      {text.split("").map((char, index) => {
        const kind = classOf(char);
        if (kind !== "digit") {
          return (
            <span
              key={`${index}:${char}`}
              className={`flap-${kind}`}
              aria-hidden="true"
            >
              {char}
            </span>
          );
        }
        return (
          <span
            key={`${index}:${char}`}
            className="flap-cell"
            aria-hidden="true"
          >
            <span className="flap-char">{char}</span>
          </span>
        );
      })}
    </span>
  );
}
