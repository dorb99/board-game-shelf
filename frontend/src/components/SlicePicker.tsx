import { type KeyboardEvent, type PointerEvent, useRef } from 'react'
import { sliceBackground, SPINE_ASPECT } from './Spine'

interface Props {
  imageUrl: string
  name: string
  /** How far down the cover the slice sits, 0 to 100. */
  position: number
  showLabel: boolean
  onPositionChange: (position: number) => void
  onShowLabelChange: (showLabel: boolean) => void
  onImageError?: () => void
}

const clamp = (value: number) => Math.min(100, Math.max(0, Math.round(value)))

/** Lets you pick which strip of the cover the box shows when it lies on the shelf. */
export function SlicePicker(props: Props) {
  const { imageUrl, name, position, showLabel, onPositionChange } = props
  const frame = useRef<HTMLDivElement>(null)

  /** Centre the band on the pointer. */
  function moveTo(event: PointerEvent) {
    const box = frame.current!.getBoundingClientRect()
    const band = box.width / SPINE_ASPECT
    const travel = box.height - band
    if (travel > 0) onPositionChange(clamp(((event.clientY - box.top - band / 2) / travel) * 100))
  }

  function onKeyDown(event: KeyboardEvent) {
    const step = { ArrowUp: -2, ArrowDown: 2, PageUp: -10, PageDown: 10 }[event.key]
    if (step === undefined) return
    event.preventDefault()
    onPositionChange(clamp(position + step))
  }

  return (
    <div className="slice-picker">
      <div
        ref={frame}
        className="slice-frame"
        role="slider"
        tabIndex={0}
        aria-label="Part of the cover shown on the shelf"
        aria-orientation="vertical"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={position}
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId)
          moveTo(event)
        }}
        onPointerMove={(event) => event.buttons === 1 && moveTo(event)}
      >
        <img
          src={imageUrl}
          alt={`${name} cover`}
          draggable={false}
          referrerPolicy="no-referrer"
          onError={props.onImageError}
        />
        <span
          className="slice-band"
          style={{ aspectRatio: SPINE_ASPECT, top: `${position}%`, translate: `0 -${position}%` }}
        />
      </div>

      <p className="hint">Drag the band to the part of the cover to show on the shelf.</p>
      <div
        className="spine slice-preview"
        style={{ aspectRatio: SPINE_ASPECT, ...sliceBackground(imageUrl, position) }}
      >
        {showLabel && <span className="spine-title">{name}</span>}
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={showLabel}
          onChange={(event) => props.onShowLabelChange(event.target.checked)}
        />
        Show the name label on the box
      </label>
    </div>
  )
}
