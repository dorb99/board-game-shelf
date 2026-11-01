import { describe, expect, it } from 'vitest'
import type { Game } from './api'
import { stacksOf } from './components/Shelf'

const game = (id: number) => ({ id }) as Game
const ids = (piles: Game[][]) => piles.map((pile) => pile.map((item) => item.id))

describe('stacksOf', () => {
  it('piles boxes five high', () => {
    const games = [1, 2, 3, 4, 5, 6, 7].map(game)
    expect(ids(stacksOf(games))).toEqual([[1, 2, 3, 4, 5], [6, 7]])
  })
})
