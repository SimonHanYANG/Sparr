import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../stores/auth'

const inputCls =
  'w-full rounded-xl border border-line bg-white px-4 py-2.5 text-[14px] text-ink outline-none transition-colors placeholder:text-faint focus:border-accent'

/** Password policy mirrors backend core/validators.SparrPasswordValidator. */
function passwordChecks(pw: string) {
  return {
    length: pw.length >= 8 && pw.length <= 64,
    upper: /[A-Z]/.test(pw),
    lower: /[a-z]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw),
  }
}

function extractFieldErrors(err: unknown): Record<string, string> {
  if (err instanceof ApiError) {
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(err.detail)) {
      const msg = Array.isArray(v) ? v[0] : v
      if (typeof msg === 'string') out[k] = msg
    }
    return out
  }
  return {}
}

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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  const checks = useMemo(() => passwordChecks(password), [password])
  const passwordOk = Object.values(checks).every(Boolean)
  const registerReady = username.trim().length > 0 && passwordOk && !busy

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setFieldErrors({})
    if (mode === 'register' && !passwordOk) return
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
    } catch (err) {
      const fields = extractFieldErrors(err)
      if (fields.username && /exists|已存在/.test(fields.username)) {
        setFieldErrors({ username: t('auth.usernameTaken') })
      } else if (Object.keys(fields).length > 0) {
        setFieldErrors(fields)
      } else if (mode === 'login' && err instanceof ApiError && err.status === 401) {
        setError(t('auth.invalidCredentials'))
      } else {
        setError(t('auth.error'))
      }
    } finally {
      setBusy(false)
    }
  }

  const rules: Array<[keyof typeof checks, string]> = [
    ['length', t('auth.ruleLength')],
    ['upper', t('auth.ruleUpper')],
    ['lower', t('auth.ruleLower')],
    ['special', t('auth.ruleSpecial')],
  ]

  return (
    <div className="mx-auto max-w-sm pt-14">
      <h1 className="text-center text-[24px] font-semibold tracking-tight text-ink">
        {mode === 'login' ? t('auth.loginTitle') : t('auth.registerTitle')}
      </h1>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <div>
          <input
            className={inputCls}
            placeholder={t('auth.username')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          {fieldErrors.username && (
            <p className="mt-1.5 text-[12.5px] text-red-600">{fieldErrors.username}</p>
          )}
        </div>

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

        <div>
          <input
            className={inputCls}
            placeholder={t('auth.password')}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            maxLength={64}
          />
          {fieldErrors.password && (
            <p className="mt-1.5 text-[12.5px] text-red-600">{fieldErrors.password}</p>
          )}
          {mode === 'register' && (
            <div className="mt-2.5 rounded-xl bg-surface px-4 py-3">
              <p className="text-[12px] font-medium text-muted">{t('auth.passwordRulesTitle')}</p>
              <ul className="mt-1.5 grid grid-cols-1 gap-1 sm:grid-cols-2">
                {rules.map(([key, label]) => (
                  <li
                    key={key}
                    className={`flex items-center gap-1.5 text-[12px] ${
                      checks[key] ? 'text-accent' : 'text-faint'
                    }`}
                  >
                    <span aria-hidden>{checks[key] ? '✓' : '○'}</span>
                    {label}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {error && <p className="text-center text-[13px] text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={mode === 'register' ? !registerReady : busy}
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
