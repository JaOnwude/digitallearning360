/**
 * Turn a school's brand colours into design tokens that always pass WCAG AA (spec AC11).
 * The school picks colours; we pick the text colours that stay readable on them.
 */
type RGB = [number, number, number];

function parseHex(hex: string | null | undefined): RGB | null {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex ?? "").trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const toHex = ([r, g, b]: RGB) =>
  "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const WHITE: RGB = [255, 255, 255];
const NEAR_BLACK: RGB = [17, 17, 17];
const DARK_BG: RGB = [37, 37, 37]; // approx. --background in dark mode

/** Darken (towards black) or lighten (towards white) until the colour reaches `ratio` on `bg`. */
function adjustFor(color: RGB, bg: RGB, ratio: number, towards: RGB): RGB {
  let c = color;
  for (let i = 0; i < 20 && contrast(c, bg) < ratio; i++) {
    c = c.map((v, k) => v + (towards[k] - v) * 0.12) as RGB;
  }
  return c;
}

export type BrandTokens = Record<"--brand" | "--brand-foreground" | "--brand-ink", string>;

export function brandTokens(
  primaryHex: string | null | undefined,
  inkHex: string | null | undefined,
): { light: BrandTokens; dark: BrandTokens } | null {
  const primary = parseHex(primaryHex);
  if (!primary) return null;
  const fg = contrast(primary, NEAR_BLACK) >= contrast(primary, WHITE) ? NEAR_BLACK : WHITE;
  const preferredInk = parseHex(inkHex) ?? primary;
  return {
    light: {
      "--brand": toHex(primary),
      "--brand-foreground": toHex(fg),
      "--brand-ink": toHex(adjustFor(preferredInk, WHITE, 4.5, [0, 0, 0])),
    },
    dark: {
      "--brand": toHex(primary),
      "--brand-foreground": toHex(fg),
      "--brand-ink": toHex(adjustFor(primary, DARK_BG, 4.5, WHITE)),
    },
  };
}

/** A `<style>` body that overrides the platform brand tokens for one school. */
export function brandCss(tokens: { light: BrandTokens; dark: BrandTokens }): string {
  const decl = (t: BrandTokens) =>
    Object.entries(t)
      .map(([k, v]) => `${k}:${v}`)
      .join(";");
  return `:root{${decl(tokens.light)}}.dark{${decl(tokens.dark)}}`;
}
