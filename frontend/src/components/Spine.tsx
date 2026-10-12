import type { CSSProperties } from 'react'
import type { Game } from '../api'

/** Width divided by height of the strip a box shows on the shelf (boxes lie flat). */
export const SPINE_ASPECT = 5
export const DEFAULT_SLICE = 50

/** Stable pseudo-random number per game so boxes keep their size between renders. */
function hash(id: number): number {
  let h = id * 2654435761
  h ^= h >>> 15
  return Math.abs(h)
}

/**
 * Background showing one horizontal slice of the cover. `position` is how far down the
 * cover the slice sits, from 0 (top edge) to 100 (bottom edge).
 */
export function sliceBackground(imageUrl: string | null, position: number | null): CSSProperties {
  if (!imageUrl) return {}
  return {
    backgroundImage: `url("${imageUrl}")`,
    backgroundPosition: `center ${position ?? DEFAULT_SLICE}%`,
  }
}

export function Spine({ game, onClick }: { game: Game; onClick: () => void }) {
  const h = hash(game.id)
  const height = 40 + ((h >>> 4) % 3) * 5
  const style = {
    width: Math.round(height * SPINE_ASPECT) + (h % 3) * 12,
    height,
    backgroundColor: `hsl(${h % 360} 45% 32%)`,
    ...sliceBackground(game.image_url, game.spine_position),
  }
  // A box without a cover always needs its name; otherwise the label is optional.
  const showLabel = game.spine_label || !game.image_url
  return (
    <button className="spine" style={style} title={game.name} onClick={onClick}>
      {showLabel ? (
        <span className="spine-title">{game.name}</span>
      ) : (
        <span className="visually-hidden">{game.name}</span>
      )}
    </button>
  )
}
