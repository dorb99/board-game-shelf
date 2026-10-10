import type { ReactNode } from 'react'
import type { Owner } from '../api'
import { type Filters, LENGTHS, MAX_PLAYERS_OPTION, NO_FILTERS } from '../filters'

interface Props {
  owners: Owner[]
  filters: Filters
  onChange: (filters: Filters) => void
}

const PLAYER_OPTIONS = Array.from({ length: MAX_PLAYERS_OPTION }, (_, i) => i + 1)

function Chip(props: { active: boolean; onClick: () => void; title?: string; children: ReactNode }) {
  return (
    <button
      className={props.active ? 'chip active' : 'chip'}
      aria-pressed={props.active}
      title={props.title}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  )
}

export function FilterBar({ owners, filters, onChange }: Props) {
  const set = (changes: Partial<Filters>) => onChange({ ...filters, ...changes })
  const anyActive =
    filters.ownerId != null || filters.players != null || filters.length != null

  return (
    <section className="filter-bar" aria-label="Filters">
      <div className="filter-group">
        <span className="filter-label">Shelf</span>
        <Chip active={filters.ownerId == null} onClick={() => set({ ownerId: null })}>
          All
        </Chip>
        {owners.map((owner) => (
          <Chip
            key={owner.id}
            active={filters.ownerId === owner.id}
            onClick={() => set({ ownerId: owner.id })}
          >
            {owner.name}
          </Chip>
        ))}
      </div>

      <div className="filter-group">
        <span className="filter-label">Players</span>
        <Chip active={filters.players == null} onClick={() => set({ players: null })}>
          Any
        </Chip>
        {PLAYER_OPTIONS.map((count) => (
          <Chip
            key={count}
            active={filters.players === count}
            onClick={() => set({ players: count })}
          >
            {count === MAX_PLAYERS_OPTION ? `${count}+` : count}
          </Chip>
        ))}
      </div>

      <div className="filter-group">
        <span className="filter-label">Length</span>
        <Chip active={filters.length == null} onClick={() => set({ length: null })}>
          Any
        </Chip>
        {LENGTHS.map(({ value, label, hint }) => (
          <Chip
            key={value}
            active={filters.length === value}
            title={hint}
            onClick={() => set({ length: value })}
          >
            {label} <small>{hint}</small>
          </Chip>
        ))}
      </div>

      {anyActive && (
        <button className="link" onClick={() => onChange(NO_FILTERS)}>
          Clear filters
        </button>
      )}
    </section>
  )
}
