import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { api, type Candidate, type Owner } from '../api'
import { playersLabel, timeLabel } from '../filters'
import { Modal } from './Modal'
import { ReviewGame, type ReviewStart } from './ReviewGame'

interface Props {
  owners: Owner[]
  onClose: () => void
}

/** Two steps: search for the game, then review what was found before adding it. */
export function AddGameDialog({ owners, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [reviewing, setReviewing] = useState<ReviewStart | null>(null)
  const lookup = useMutation({ mutationFn: api.lookup })
  const candidates = lookup.data?.candidates ?? []

  function search(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) lookup.mutate(query.trim())
  }

  if (reviewing) {
    return (
      <Modal label="Review game" className="add-dialog" onClose={onClose}>
        <h2>Review before adding</h2>
        <ReviewGame
          start={reviewing}
          owners={owners}
          onBack={() => setReviewing(null)}
          onAdded={onClose}
        />
      </Modal>
    )
  }

  return (
    <Modal label="Add a game" className="add-dialog" onClose={onClose}>
      <h2>Add a game</h2>

      <form className="search-row" onSubmit={search}>
        <input
          autoFocus
          aria-label="Game name"
          placeholder="Game name, e.g. Wingspan"
          maxLength={120}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="primary" disabled={!query.trim() || lookup.isPending}>
          {lookup.isPending ? 'Searching…' : 'Search'}
        </button>
      </form>

      {lookup.error && <p className="notice error">{lookup.error.message}</p>}
      {lookup.data?.warnings.map((warning) => (
        <p key={warning} className="hint">
          {warning}
        </p>
      ))}
      {lookup.isSuccess && candidates.length === 0 && (
        <p className="notice">No matches found. You can add it by hand below.</p>
      )}

      {candidates.length > 0 && (
        <>
          <p className="hint">Pick the right match to review its details.</p>
          <ul className="candidates">
            {candidates.map((candidate, index) => (
              <li key={`${candidate.source}-${candidate.bgg_id ?? index}`}>
                <CandidateRow candidate={candidate} onSelect={() => setReviewing(candidate)} />
              </li>
            ))}
          </ul>
        </>
      )}

      {(lookup.isSuccess || lookup.isError) && (
        <button
          className="link"
          onClick={() => setReviewing({ source: 'manual', name: query.trim() })}
        >
          Not here? Add it by hand
        </button>
      )}
    </Modal>
  )
}

function CandidateRow({ candidate, onSelect }: { candidate: Candidate; onSelect: () => void }) {
  const facts = [
    candidate.year,
    candidate.is_expansion && 'Expansion',
    playersLabel(candidate),
    timeLabel(candidate),
  ].filter(Boolean)
  return (
    <button className="candidate" onClick={onSelect}>
      {candidate.thumbnail_url && (
        <img src={candidate.thumbnail_url} alt="" referrerPolicy="no-referrer" />
      )}
      <span className="candidate-text">
        <strong>{candidate.name}</strong>
        <span>{facts.join(' · ')}</span>
      </span>
    </button>
  )
}
