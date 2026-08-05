import { translate } from '@repibot/core'
import { createRootRoute, Link, Outlet } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { useAuthState } from '../auth'

function Navigation() {
  const language = useLanguage()

  return (
    <nav className="mx-auto mb-4 flex max-w-md gap-4 text-sm">
      <Link to="/" className="text-text-accent">
        {translate(language, 'miniapp.nav.home')}
      </Link>
      <Link to="/profile" className="text-text-accent">
        {translate(language, 'account.title')}
      </Link>
    </nav>
  )
}

function Layout() {
  const state = useAuthState((store) => store.state)

  return (
    <div className="min-h-dvh bg-bg p-4 text-text">
      {/* Навигация появляется только после входа: до него единственный
          осмысленный экран — сообщение о том, что делать дальше. */}
      {state === 'ready' && <Navigation />}
      <Outlet />
    </div>
  )
}

export const rootRoute = createRootRoute({ component: Layout })
