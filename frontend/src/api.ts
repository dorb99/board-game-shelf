export interface Owner {
  id: number
  name: string
}

export interface GameDetails {
  min_players: number | null
  max_players: number | null
  playing_time: number | null
}

export interface Game extends GameDetails {
  id: number
  name: string
  owner_id: number
  bgg_id: number | null
  year: number | null
  image_url: string | null
  /** Which strip of the cover shows on the shelf: 0 = top, 100 = bottom, null = middle. */
  spine_position: number | null
  spine_label: boolean
}

export interface Candidate extends GameDetails {
  source: 'catalog' | 'web'
  bgg_id: number | null
  name: string
  year: number | null
  is_expansion: boolean
  thumbnail_url: string | null
  image_url: string | null
}

/** What the AI found online for one game; unknown values are null. */
export interface FoundDetails extends GameDetails {
  image_url: string | null
  /** False when web search was refused and the AI answered from memory. */
  searched: boolean
}

export interface LookupResult {
  candidates: Candidate[]
  warnings: string[]
}

/** Either an existing owner or the name of one to create. */
export type OwnerRef = { owner_id: number } | { owner_name: string }

export type NewGame = OwnerRef &
  Partial<GameDetails> & {
    name: string
    bgg_id?: number | null
    year?: number | null
    image_url?: string | null
    spine_position?: number | null
    spine_label?: boolean
  }

export type GameChanges = Partial<GameDetails> &
  Partial<{
    owner_id: number
    owner_name: string
    spine_position: number | null
    spine_label: boolean
  }>

export interface Source {
  uri: string
  title: string
}

export interface ChatMessage {
  role: 'user' | 'model'
  text: string
}

export type ChatEvent =
  | { type: 'text'; text: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'notice'; message: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

async function errorMessage(response: Response): Promise<string> {
  try {
    const { detail } = await response.json()
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  } catch {
    // not a JSON error body
  }
  return `Request failed (${response.status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.status === 204 ? (undefined as T) : response.json()
}

export const api = {
  owners: () => request<Owner[]>('/api/owners'),
  games: () => request<Game[]>('/api/games'),
  lookup: (query: string) =>
    request<LookupResult>(`/api/lookup?q=${encodeURIComponent(query)}`),
  lookupDetails: (name: string, year: number | null, bggId: number | null) => {
    const params = new URLSearchParams({ name })
    if (year) params.set('year', String(year))
    if (bggId) params.set('bgg_id', String(bggId))
    return request<FoundDetails>(`/api/lookup/details?${params}`)
  },
  addGame: (game: NewGame) =>
    request<Game>('/api/games', { method: 'POST', body: JSON.stringify(game) }),
  updateGame: (id: number, changes: GameChanges) =>
    request<Game>(`/api/games/${id}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  deleteGame: (id: number) => request<void>(`/api/games/${id}`, { method: 'DELETE' }),
}

/** Ask the rules assistant; events arrive as the answer streams. */
export async function streamChat(
  gameId: number,
  messages: ChatMessage[],
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/games/${gameId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  })
  if (!response.ok || !response.body) throw new Error(await errorMessage(response))

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += value
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const event of events) {
      if (event.startsWith('data: ')) onEvent(JSON.parse(event.slice(6)))
    }
  }
}
