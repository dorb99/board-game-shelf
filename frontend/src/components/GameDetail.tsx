import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Game, type GameChanges, type Owner } from '../api'
import { parseCount, toText } from '../fields'
import { Modal } from './Modal'
import { type OwnerChoice, OwnerPicker, toOwnerRef } from './OwnerPicker'
import { RulesChat } from './RulesChat'

interface Props {
  game: Game
  owners: Owner[]
  onClose: () => void
}

export function GameDetail({ game, owners, onClose }: Props) {
  const queryClient = useQueryClient()
  const [minPlayers, setMinPlayers] = useState(toText(game.min_players))
  const [maxPlayers, setMaxPlayers] = useState(toText(game.max_players))
  const [playingTime, setPlayingTime] = useState(toText(game.playing_time))
  const [owner, setOwner] = useState<OwnerChoice>({ id: game.owner_id, newName: '' })

  const refresh = () => queryClient.invalidateQueries()
  const save = useMutation({
    mutationFn: (changes: GameChanges) => api.updateGame(game.id, changes),
    onSuccess: async (updated) => {
      await refresh()
      setOwner({ id: updated.owner_id, newName: '' })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.deleteGame(game.id),
    onSuccess: async () => {
      await refresh()
      onClose()
    },
  })

  const parsed = {
    min_players: parseCount(minPlayers),
    max_players: parseCount(maxPlayers),
    playing_time: parseCount(playingTime),
  }
  const ownerRef = toOwnerRef(owner)
  const valid = ownerRef != null && Object.values(parsed).every((value) => value !== undefined)
  const dirty =
    parsed.min_players !== game.min_players ||
    parsed.max_players !== game.max_players ||
    parsed.playing_time !== game.playing_time ||
    owner.id !== game.owner_id

  function confirmRemove() {
    if (window.confirm(`Remove ${game.name} from the library?`)) remove.mutate()
  }

  return (
    <Modal label={game.name} className="game-detail" onClose={onClose}>
      <div className="detail-side">
        {game.image_url ? (
          <img className="cover" src={game.image_url} alt={`${game.name} box cover`} />
        ) : (
          <div className="cover placeholder">{game.name}</div>
        )}

        <div className="detail-form">
          <label>
            Players
            <span className="range">
              <input
                type="number"
                min={1}
                aria-label="Minimum players"
                value={minPlayers}
                onChange={(event) => setMinPlayers(event.target.value)}
              />
              to
              <input
                type="number"
                min={1}
                aria-label="Maximum players"
                value={maxPlayers}
                onChange={(event) => setMaxPlayers(event.target.value)}
              />
            </span>
          </label>
          <label>
            Play time (minutes)
            <input
              type="number"
              min={1}
              value={playingTime}
              onChange={(event) => setPlayingTime(event.target.value)}
            />
          </label>
          <label>
            Owner
            <OwnerPicker owners={owners} value={owner} onChange={setOwner} />
          </label>

          <div className="detail-actions">
            <button
              className="primary"
              disabled={!dirty || !valid || save.isPending}
              onClick={() => save.mutate({ ...(parsed as GameChanges), ...ownerRef })}
            >
              {save.isPending ? 'Saving…' : 'Save changes'}
            </button>
            <button className="danger" disabled={remove.isPending} onClick={confirmRemove}>
              Remove
            </button>
          </div>
          {(save.error ?? remove.error) && (
            <p className="notice error">{(save.error ?? remove.error)!.message}</p>
          )}
        </div>
      </div>

      <div className="detail-main">
        <h2>
          {game.name} {game.year && <span className="year">({game.year})</span>}
        </h2>
        {game.description && <p className="description">{game.description}</p>}
        <RulesChat game={game} />
      </div>
    </Modal>
  )
}
