import { useEffect, useId, useRef, type ReactNode } from 'react'

interface ModalProps {
  title: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'lg' | 'xl'
  /** Disable closing (Escape / backdrop / X) while something is being saved. */
  busy?: boolean
}

/**
 * Bootstrap modal markup controlled by React (no Bootstrap JS). Render it to open it;
 * unmount it to close it. Closes on Escape and backdrop click; focus moves into the dialog.
 */
export default function Modal({ title, onClose, children, footer, size, busy = false }: ModalProps) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()
    document.body.classList.add('modal-open')
    return () => {
      document.body.classList.remove('modal-open')
      previous?.focus()
    }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, busy])

  return (
    <>
      <div
        className="modal d-block"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={dialogRef}
        onMouseDown={(e) => {
          if (e.target === e.currentTarget && !busy) onClose()
        }}
      >
        <div className={`modal-dialog modal-dialog-scrollable ${size ? `modal-${size}` : ''}`}>
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5" id={titleId}>
                {title}
              </h2>
              <button type="button" className="btn-close" aria-label="Close" onClick={onClose} disabled={busy} />
            </div>
            <div className="modal-body">{children}</div>
            {footer && <div className="modal-footer">{footer}</div>}
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  )
}
