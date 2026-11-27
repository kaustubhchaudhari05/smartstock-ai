interface ErrorStateProps {
  error: Error
  onRetry?: () => void
}

/** Shows the backend's error message with an optional retry button. */
export default function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div className="alert alert-danger d-flex flex-wrap align-items-center gap-2 mb-0" role="alert">
      <i className="bi bi-exclamation-octagon" aria-hidden="true" />
      <span className="me-auto">{error.message}</span>
      {onRetry && (
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}
