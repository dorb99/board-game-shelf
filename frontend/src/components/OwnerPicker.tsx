import type { Owner, OwnerRef } from '../api'

/** `id` is an owner id, or 'new' when the name in `newName` should be created. */
export interface OwnerChoice {
  id: number | 'new' | null
  newName: string
}

export function toOwnerRef(choice: OwnerChoice): OwnerRef | null {
  if (typeof choice.id === 'number') return { owner_id: choice.id }
  const name = choice.newName.trim()
  return choice.id === 'new' && name ? { owner_name: name } : null
}

interface Props {
  owners: Owner[]
  value: OwnerChoice
  onChange: (value: OwnerChoice) => void
}

export function OwnerPicker({ owners, value, onChange }: Props) {
  return (
    <div className="owner-picker">
      <select
        aria-label="Owner"
        value={value.id ?? ''}
        onChange={(event) => {
          const picked = event.target.value
          onChange({ ...value, id: picked === 'new' ? 'new' : picked ? Number(picked) : null })
        }}
      >
        <option value="" disabled>
          Who owns it?
        </option>
        {owners.map((owner) => (
          <option key={owner.id} value={owner.id}>
            {owner.name}
          </option>
        ))}
        <option value="new">+ New owner…</option>
      </select>
      {value.id === 'new' && (
        <input
          autoFocus
          aria-label="New owner name"
          placeholder="Owner name"
          maxLength={60}
          value={value.newName}
          onChange={(event) => onChange({ ...value, newName: event.target.value })}
        />
      )}
    </div>
  )
}
