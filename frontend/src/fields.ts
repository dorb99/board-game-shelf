export const toText = (value: number | null) => (value == null ? '' : String(value))

/** Empty text is "unknown" (null); anything else must be a whole number of at least 1. */
export function parseCount(text: string): number | null | undefined {
  if (!text.trim()) return null
  const value = Number(text)
  return Number.isInteger(value) && value >= 1 ? value : undefined
}
