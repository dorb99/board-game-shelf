import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { AddGameDialog } from '../components/AddGameDialog'
import { FilterBar } from '../components/FilterBar'
import { GameDetail } from '../components/GameDetail'
import { Shelf } from '../components/Shelf'
import { type Filters, matchesFilters, NO_FILTERS } from '../filters'

export function ShelvesPage() {
  const owners = useQuery({ queryKey: ['owners'], queryFn: api.owners })
  const games = useQuery({ queryKey: ['games'], queryFn: api.games })
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)

  const allOwners = owners.data ?? []
  const allGames = games.data ?? []
  const visible = allGames.filter((game) => matchesFilters(game, filters))
  const shelves = allOwners
    .map((owner) => ({ owner, games: visible.filter((game) => game.owner_id === owner.id) }))
    .filter((shelf) => shelf.games.length > 0)
  const selected = allGames.find((game) => game.id === selectedId)
  const error = owners.error ?? games.error

  return (
    <div className="page">
      <header className="page-header">
        <h1>🎲 Board Games Library</h1>
        <button className="primary" onClick={() => setAdding(true)}>
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
          <Shelf key={owner.id} owner={owner} games={games} onSelect={setSelectedId} />
        ))}
      </main>

      {adding && <AddGameDialog owners={allOwners} onClose={() => setAdding(false)} />}
      {selected && (
        <GameDetail
          key={selected.id}
          game={selected}
          owners={allOwners}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  )
}
