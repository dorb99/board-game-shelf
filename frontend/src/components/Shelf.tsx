import type { Game, Owner } from '../api'
import { Spine } from './Spine'

interface Props {
  owner: Owner
  games: Game[]
  onSelect: (gameId: number) => void
}

/** Boxes lie flat, so they are piled this many high before a new pile starts. */
const STACK_SIZE = 5

/** Each game followed by its expansions; an expansion whose base is not shown stands alone. */
export function groupsOf(games: Game[]): Game[][] {
  const shown = new Set(games.map((game) => game.id))
  return games
    .filter((game) => game.parent_id == null || !shown.has(game.parent_id))
    .map((game) => [game, ...games.filter((other) => other.parent_id === game.id)])
}

/** Piles of boxes, keeping a game with its expansions unless they cannot fit one pile. */
export function stacksOf(games: Game[]): Game[][] {
  const stacks: Game[][] = []
  for (const group of groupsOf(games)) {
    const last = stacks.at(-1)
    if (last && last.length + group.length <= STACK_SIZE) last.push(...group)
    else {
      for (let i = 0; i < group.length; i += STACK_SIZE) stacks.push(group.slice(i, i + STACK_SIZE))
    }
  }
  return stacks
}

function countLabel(games: Game[]): string {
  const expansions = games.filter((game) => game.parent_id != null).length
  const base = games.length - expansions
  const parts = [base === 1 ? '1 game' : `${base} games`]
  if (expansions) parts.push(expansions === 1 ? '1 expansion' : `${expansions} expansions`)
  return parts.join(' · ')
}

export function Shelf({ owner, games, onSelect }: Props) {
  return (
    <section className="shelf">
      <h2 className="shelf-label">
        {owner.name} <span>{countLabel(games)}</span>
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
