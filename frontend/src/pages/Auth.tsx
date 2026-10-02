import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../stores/auth'

const inputCls =
  'w-full rounded-xl border border-line bg-white px-4 py-2.5 text-[14px] text-ink outline-none transition-colors placeholder:text-faint focus:border-accent'

/** Shared login / register form — centered card (PLAN.md §7). */
export default function Auth({ mode }: { mode: 'login' | 'register' }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { login, register } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [nickname, setNickname] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'login') {
        await login(username, password)
        navigate('/')
      } else {
        await register({ username, password, email, nickname })
        await login(username, password)
        navigate('/')
      }
    } catch {
      setError(t('auth.error'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-sm pt-14">
      <h1 className="text-center text-[24px] font-semibold tracking-tight text-ink">
        {mode === 'login' ? t('auth.loginTitle') : t('auth.registerTitle')}
      </h1>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <input
          className={inputCls}
          placeholder={t('auth.username')}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        {mode === 'register' && (
          <>
            <input
              className={inputCls}
              placeholder={t('auth.email')}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <input
              className={inputCls}
              placeholder={t('auth.nickname')}
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
            />
          </>
        )}
        <input
          className={inputCls}
          placeholder={t('auth.password')}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />

        {error && <p className="text-center text-[13px] text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-full bg-accent py-2.5 text-[14px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {mode === 'login' ? t('auth.loginButton') : t('auth.registerButton')}
        </button>
      </form>

      <p className="mt-6 text-center text-[13px] text-muted">
        <Link to={mode === 'login' ? '/register' : '/login'} className="text-accent hover:underline">
          {mode === 'login' ? t('auth.toRegister') : t('auth.toLogin')}
        </Link>
      </p>
    </div>
  )
}
