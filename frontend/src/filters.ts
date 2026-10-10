import type { GameDetails } from './api'

export type Length = 'short' | 'medium' | 'long'

export interface Filters {
  ownerId: number | null
  players: number | null
  length: Length | null
}

export const NO_FILTERS: Filters = { ownerId: null, players: null, length: null }

/** The highest player-count option means "this many or more". */
export const MAX_PLAYERS_OPTION = 8

export const LENGTHS: { value: Length; label: string; hint: string }[] = [
  { value: 'short', label: 'Short', hint: 'up to 40 min' },
  { value: 'medium', label: 'Medium', hint: '40–90 min' },
  { value: 'long', label: 'Long', hint: 'over 90 min' },
]

export function lengthOf(minutes: number | null): Length | null {
  if (minutes == null) return null
  if (minutes <= 40) return 'short'
  if (minutes <= 90) return 'medium'
  return 'long'
}

export function supportsPlayers(game: GameDetails, players: number): boolean {
  const min = game.min_players ?? game.max_players
  const max = game.max_players ?? game.min_players
  if (min == null || max == null) return false
  if (players >= MAX_PLAYERS_OPTION) return max >= MAX_PLAYERS_OPTION
  return min <= players && players <= max
}

/** Games with unknown data are hidden while the filter that needs it is active. */
export function matchesFilters(game: GameDetails & { owner_id: number }, filters: Filters) {
  if (filters.ownerId != null && game.owner_id !== filters.ownerId) return false
  if (filters.players != null && !supportsPlayers(game, filters.players)) return false
  if (filters.length != null && lengthOf(game.playing_time) !== filters.length) return false
  return true
}

export function playersLabel(game: GameDetails): string | null {
  const min = game.min_players ?? game.max_players
  const max = game.max_players ?? game.min_players
  if (min == null || max == null) return null
  return min === max ? `${min} players` : `${min}–${max} players`
}

export function timeLabel(game: GameDetails): string | null {
  return game.playing_time == null ? null : `${game.playing_time} min`
}
