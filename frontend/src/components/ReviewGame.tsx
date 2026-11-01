import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, type Candidate, type Game, type NewGame, type Owner } from '../api'
import { parseCount, toText } from '../fields'
import { type OwnerChoice, OwnerPicker, toOwnerRef } from './OwnerPicker'
import { SlicePicker } from './SlicePicker'
import { DEFAULT_SLICE } from './Spine'

/** What the review form starts from: a lookup match, or just a typed name. */
export type ReviewStart = Candidate | { source: 'manual'; name: string }

interface Props {
  start: ReviewStart
  owners: Owner[]
  /** Set when adding an expansion: the game it expands, whose owner it takes. */
  base?: Game
  onBack: () => void
  onAdded: () => void
}

const SOURCE_NOTE = {
  catalog: 'Matched in the BoardGameGeek catalog; the cover and details come from an AI web search.',
  bgg: 'Found on BoardGameGeek; anything it lacks comes from an AI web search.',
  web: 'Not in the catalog, so everything here comes from an AI web search.',
  manual: 'Entered by hand.',
}

/** The fields the lookup can fill in. */
const FOUND_KEYS = ['min_players', 'max_players', 'playing_time', 'image_url'] as const
const DETAIL_KEYS = ['min_players', 'max_players', 'playing_time'] as const

/** The cover a lookup match came with, if any. */
function foundCover(start: ReviewStart): string {
  return start.source === 'manual' ? '' : (start.image_url ?? '')
}

function initialFields(start: ReviewStart, withCover: boolean) {
  const found = start.source === 'manual' ? null : start
  return {
    name: start.name,
    year: toText(found?.year ?? null),
    min_players: toText(found?.min_players ?? null),
    max_players: toText(found?.max_players ?? null),
    playing_time: toText(found?.playing_time ?? null),
    image_url: withCover ? foundCover(start) : '',
  }
}

/** Shows everything the lookup found so it can be checked and corrected before adding. */
export function ReviewGame({ start, owners, base, onBack, onAdded }: Props) {
  const queryClient = useQueryClient()
  // An expansion's cover is optional: it is only asked for once the user wants one.
  const [wantsCover, setWantsCover] = useState(!base)
  const [fields, setFields] = useState(() => initialFields(start, !base))
  const [imageBroken, setImageBroken] = useState(false)
  const [slice, setSlice] = useState(DEFAULT_SLICE)
  const [showLabel, setShowLabel] = useState(true)
  const [owner, setOwner] = useState<OwnerChoice>({
    id: owners.length === 0 ? 'new' : null,
    newName: '',
  })
  const set = (changes: Partial<typeof fields>) => setFields((current) => ({ ...current, ...changes }))

  // The lookup asks for, and fills in, only the fields that are still blank.
  const lookupKeys = wantsCover ? FOUND_KEYS : DETAIL_KEYS
  const bggId = start.source === 'manual' ? null : start.bgg_id
  const details = useMutation({
    mutationFn: () =>
      api.lookupDetails(
        fields.name.trim(),
        parseCount(fields.year) ?? null,
        bggId,
        base?.name,
        lookupKeys.filter((key) => !fields[key].trim()),
      ),
    onSuccess: (found) =>
      setFields((current) => {
        const filled = { ...current }
        for (const key of lookupKeys) {
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

  const missing = lookupKeys.some((key) => !fields[key].trim())
  const lookUpDetails = details.mutate
  const lookedUp = useRef(false)
  useEffect(() => {
    if (lookedUp.current) return
    lookedUp.current = true
    const initial = initialFields(start, !base)
    if ((base ? DETAIL_KEYS : FOUND_KEYS).some((key) => !initial[key])) lookUpDetails()
  }, [start, base, lookUpDetails])

  function addCover() {
    setWantsCover(true)
    set({ image_url: details.data?.image_url ?? foundCover(start) })
  }

  const name = fields.name.trim()
  const numbers = {
    year: parseCount(fields.year),
    min_players: parseCount(fields.min_players),
    max_players: parseCount(fields.max_players),
    playing_time: parseCount(fields.playing_time),
  }
  const ownerRef = base ? { parent_id: base.id } : toOwnerRef(owner)
  const baseOwner = base && owners.find((candidate) => candidate.id === base.owner_id)
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
      image_url: (wantsCover && fields.image_url.trim()) || null,
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
          {!wantsCover ? (
            <span className="no-cover">
              <button className="link" onClick={addCover}>
                Add a cover image
              </button>
              (optional)
            </span>
          ) : /* An expansion has no box of its own on the shelf, so no strip to pick. */
          base && fields.image_url.trim() && !imageBroken ? (
            <img
              className="cover"
              src={fields.image_url.trim()}
              alt={`${name} box cover`}
              referrerPolicy="no-referrer"
              onError={() => setImageBroken(true)}
            />
          ) : fields.image_url.trim() && !imageBroken ? (
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
          {base && (
            <p className="hint">
              Players and minutes are for {base.name} played with this expansion; the players
              widen {base.name}'s range on the shelf.
            </p>
          )}
          {details.isPending && (
            <p className="hint">
              Looking up the {wantsCover ? 'cover and details' : 'details'}…
            </p>
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

      {wantsCover && (
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
      )}

      {problem && <p className="notice error">{problem}</p>}
      {save.error && <p className="notice error">{save.error.message}</p>}

      <div className="add-footer">
        <button className="secondary" onClick={onBack}>
          Back
        </button>
        {base ? (
          <span className="hint">
            Expansion for {base.name}
            {baseOwner && ` (${baseOwner.name})`}
          </span>
        ) : (
          <OwnerPicker owners={owners} value={owner} onChange={setOwner} />
        )}
        <button
          className="primary"
          disabled={problem != null || !ownerRef || save.isPending || details.isPending}
          onClick={add}
        >
          {save.isPending ? 'Adding…' : base ? 'Add expansion' : 'Add to shelf'}
        </button>
      </div>
    </div>
  )
}
