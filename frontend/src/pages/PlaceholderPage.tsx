import EmptyState from '../components/EmptyState'
import PageHeader from '../components/PageHeader'

interface PlaceholderPageProps {
  title: string
  subtitle: string
  icon: string
}

/** Temporary page for sections that are built in later Phase 7 steps. */
export default function PlaceholderPage({ title, subtitle, icon }: PlaceholderPageProps) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <div className="card">
        <div className="card-body">
          <EmptyState icon={icon} title="Coming soon" message="This page is built in a later step." />
        </div>
      </div>
    </>
  )
}
