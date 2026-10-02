import { useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useAuth } from '../stores/auth'
import LanguageSwitcher from './LanguageSwitcher'

const navItems = [
  { to: '/', key: 'home', end: true },
  { to: '/resumes', key: 'resumes' },
  { to: '/jobs', key: 'jobs' },
  { to: '/applications', key: 'applications' },
  { to: '/settings', key: 'settings' },
] as const

/** Minimal app shell: slim top bar, content, quiet footer (PLAN.md §7). */
export default function Layout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { loggedIn, user, fetchMe, logout } = useAuth()

  useEffect(() => {
    void fetchMe()
  }, [fetchMe])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="text-[17px] font-semibold tracking-tight text-ink">
            Sparr
          </NavLink>

          <nav className="hidden items-center gap-1 sm:flex">
            {navItems.map(({ to, key, ...rest }) => (
              <NavLink
                key={key}
                to={to}
                {...rest}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1.5 text-[13.5px] transition-colors ${
                    isActive ? 'bg-surface font-medium text-ink' : 'text-muted hover:text-ink'
                  }`
                }
              >
                {t(`nav.${key}`)}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <LanguageSwitcher />
            {loggedIn ? (
              <div className="flex items-center gap-2">
                <span className="hidden text-[13px] text-muted md:inline">
                  {user?.nickname || user?.username}
                </span>
                <button
                  onClick={() => {
                    logout()
                    navigate('/')
                  }}
                  className="text-[13px] text-muted transition-colors hover:text-ink"
                >
                  {t('nav.logout')}
                </button>
              </div>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="rounded-full bg-ink px-4 py-1.5 text-[13px] text-white transition-colors hover:bg-black"
              >
                {t('nav.login')}
              </button>
            )}
          </div>
        </div>

        {/* mobile bottom-style nav: compact row under the bar */}
        <nav className="flex items-center justify-around border-t border-line py-1.5 sm:hidden">
          {navItems.map(({ to, key, ...rest }) => (
            <NavLink
              key={key}
              to={to}
              {...rest}
              className={({ isActive }) =>
                `px-2 py-1 text-[12px] ${isActive ? 'font-medium text-ink' : 'text-muted'}`
              }
            >
              {t(`nav.${key}`)}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6">
        <div className="animate-fade">
          <Outlet />
        </div>
      </main>

      <footer className="border-t border-line py-6">
        <p className="text-center text-[12px] text-faint">Sparr — {t('home.title')}</p>
      </footer>
    </div>
  )
}
