import { describe, expect, it } from 'vitest'
import { lengthOf, matchesFilters, NO_FILTERS, playersLabel, supportsPlayers } from './filters'

const game = (min: number | null, max: number | null, time: number | null, owner = 1) => ({
  min_players: min,
  max_players: max,
  playing_time: time,
  owner_id: owner,
})

describe('lengthOf', () => {
  it.each([
    [1, 'short'],
    [40, 'short'],
    [41, 'medium'],
    [90, 'medium'],
    [91, 'long'],
    [240, 'long'],
    [null, null],
  ])('%s minutes is %s', (minutes, expected) => {
    expect(lengthOf(minutes)).toBe(expected)
  })
})

describe('supportsPlayers', () => {
  it('includes both ends of the range', () => {
    expect(supportsPlayers(game(2, 4, 60), 2)).toBe(true)
    expect(supportsPlayers(game(2, 4, 60), 4)).toBe(true)
    expect(supportsPlayers(game(2, 4, 60), 1)).toBe(false)
    expect(supportsPlayers(game(2, 4, 60), 5)).toBe(false)
  })

  it('treats the top option as "or more"', () => {
    expect(supportsPlayers(game(4, 12, 60), 8)).toBe(true)
    expect(supportsPlayers(game(10, 20, 60), 8)).toBe(true)
    expect(supportsPlayers(game(2, 7, 60), 8)).toBe(false)
  })

  it('uses the known bound when only one is set', () => {
    expect(supportsPlayers(game(2, null, 60), 2)).toBe(true)
    expect(supportsPlayers(game(2, null, 60), 3)).toBe(false)
  })

  it('never matches unknown player counts', () => {
    expect(supportsPlayers(game(null, null, 60), 2)).toBe(false)
  })
})

describe('matchesFilters', () => {
  it('matches everything with no filters, including unknown data', () => {
    expect(matchesFilters(game(null, null, null), NO_FILTERS)).toBe(true)
  })

  it('combines owner, players and length', () => {
    const filters = { ownerId: 1, players: 3, length: 'medium' as const }
    expect(matchesFilters(game(2, 4, 60), filters)).toBe(true)
    expect(matchesFilters(game(2, 4, 60, 2), filters)).toBe(false)
    expect(matchesFilters(game(4, 6, 60), filters)).toBe(false)
    expect(matchesFilters(game(2, 4, 30), filters)).toBe(false)
  })

  it('hides unknown play time only while the length filter is on', () => {
    expect(matchesFilters(game(2, 4, null), { ...NO_FILTERS, length: 'short' })).toBe(false)
    expect(matchesFilters(game(2, 4, null), { ...NO_FILTERS, players: 2 })).toBe(true)
  })
})

describe('playersLabel', () => {
  it('formats ranges, single counts and unknowns', () => {
    expect(playersLabel(game(2, 4, null))).toBe('2–4 players')
    expect(playersLabel(game(2, 2, null))).toBe('2 players')
    expect(playersLabel(game(null, null, null))).toBeNull()
  })
})
