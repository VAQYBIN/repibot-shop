import { translate } from '@repibot/core'
import { createRootRoute, Link, Outlet } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { useAuthState } from '../auth'
import { AuthFallback } from '../auth-fallback'
import { PurchaseNotice } from '../purchase-notice'

function Navigation() {
  const language = useLanguage()

  return (
    <nav className="mx-auto mb-4 flex max-w-md flex-wrap gap-x-4 gap-y-2 text-sm">
      <Link to="/" className="text-text-accent">
        {translate(language, 'miniapp.nav.home')}
      </Link>
      <Link to="/subscription" className="text-text-accent">
        {translate(language, 'subscription.title')}
      </Link>
      <Link to="/payments" className="text-text-accent">
        {translate(language, 'payment.title')}
      </Link>
      <Link to="/devices" className="text-text-accent">
        {translate(language, 'devices.title')}
      </Link>
      <Link to="/profile" className="text-text-accent">
        {translate(language, 'account.title')}
      </Link>
      <Link to="/support" className="text-text-accent">
        {translate(language, 'support.title')}
      </Link>
    </nav>
  )
}

function Layout() {
  const state = useAuthState((store) => store.state)

  if (state !== 'ready') {
    return (
      <div className="min-h-dvh bg-bg p-4 text-text">
        <AuthFallback state={state} />
      </div>
    )
  }

  return (
    <div className="min-h-dvh bg-bg p-4 text-text">
      <Navigation />
      <Outlet />
      {/* Не на экране оплаты: человек возвращается из браузера на ту вкладку,
          которую выберет сам, а новость об оплате нужна на любой. */}
      <PurchaseNotice />
    </div>
  )
}

export const rootRoute = createRootRoute({ component: Layout })
