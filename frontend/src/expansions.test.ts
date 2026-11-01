import { describe, expect, it } from 'vitest'
import { withExpansions } from './filters'

const details = (min: number | null, max: number | null) => ({
  min_players: min,
  max_players: max,
  playing_time: 60,
})

describe('withExpansions', () => {
  it('widens the player range to cover every expansion', () => {
    const combined = withExpansions(details(3, 4), [details(5, 6), details(2, 4)])
    expect([combined.min_players, combined.max_players]).toEqual([2, 6])
    expect(combined.playing_time).toBe(60)
  })

  it('keeps the game as it is without expansions or known counts', () => {
    expect(withExpansions(details(3, 4), [])).toEqual(details(3, 4))
    expect(withExpansions(details(null, null), [details(null, null)])).toEqual(details(null, null))
  })

  it('uses an expansion range when the game has none', () => {
    const combined = withExpansions(details(null, null), [details(1, 5)])
    expect([combined.min_players, combined.max_players]).toEqual([1, 5])
  })
})
