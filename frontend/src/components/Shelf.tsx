import type { Game, Owner } from '../api'
import { Spine } from './Spine'

interface Props {
  owner: Owner
  games: Game[]
  onSelect: (gameId: number) => void
}

export function Shelf({ owner, games, onSelect }: Props) {
  return (
    <section className="shelf">
      <h2 className="shelf-label">
        {owner.name} <span>{games.length === 1 ? '1 game' : `${games.length} games`}</span>
      </h2>
      <div className="shelf-rows">
        {games.map((game) => (
          <Spine key={game.id} game={game} onClick={() => onSelect(game.id)} />
        ))}
      </div>
    </section>
  )
}
