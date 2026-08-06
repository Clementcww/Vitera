/* Brand hexes, duplicated out of tokens.css because three.js materials take
 * colours as values, not as CSS custom properties. Kept in one file so the
 * duplication is auditable rather than scattered through the scene. */

export const BRAND = {
  dark: '#141413',
  light: '#faf9f5',
  mid: '#b0aea5',
  line: '#e8e6dc',
  orange: '#d97757',
  blue: '#6a9bcc',
  green: '#788c5d',
} as const

export const REMEDY_HEX = {
  QUERY: '#d97757',  // DPJP — window shuts at discharge
  OBTAIN: '#4f7ba8', // petugas berkas
  RECODE: '#5e7047', // koder
} as const

export const CLEAN_HEX = '#d9d6c9'
