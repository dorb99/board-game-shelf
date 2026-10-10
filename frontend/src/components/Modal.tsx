import { type ReactNode, useEffect, useRef } from 'react'

interface Props {
  label: string
  className?: string
  onClose: () => void
  children: ReactNode
}

export function Modal({ label, className, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={ref}
      className={`modal ${className ?? ''}`}
      aria-label={label}
      onClose={onClose}
      // A click that lands on the dialog itself is a click on the backdrop.
      onMouseDown={(event) => event.target === ref.current && onClose()}
    >
      <button className="modal-close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      {children}
    </dialog>
  )
}
