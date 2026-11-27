import { Link } from 'react-router'
import EmptyState from '../components/EmptyState'

export default function NotFoundPage() {
  return (
    <EmptyState
      icon="signpost-split"
      title="Page not found"
      message="The page you are looking for does not exist."
      action={
        <Link to="/" className="btn btn-primary btn-sm">
          Back to dashboard
        </Link>
      }
    />
  )
}
