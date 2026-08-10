/* Brand hexes, duplicated out of tokens.css because three.js materials take
 * colours as values, not as CSS custom properties. Kept in one file so the
 * duplication is auditable rather than scattered through the scene.
 *
 * If a value here disagrees with tokens.css, tokens.css is right. */

export const BRAND = {
  dark: '#101c1f',
  light: '#f4f7f7',
  mid: '#9aa8ab',
  line: '#dde5e6',
  petrol: '#0e5a63',
  orange: '#b4611c',
  blue: '#2f6b9a',
  green: '#4a7343',
} as const

export const REMEDY_HEX = {
  QUERY: '#b4611c',  // DPJP, window shuts at discharge
  OBTAIN: '#2f6b9a', // petugas berkas
  RECODE: '#4a7343', // koder
} as const

export const CLEAN_HEX = '#c9d5d7'
