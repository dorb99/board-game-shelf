import type { Game, Owner } from '../api'
import { Spine } from './Spine'

interface Props {
  owner: Owner
  games: Game[]
  onSelect: (gameId: number) => void
}

/** Boxes lie flat, so they are piled this many high before a new pile starts. */
const STACK_SIZE = 5

function stacksOf(games: Game[]): Game[][] {
  const stacks = []
  for (let i = 0; i < games.length; i += STACK_SIZE) stacks.push(games.slice(i, i + STACK_SIZE))
  return stacks
}

export function Shelf({ owner, games, onSelect }: Props) {
  return (
    <section className="shelf">
      <h2 className="shelf-label">
        {owner.name} <span>{games.length === 1 ? '1 game' : `${games.length} games`}</span>
      </h2>
      <div className="shelf-rows">
        {stacksOf(games).map((stack) => (
          <div key={stack[0].id} className="stack">
            {stack.map((game) => (
              <Spine key={game.id} game={game} onClick={() => onSelect(game.id)} />
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}
