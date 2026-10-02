import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiFetch } from '../api/client'

interface Credential {
  id: number
  provider: 'mineru' | 'deepseek' | 'mimo'
  provider_label: string
  api_key_masked: string
  model_name: string
  base_url: string
  is_valid: boolean | null
  last_validated_at: string | null
}

const inputCls =
  'w-full rounded-xl border border-line bg-white px-3.5 py-2 text-[13px] text-ink outline-none focus:border-accent'

interface ProviderInfo {
  models: string[]
  default_model: string
  base_url: string
}

/** Which LLM powers AI features — user-selectable (provider + model). */
function PreferenceCard({
  registry,
}: {
  registry: Record<string, ProviderInfo>
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data: pref } = useQuery({
    queryKey: ['preferences'],
    queryFn: () => apiFetch<{ llm_provider: string; llm_model: string }>('/api/auth/preferences'),
  })

  const save = async (provider: string, model: string) => {
    await apiFetch('/api/auth/preferences', {
      method: 'PUT',
      body: JSON.stringify({ llm_provider: provider, llm_model: model }),
    })
    queryClient.invalidateQueries({ queryKey: ['preferences'] })
  }

  const models = pref?.llm_provider ? registry[pref.llm_provider]?.models ?? [] : []

  return (
    <div className="rounded-2xl border border-line px-6 py-5">
      <h3 className="text-[15px] font-medium text-ink">{t('settings.prefTitle')}</h3>
      <p className="mt-1 text-[12px] text-faint">{t('settings.prefHint')}</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <select
          className={inputCls}
          value={pref?.llm_provider ?? ''}
          onChange={(e) => save(e.target.value, '')}
        >
          <option value="">{t('settings.prefAuto')}</option>
          {Object.keys(registry).map((p) => (
            <option key={p} value={p}>
              {t(`settings.providers.${p}`)}
            </option>
          ))}
        </select>
        <select
          className={inputCls}
          value={pref?.llm_model ?? ''}
          disabled={!pref?.llm_provider}
          onChange={(e) => save(pref!.llm_provider, e.target.value)}
        >
          <option value="">{t('settings.modelDefault')}</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}

/** One provider credential card: masked key, validate, add/update/delete. */
function CredentialCard({
  provider,
  cred,
  registry,
}: {
  provider: string
  cred?: Credential
  registry: Record<string, ProviderInfo>
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(cred?.base_url ?? '')
  const [model, setModel] = useState(cred?.model_name ?? '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['credentials'] })

  const save = async () => {
    setBusy(true)
    setMessage('')
    try {
      const payload: Record<string, string> = {}
      if (apiKey) payload.api_key = apiKey
      if (provider !== 'mineru') {
        if (baseUrl) payload.base_url = baseUrl
        if (model) payload.model_name = model
      }
      if (cred) {
        await apiFetch(`/api/auth/credentials/${cred.id}`, { method: 'PATCH', body: JSON.stringify(payload) })
      } else {
        await apiFetch('/api/auth/credentials', {
          method: 'POST',
          body: JSON.stringify({ provider, ...payload }),
        })
      }
      setEditing(false)
      setApiKey('')
      refresh()
    } catch {
      setMessage(t('auth.error'))
    } finally {
      setBusy(false)
    }
  }

  const validate = async () => {
    if (!cred) return
    setBusy(true)
    setMessage('')
    try {
      const resp = await apiFetch<{ is_valid: boolean; message: string }>(
        `/api/auth/credentials/${cred.id}/validate`,
        { method: 'POST' },
      )
      setMessage(resp.is_valid ? t('settings.valid') : `${t('settings.invalid')}: ${resp.message}`)
      refresh()
    } catch (e) {
      setMessage(t('settings.invalid'))
      refresh()
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!cred) return
    await apiFetch(`/api/auth/credentials/${cred.id}`, { method: 'DELETE' })
    refresh()
  }

  const isLlm = provider !== 'mineru'

  return (
    <div className="rounded-2xl border border-line px-6 py-5">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-[15px] font-medium text-ink">
          {t(`settings.providers.${provider}`)}
        </h3>
        {cred ? (
          <span
            className={`rounded-full px-2.5 py-0.5 text-[11px] ${
              cred.is_valid === true
                ? 'bg-emerald-50 text-emerald-700'
                : cred.is_valid === false
                  ? 'bg-red-50 text-red-600'
                  : 'bg-surface text-muted'
            }`}
          >
            {cred.is_valid === true
              ? t('settings.valid')
              : cred.is_valid === false
                ? t('settings.invalid')
                : t('settings.notVerified')}
          </span>
        ) : (
          <span className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] text-muted">
            {t('settings.notConfigured')}
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {cred && (
            <button className="text-[12px] text-accent hover:underline" onClick={validate} disabled={busy}>
              {busy ? t('common.loading') : t('settings.validate')}
            </button>
          )}
          <button
            className="text-[12px] text-muted hover:text-ink"
            onClick={() => {
              setEditing(!editing)
              setBaseUrl(cred?.base_url ?? '')
              setModel(cred?.model_name ?? '')
            }}
          >
            {cred ? t('settings.update') : t('settings.add')}
          </button>
          {cred && (
            <button className="text-[12px] text-muted hover:text-red-600" onClick={remove}>
              {t('settings.delete')}
            </button>
          )}
        </div>
      </div>

      {cred && !editing && (
        <p className="mt-2 font-mono text-[12px] text-muted">
          {cred.api_key_masked}
          {isLlm && cred.model_name && <span className="ml-3 font-sans">{cred.model_name}</span>}
          {isLlm && cred.base_url && <span className="ml-3 font-sans text-faint">{cred.base_url}</span>}
        </p>
      )}

      {editing && (
        <div className="mt-4 space-y-3">
          <div>
            <input
              className={inputCls}
              type="password"
              placeholder={t('settings.apiKeyLabel')}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="new-password"
            />
            <p className="mt-1.5 text-[11px] text-faint">{t('settings.apiKeyHint')}</p>
          </div>
          {isLlm && (
            <div className="grid gap-3 sm:grid-cols-2">
              <select className={inputCls} value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="">{t('settings.modelDefault')}</option>
                {(registry[provider]?.models ?? []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <input
                className={inputCls}
                placeholder={t('settings.baseUrlLabel')}
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </div>
          )}
          {provider === 'mimo' && <p className="text-[11px] text-faint">{t('settings.mimoHint')}</p>}
          <button
            disabled={busy || (!apiKey && !cred)}
            onClick={save}
            className="rounded-full bg-accent px-5 py-2 text-[12.5px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? t('common.loading') : t('settings.save')}
          </button>
        </div>
      )}

      {message && <p className="mt-2.5 text-[12px] text-muted">{message}</p>}
    </div>
  )
}

/** Settings: user-supplied API keys, Fernet-encrypted, masked on read (PLAN.md §5.1). */
export default function Settings() {
  const { t } = useTranslation()
  const { data: creds } = useQuery({
    queryKey: ['credentials'],
    queryFn: () => apiFetch<Credential[]>('/api/auth/credentials'),
  })
  const { data: registry } = useQuery({
    queryKey: ['providers'],
    queryFn: () => apiFetch<Record<string, ProviderInfo>>('/api/auth/providers'),
  })

  const byProvider = Object.fromEntries((creds ?? []).map((c) => [c.provider, c]))
  const reg = registry ?? {}

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('page.settingsTitle')}</h1>
      <p className="mt-1.5 text-[13.5px] text-muted">{t('settings.intro')}</p>

      <div className="mt-8 space-y-4">
        <PreferenceCard registry={reg} />
        {['mineru', 'deepseek', 'mimo'].map((p) => (
          <CredentialCard key={p} provider={p} cred={byProvider[p]} registry={reg} />
        ))}
      </div>
    </div>
  )
}
