import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Game } from '../api'
import { AddGameDialog } from '../components/AddGameDialog'
import { FilterBar } from '../components/FilterBar'
import { GameDetail } from '../components/GameDetail'
import { Shelf } from '../components/Shelf'
import { type Filters, matchesFilters, NO_FILTERS, withExpansions } from '../filters'

export function ShelvesPage() {
  const owners = useQuery({ queryKey: ['owners'], queryFn: api.owners })
  const games = useQuery({ queryKey: ['games'], queryFn: api.games })
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // What the add dialog is adding: a game, or an expansion for `base`.
  const [adding, setAdding] = useState<{ base?: Game } | null>(null)

  const allOwners = owners.data ?? []
  const allGames = games.data ?? []
  const expansionsOf = (game: Game) => allGames.filter((other) => other.parent_id === game.id)
  // Expansions live inside their base game's box, and widen its player range.
  const baseGames = allGames
    .filter((game) => game.parent_id == null)
    .map((game) => withExpansions(game, expansionsOf(game)))
  const expansionCounts = new Map(baseGames.map((game) => [game.id, expansionsOf(game).length]))
  const visible = baseGames.filter((game) => matchesFilters(game, filters))
  const shelves = allOwners
    .map((owner) => ({ owner, games: visible.filter((game) => game.owner_id === owner.id) }))
    .filter((shelf) => shelf.games.length > 0)
  const selected = allGames.find((game) => game.id === selectedId)
  const error = owners.error ?? games.error

  return (
    <div className="page">
      <header className="page-header">
        <h1>🎲 Board Games Library</h1>
        <button className="primary" onClick={() => setAdding({})}>
          + Add game
        </button>
      </header>

      {allGames.length > 0 && (
        <FilterBar owners={allOwners} filters={filters} onChange={setFilters} />
      )}

      <main>
        {error && <p className="notice error">Could not load the library: {error.message}</p>}
        {games.isPending && <p className="notice">Loading shelves…</p>}
        {games.isSuccess && allGames.length === 0 && (
          <p className="notice">The shelves are empty. Add your first game to get started.</p>
        )}
        {allGames.length > 0 && shelves.length === 0 && (
          <p className="notice">
            No games match these filters.{' '}
            <button className="link" onClick={() => setFilters(NO_FILTERS)}>
              Clear filters
            </button>
          </p>
        )}
        {shelves.map(({ owner, games }) => (
          <Shelf
            key={owner.id}
            owner={owner}
            games={games}
            expansionCounts={expansionCounts}
            onSelect={setSelectedId}
          />
        ))}
      </main>

      {adding && (
        <AddGameDialog owners={allOwners} base={adding.base} onClose={() => setAdding(null)} />
      )}
      {selected && (
        <GameDetail
          key={selected.id}
          game={selected}
          owners={allOwners}
          games={allGames}
          onSelect={setSelectedId}
          onAddExpansion={() => {
            setSelectedId(null)
            setAdding({ base: selected })
          }}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  )
}
