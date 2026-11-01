import type { Game, Owner } from '../api'
import { Spine } from './Spine'

interface Props {
  owner: Owner
  /** Base games only; expansions live inside their base game's box. */
  games: Game[]
  /** How many expansions each game has, by game id. */
  expansionCounts: Map<number, number>
  onSelect: (gameId: number) => void
}

/** Boxes lie flat, so they are piled this many high before a new pile starts. */
const STACK_SIZE = 5

/** Piles of boxes, STACK_SIZE high. */
export function stacksOf(games: Game[]): Game[][] {
  const stacks: Game[][] = []
  for (let i = 0; i < games.length; i += STACK_SIZE) stacks.push(games.slice(i, i + STACK_SIZE))
  return stacks
}

function countLabel(games: Game[], expansionCounts: Map<number, number>): string {
  const expansions = games.reduce((sum, game) => sum + (expansionCounts.get(game.id) ?? 0), 0)
  const parts = [games.length === 1 ? '1 game' : `${games.length} games`]
  if (expansions) parts.push(expansions === 1 ? '1 expansion' : `${expansions} expansions`)
  return parts.join(' · ')
}

export function Shelf({ owner, games, expansionCounts, onSelect }: Props) {
  return (
    <section className="shelf">
      <h2 className="shelf-label">
        {owner.name} <span>{countLabel(games, expansionCounts)}</span>
      </h2>
      <div className="shelf-rows">
        {stacksOf(games).map((stack) => (
          <div key={stack[0].id} className="stack">
            {stack.map((game) => (
              <Spine
                key={game.id}
                game={game}
                expansions={expansionCounts.get(game.id) ?? 0}
                onClick={() => onSelect(game.id)}
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}
