import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, type Candidate, type NewGame, type Owner } from '../api'
import { parseCount, toText } from '../fields'
import { type OwnerChoice, OwnerPicker, toOwnerRef } from './OwnerPicker'
import { SlicePicker } from './SlicePicker'
import { DEFAULT_SLICE } from './Spine'

/** What the review form starts from: a lookup match, or just a typed name. */
export type ReviewStart = Candidate | { source: 'manual'; name: string }

interface Props {
  start: ReviewStart
  owners: Owner[]
  onBack: () => void
  onAdded: () => void
}

const SOURCE_NOTE = {
  catalog: 'Matched in the BoardGameGeek catalog; the cover and details come from an AI web search.',
  web: 'Not in the catalog, so everything here comes from an AI web search.',
  manual: 'Entered by hand.',
}

/** The fields the AI lookup can fill in. */
const FOUND_KEYS = ['min_players', 'max_players', 'playing_time', 'image_url'] as const

function initialFields(start: ReviewStart) {
  const found = start.source === 'manual' ? null : start
  return {
    name: start.name,
    year: toText(found?.year ?? null),
    min_players: toText(found?.min_players ?? null),
    max_players: toText(found?.max_players ?? null),
    playing_time: toText(found?.playing_time ?? null),
    image_url: found?.image_url ?? '',
  }
}

/** Shows everything the lookup found so it can be checked and corrected before adding. */
export function ReviewGame({ start, owners, onBack, onAdded }: Props) {
  const queryClient = useQueryClient()
  const [fields, setFields] = useState(() => initialFields(start))
  const [imageBroken, setImageBroken] = useState(false)
  const [slice, setSlice] = useState(DEFAULT_SLICE)
  const [showLabel, setShowLabel] = useState(true)
  const [owner, setOwner] = useState<OwnerChoice>({
    id: owners.length === 0 ? 'new' : null,
    newName: '',
  })
  const set = (changes: Partial<typeof fields>) => setFields((current) => ({ ...current, ...changes }))

  // The AI lookup fills in only the fields that are still blank.
  const bggId = start.source === 'catalog' ? start.bgg_id : null
  const details = useMutation({
    mutationFn: () =>
      api.lookupDetails(fields.name.trim(), parseCount(fields.year) ?? null, bggId),
    onSuccess: (found) =>
      setFields((current) => {
        const filled = { ...current }
        for (const key of FOUND_KEYS) {
          if (!filled[key].trim()) filled[key] = String(found[key] ?? '')
        }
        return filled
      }),
  })
  const save = useMutation({
    mutationFn: api.addGame,
    onSuccess: async () => {
      await queryClient.invalidateQueries()
      onAdded()
    },
  })

  const missing = FOUND_KEYS.some((key) => !fields[key].trim())
  const lookUpDetails = details.mutate
  const lookedUp = useRef(false)
  useEffect(() => {
    if (lookedUp.current) return
    lookedUp.current = true
    if (FOUND_KEYS.some((key) => !initialFields(start)[key])) lookUpDetails()
  }, [start, lookUpDetails])

  const name = fields.name.trim()
  const numbers = {
    year: parseCount(fields.year),
    min_players: parseCount(fields.min_players),
    max_players: parseCount(fields.max_players),
    playing_time: parseCount(fields.playing_time),
  }
  const ownerRef = toOwnerRef(owner)
  const rangeInverted =
    numbers.min_players != null &&
    numbers.max_players != null &&
    numbers.min_players > numbers.max_players
  const problem = !name
    ? 'Enter the game name.'
    : Object.values(numbers).includes(undefined)
      ? 'Year, players and play time must be whole numbers.'
      : rangeInverted
        ? 'Minimum players cannot be more than maximum players.'
        : null

  function add() {
    if (problem || !ownerRef) return
    const game: NewGame = {
      ...ownerRef,
      ...(numbers as Record<keyof typeof numbers, number | null>),
      name,
      bgg_id: bggId,
      image_url: fields.image_url.trim() || null,
      spine_position: slice,
      spine_label: showLabel,
    }
    save.mutate(game)
  }

  return (
    <div className="review">
      <p className="hint">{SOURCE_NOTE[start.source]} Check the details, fix anything wrong, then add it.</p>

      <div className="review-body">
        <div className="review-cover">
          {fields.image_url.trim() && !imageBroken ? (
            <SlicePicker
              imageUrl={fields.image_url.trim()}
              name={name || 'Game name'}
              position={slice}
              showLabel={showLabel}
              onPositionChange={setSlice}
              onShowLabelChange={setShowLabel}
              onImageError={() => setImageBroken(true)}
            />
          ) : (
            <span className="no-cover">
              {fields.image_url.trim() ? 'This image link does not load' : 'No cover image'}
            </span>
          )}
        </div>

        <div className="review-fields">
          <label>
            Name
            <input
              maxLength={200}
              value={fields.name}
              onChange={(event) => set({ name: event.target.value })}
            />
          </label>
          <div className="field-row">
            <label>
              Year
              <input
                type="number"
                value={fields.year}
                onChange={(event) => set({ year: event.target.value })}
              />
            </label>
            <label>
              Min players
              <input
                type="number"
                min={1}
                value={fields.min_players}
                onChange={(event) => set({ min_players: event.target.value })}
              />
            </label>
            <label>
              Max players
              <input
                type="number"
                min={1}
                value={fields.max_players}
                onChange={(event) => set({ max_players: event.target.value })}
              />
            </label>
            <label>
              Minutes
              <input
                type="number"
                min={1}
                value={fields.playing_time}
                onChange={(event) => set({ playing_time: event.target.value })}
              />
            </label>
          </div>
          {details.isPending && (
            <p className="hint">Searching the web for the cover and details…</p>
          )}
          {details.error && <p className="hint">{details.error.message}</p>}
          {details.data?.searched === false && (
            <p className="hint warning">
              Web search is not available on the AI key, so these details come from the
              AI's memory and no cover was found. Check them and paste a cover link.
            </p>
          )}
          {!details.isPending && missing && (
            <p className="hint">
              Some fields are still blank.{' '}
              <button className="link" disabled={!name} onClick={() => lookUpDetails()}>
                Search again
              </button>{' '}
              or fill them in yourself.
            </p>
          )}
        </div>
      </div>

      <label>
        Cover image link
        <input
          maxLength={2000}
          placeholder="https://…"
          value={fields.image_url}
          onChange={(event) => {
            setImageBroken(false)
            set({ image_url: event.target.value })
          }}
        />
      </label>

      {problem && <p className="notice error">{problem}</p>}
      {save.error && <p className="notice error">{save.error.message}</p>}

      <div className="add-footer">
        <button className="secondary" onClick={onBack}>
          Back
        </button>
        <OwnerPicker owners={owners} value={owner} onChange={setOwner} />
        <button
          className="primary"
          disabled={problem != null || !ownerRef || save.isPending || details.isPending}
          onClick={add}
        >
          {save.isPending ? 'Adding…' : 'Add to shelf'}
        </button>
      </div>
    </div>
  )
}
