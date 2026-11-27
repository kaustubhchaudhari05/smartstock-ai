import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import ApiStatus from '../components/ApiStatus'
import { NAV_ITEMS } from './navigation'

/** Application shell: sidebar navigation, top bar and the routed page. */
export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the mobile menu on Escape (links close it when clicked).
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="app-shell">
      <aside
        id="app-sidebar"
        className={`app-sidebar border-end bg-body-tertiary ${menuOpen ? 'is-open' : ''}`}
      >
        <div className="app-brand d-flex align-items-center gap-2 px-3 border-bottom">
          <i className="bi bi-box-seam-fill text-primary fs-4" aria-hidden="true" />
          <span className="fw-semibold">SmartStock AI</span>
        </div>
        <nav className="nav nav-pills flex-column gap-1 p-2" aria-label="Main">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `nav-link d-flex align-items-center gap-2 ${isActive ? 'active' : 'link-body-emphasis'}`
              }
            >
              <i className={`bi bi-${item.icon}`} aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {menuOpen && (
        <div className="app-backdrop d-lg-none" onClick={() => setMenuOpen(false)} aria-hidden="true" />
      )}

      <div className="app-main">
        <header className="app-topbar d-flex align-items-center gap-2 px-3 border-bottom bg-body">
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm d-lg-none"
            onClick={() => setMenuOpen((open) => !open)}
            aria-controls="app-sidebar"
            aria-expanded={menuOpen}
            aria-label="Toggle navigation"
          >
            <i className="bi bi-list" aria-hidden="true" />
          </button>
          <span className="fw-semibold d-lg-none">SmartStock AI</span>
          <div className="ms-auto">
            <ApiStatus />
          </div>
        </header>
        <main className="app-content p-3 p-md-4">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
