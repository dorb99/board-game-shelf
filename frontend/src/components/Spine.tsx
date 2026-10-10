import type { Game } from '../api'

/** Stable pseudo-random number per game so boxes keep their size between renders. */
function hash(id: number): number {
  let h = id * 2654435761
  h ^= h >>> 15
  return Math.abs(h)
}

export function Spine({ game, onClick }: { game: Game; onClick: () => void }) {
  const h = hash(game.id)
  const style = {
    width: 46 + (h % 5) * 7,
    height: 192 + ((h >>> 4) % 4) * 12,
    backgroundColor: `hsl(${h % 360} 45% 32%)`,
    backgroundImage: game.image_url ? `url("${game.image_url}")` : undefined,
  }
  return (
    <button className="spine" style={style} title={game.name} onClick={onClick}>
      <span className="spine-title">{game.name}</span>
    </button>
  )
}
