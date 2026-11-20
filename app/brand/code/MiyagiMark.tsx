// The bonsai and the wordmark as React components.
// Copy ../logo/svg/* into app/src/assets/brand/ (Vite turns each import into a URL).
import treeFull from '../assets/brand/tree-full.svg';
import treeFullDark from '../assets/brand/tree-full-dark.svg';
import treeIcon from '../assets/brand/tree-icon.svg';
import treeIconDark from '../assets/brand/tree-icon-dark.svg';
import treeSmall from '../assets/brand/tree-small.svg';
import treeSmallDark from '../assets/brand/tree-small-dark.svg';
import wordmark from '../assets/brand/wordmark.svg';
import wordmarkDark from '../assets/brand/wordmark-dark.svg';

type Level = 'auto' | 'full' | 'icon' | 'small';
type Tone = 'light' | 'dark'; // "dark" = for dark backgrounds (lighter bark and clay)

const SRC = {
  full: { light: treeFull, dark: treeFullDark },
  icon: { light: treeIcon, dark: treeIconDark },
  small: { light: treeSmall, dark: treeSmallDark },
} as const;

/** The bonsai. Picks the right cut for the size: small at 32 px and under, icon up to 140 px, full above. */
export function MiyagiMark({ size = 32, tone = 'light', level = 'auto', className }: { size?: number; tone?: Tone; level?: Level; className?: string }) {
  const lvl = level === 'auto' ? (size <= 32 ? 'small' : size <= 140 ? 'icon' : 'full') : level;
  return <img src={SRC[lvl][tone]} width={size} height={size} alt="" aria-hidden draggable={false} className={className} />;
}

/** The wordmark: lowercase miyagi, green light on the first i. Height in px; width follows. */
export function MiyagiWordmark({ height = 24, tone = 'light', className }: { height?: number; tone?: Tone; className?: string }) {
  return <img src={tone === 'dark' ? wordmarkDark : wordmark} height={height} style={{ width: 'auto' }} alt="Miyagi" draggable={false} className={className} />;
}

/** Tree + wordmark side by side. */
export function MiyagiLockup({ height = 32, tone = 'light' }: { height?: number; tone?: Tone }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: height * 0.16 }}>
      <MiyagiMark size={height * 1.5} tone={tone} />
      <MiyagiWordmark height={height} tone={tone} />
    </span>
  );
}
