/**
 * Feature: launcher. Every fill the launcher needs that core/theme.ts has no token for yet.
 * Derived from the theme's colors wherever one fits, so Adrian's theme flows straight through;
 * the two aurora hues (violet, pink) are the only new colors, and they live here, in one place
 * (see "Core requests" in the brief).
 */
import { color } from "../../core/theme";

/** A theme color (#RRGGBB) at an alpha, as rgba() (animatable everywhere, unlike 8-digit hex). */
export function rgba(hex: string, a: number): string {
  const n = parseInt(hex.slice(1, 7), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Mix a theme color toward white (t = 0 → the color, 1 → white). */
function lighten(hex: string, t: number): string {
  const n = parseInt(hex.slice(1, 7), 16);
  const ch = (v: number): number => Math.round(v + (255 - v) * t);
  return `rgb(${ch((n >> 16) & 255)},${ch((n >> 8) & 255)},${ch(n & 255)})`;
}

/** The aurora's two extra hues (accent → violet → pink). */
export const violet = "#7D5CFF";
export const pink = "#E35BD0";

export const tint = {
  /** Search field: an opaque fill (it sits on the moving light), and the resting edge under the light. */
  fieldSolid: "#131317",
  fieldEdge: "rgba(255,255,255,.1)",
  /** The light that travels around the field: a comet sweep, transparent for the last quarter turn. */
  ring: `conic-gradient(from 0deg, transparent 0deg, ${color.accent} 80deg, ${violet} 160deg, ${pink} 220deg, transparent 290deg)`,
  /** Soft color blobs behind the title. */
  ambient: [rgba(color.accent, 0.5), rgba(violet, 0.45), rgba(pink, 0.3)],
  /** Backdrop: a dim, plus light spilling down out of the notch. */
  dim: "rgba(0,0,0,.34)",
  notchGlow: `radial-gradient(ellipse 50% 48% at 50% 0%, ${rgba(color.accent, 0.2)}, ${rgba(violet, 0.08)} 45%, transparent 75%)`,
  /** Title: white fading down a touch. */
  title: "linear-gradient(180deg, #fff 30%, rgba(255,255,255,.62))",
  /** Section rule. */
  divider:
    "linear-gradient(90deg, transparent, rgba(255,255,255,.1) 18%, rgba(255,255,255,.1) 82%, transparent)",
  /** Chips (suggestions, quick actions). */
  chip: "rgba(255,255,255,.05)",
  chipHover: "rgba(255,255,255,.1)",
  chipBorder: "rgba(255,255,255,.08)",
  /** The gliding row highlight. */
  highlight: `linear-gradient(90deg, ${rgba(color.accent, 0.22)}, ${rgba(color.accent, 0.06)})`,
  highlightBorder: rgba(color.accent, 0.38),
  highlightGlow: `0 0 28px ${rgba(color.accent, 0.16)}`,
  /** Accent text on dark (badges). */
  accentText: lighten(color.accent, 0.35),
  accentBadge: rgba(color.accent, 0.16),
  /** Icon tiles and skeletons. */
  icon: "rgba(255,255,255,.07)",
  skeleton:
    "linear-gradient(90deg, rgba(255,255,255,.05) 0%, rgba(255,255,255,.13) 50%, rgba(255,255,255,.05) 100%)",
  /** Primary button: lit from the top, glowing; ghost when it can't act yet. */
  button: `linear-gradient(180deg, rgba(255,255,255,.24), rgba(255,255,255,0) 65%), ${color.accent}`,
  buttonInset:
    "inset 0 1px 0 rgba(255,255,255,.3), inset 0 -1px 0 rgba(0,0,0,.15)",
  buttonGlow: `0 8px 26px ${rgba(color.accent, 0.5)}`,
  buttonGlowOff: `0 8px 26px ${rgba(color.accent, 0)}`,
  sheen:
    "linear-gradient(90deg, transparent, rgba(255,255,255,.35), transparent)",
  ghost: "rgba(255,255,255,.06)",
  onAccent: "rgba(255,255,255,.22)",
  /**
   * Shadows. pill/card must equal core/Island.tsx's (so the hand-over is invisible); each has the same
   * three layers as `panel` (the extra ones fully transparent) so the spring can interpolate between them.
   */
  pillShadow: `0 2px 10px rgba(0,0,0,.25), 0 0 0 0px rgba(255,255,255,0), 0 0 0px 0px ${rgba(color.accent, 0)}`,
  cardShadow: `0 24px 60px rgba(0,0,0,.5), 0 0 0 0px rgba(255,255,255,0), 0 0 0px 0px ${rgba(color.accent, 0)}`,
  panelShadow: `0 30px 90px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.08), 0 0 90px 0px ${rgba(color.accent, 0.2)}`,
} as const;

/** One tone per source kind (tile glyphs). */
export const kindTone: Record<string, string> = {
  video: color.accent,
  notebook: color.green,
  repo: color.green,
  paper: color.amber,
  blog: violet,
};
