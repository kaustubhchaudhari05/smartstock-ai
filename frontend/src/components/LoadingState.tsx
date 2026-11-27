export default function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="d-flex align-items-center justify-content-center gap-2 text-body-secondary py-4" role="status">
      <span className="spinner-border spinner-border-sm" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}
