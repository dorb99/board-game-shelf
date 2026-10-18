import { describe, expect, it } from 'vitest'
import type { Game } from './api'
import { groupsOf, stacksOf } from './components/Shelf'

const game = (id: number, parent_id: number | null = null) => ({ id, parent_id }) as Game
const ids = (piles: Game[][]) => piles.map((pile) => pile.map((item) => item.id))

describe('groupsOf', () => {
  it('puts each expansion right after its base game', () => {
    expect(ids(groupsOf([game(1), game(2), game(3, 1), game(4, 1)]))).toEqual([[1, 3, 4], [2]])
  })

  it('shows an expansion on its own when its base is filtered out', () => {
    expect(ids(groupsOf([game(2), game(3, 1)]))).toEqual([[2], [3]])
  })
})

describe('stacksOf', () => {
  it('keeps a game with its expansions in one pile', () => {
    const games = [game(1), game(2), game(3), game(4), game(5, 4), game(6, 4)]
    expect(ids(stacksOf(games))).toEqual([[1, 2, 3], [4, 5, 6]])
  })

  it('splits a group too big for one pile', () => {
    const games = [game(1), ...[2, 3, 4, 5, 6, 7].map((id) => game(id, 1))]
    expect(ids(stacksOf(games))).toEqual([[1, 2, 3, 4, 5], [6, 7]])
  })
})
