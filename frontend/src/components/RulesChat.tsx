import { type FormEvent, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { type ChatMessage, type Game, type Source, streamChat } from '../api'

interface Entry extends ChatMessage {
  sources?: Source[]
  error?: string
}

const STARTERS = ['How do we set up?', 'What happens on a turn?', 'How does the game end?']

export function RulesChat({ game }: { game: Game }) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const log = useRef<HTMLDivElement>(null)

  useEffect(() => () => abort.current?.abort(), [])
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight })
  }, [entries])

  /** Apply a change to the answer currently being streamed (the last entry). */
  function updateAnswer(change: (answer: Entry) => Entry) {
    setEntries((current) => [...current.slice(0, -1), change(current[current.length - 1])])
  }

  async function ask(question: string) {
    const text = question.trim()
    if (!text || streaming) return
    const history: ChatMessage[] = entries
      .filter((entry) => entry.text)
      .map(({ role, text }) => ({ role, text }))
    const messages: ChatMessage[] = [...history, { role: 'user', text }]

    setEntries([...entries, { role: 'user', text }, { role: 'model', text: '' }])
    setDraft('')
    setStreaming(true)
    const controller = new AbortController()
    abort.current = controller
    try {
      await streamChat(
        game.id,
        messages,
        (event) => {
          if (event.type === 'text') {
            updateAnswer((answer) => ({ ...answer, text: answer.text + event.text }))
          } else if (event.type === 'sources') {
            updateAnswer((answer) => ({ ...answer, sources: event.sources }))
          } else if (event.type === 'error') {
            updateAnswer((answer) => ({ ...answer, error: event.message }))
          }
        },
        controller.signal,
      )
    } catch (error) {
      if (controller.signal.aborted) return
      const message = error instanceof Error ? error.message : 'Something went wrong.'
      updateAnswer((answer) => ({ ...answer, error: message }))
    }
    setStreaming(false)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    void ask(draft)
  }

  return (
    <section className="chat" aria-label="Rules assistant">
      <h3>Rules assistant</h3>
      <div className="chat-log" ref={log}>
        {entries.length === 0 && (
          <div className="chat-empty">
            <p>Ask anything about the rules of {game.name}.</p>
            {STARTERS.map((starter) => (
              <button key={starter} className="chip" onClick={() => void ask(starter)}>
                {starter}
              </button>
            ))}
          </div>
        )}
        {entries.map((entry, index) => (
          <div key={index} className={`bubble ${entry.role}`}>
            {entry.role === 'user' ? entry.text : <Markdown>{entry.text}</Markdown>}
            {entry.role === 'model' && !entry.text && !entry.error && (
              <span className="thinking">Looking up the rules…</span>
            )}
            {entry.error && <p className="notice error">{entry.error}</p>}
            {entry.sources && (
              <p className="sources">
                Sources:{' '}
                {entry.sources.map((source) => (
                  <a key={source.uri} href={source.uri} target="_blank" rel="noreferrer">
                    {source.title}
                  </a>
                ))}
              </p>
            )}
          </div>
        ))}
      </div>
      <form className="chat-input" onSubmit={submit}>
        <input
          aria-label="Your question"
          placeholder="Ask a rules question…"
          maxLength={2000}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button className="primary" disabled={!draft.trim() || streaming}>
          Ask
        </button>
      </form>
    </section>
  )
}
