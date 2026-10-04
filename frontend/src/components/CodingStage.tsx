import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { java } from '@codemirror/lang-java'
import { javascript } from '@codemirror/lang-javascript'
import { cpp } from '@codemirror/lang-cpp'
import { go } from '@codemirror/lang-go'
import { python } from '@codemirror/lang-python'
import { EditorState } from '@codemirror/state'
import { EditorView, lineNumbers } from '@codemirror/view'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  generateCoding,
  getCoding,
  submitCoding,
  type CodingQuestion,
} from '../api/applications'

const LANGS = ['python', 'java', 'javascript', 'cpp', 'go'] as const
const LANG_LABELS: Record<string, string> = {
  python: 'Python',
  java: 'Java',
  javascript: 'JavaScript',
  cpp: 'C++',
  go: 'Go',
}
const langExt = (l: string) =>
  l === 'java' ? java() : l === 'javascript' ? javascript() : l === 'cpp' ? cpp() : l === 'go' ? go() : python()

/** CodeMirror 6 编辑器（语言切换重建；改动回调上抛）。 */
function CodeBox({
  initial,
  language,
  onChange,
}: {
  initial: string
  language: string
  onChange: (code: string) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    if (!host.current) return
    const view = new EditorView({
      state: EditorState.create({
        doc: initial,
        extensions: [
          lineNumbers(),
          langExt(language),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) onChangeRef.current(u.state.doc.toString())
          }),
          EditorView.theme({
            '&': { fontSize: '12.5px', maxHeight: '360px' },
            '.cm-scroller': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' },
            '.cm-content': { padding: '10px 0' },
            '.cm-gutters': { background: '#fafafa', border: 'none' },
          }),
          EditorView.lineWrapping,
        ],
      }),
      parent: host.current,
    })
    return () => view.destroy()
    // 仅语言变化时重建编辑器
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

  return <div ref={host} className="overflow-hidden rounded-xl border border-line bg-white" />
}

const REVIEW_DIMS = ['correctness', 'edge_cases', 'complexity', 'style'] as const

/** 代码笔试（§5.3②）：场景题 + CodeMirror 作答 + AI 四维评审。 */
export default function CodingStage({
  sessionId,
  onGo,
}: {
  sessionId: number
  onGo: (tab: 'quiz' | 'coding' | 'interview') => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [codes, setCodes] = useState<Record<number, string>>({})
  const [langs, setLangs] = useState<Record<number, string>>({})
  const [elapsed, setElapsed] = useState(0)

  const { data: paper } = useQuery({
    queryKey: ['coding', sessionId],
    queryFn: () => getCoding(sessionId),
  })
  const gen = useMutation({
    mutationFn: () => generateCoding(sessionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['coding', sessionId] }),
  })
  const submit = useMutation({
    mutationFn: () =>
      submitCoding(
        sessionId,
        (paper?.questions ?? []).map((q) => ({
          question_id: q.id,
          code: codes[q.id] ?? '',
          language: langs[q.id] ?? q.language_hint ?? 'python',
        })),
      ),
    onSuccess: () => {
      onGo('coding') // 钉在本段展示评审结果
      void queryClient.invalidateQueries({ queryKey: ['coding', sessionId] })
      void queryClient.invalidateQueries({ queryKey: ['application', sessionId] })
    },
  })

  useEffect(() => {
    if (gen.isPending || submit.isPending) {
      const timer = window.setInterval(() => setElapsed((e) => e + 1), 1000)
      return () => window.clearInterval(timer)
    }
    setElapsed(0)
  }, [gen.isPending, submit.isPending])

  if (!paper || gen.isPending)
    return (
      <div className="mt-2">
        <div className="orbit-wrap">
          <div className="rounded-2xl border border-line px-6 py-7">
            <p className="text-[13.5px] font-medium text-ink">{t('coding.generating')}</p>
            <p className="mt-1 text-[11.5px] text-faint">
              {t('interview.planElapsed', { sec: elapsed })}
            </p>
            {!gen.isPending && <p className="mt-2 text-[12px] text-muted">{t('coding.genHint')}</p>}
            {!gen.isPending && (
              <button
                onClick={() => gen.mutate()}
                className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
              >
                {t('coding.genBtn')}
              </button>
            )}
            {gen.isPending && (
              <div className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-surface">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-accent/40" />
              </div>
            )}
          </div>
        </div>
        {gen.isError && <p className="mt-2 text-[12px] text-red-600">{t('coding.genError')}</p>}
      </div>
    )

  if (paper.questions.length === 0)
    return (
      <div className="mt-2 rounded-2xl border border-line px-6 py-8 text-center">
        <button
          onClick={() => gen.mutate()}
          className="rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          {t('coding.genBtn')}
        </button>
      </div>
    )

  const answered = paper.total_score != null
  const anyCode = paper.questions.some((q) => (codes[q.id] ?? '').trim())

  return (
    <div className="mt-2">
      {answered && (
        <div className="rounded-2xl border border-line px-6 py-4">
          <p className="text-[15px] font-medium text-ink">
            {t('quiz.score', { score: Math.round(paper.total_score ?? 0), full: paper.total_full })}
          </p>
          <p className="mt-1 text-[11px] text-faint">{t('coding.aiNote')}</p>
          <button
            onClick={() => onGo('interview')}
            className="mt-3 rounded-full bg-accent px-5 py-2 text-[12.5px] font-medium text-white hover:bg-accent-hover"
          >
            {t('coding.nextInterview')} →
          </button>
        </div>
      )}

      <div className="mt-3 space-y-4">
        {paper.questions.map((q, i) => (
          <CodingCard
            key={q.id}
            q={q}
            index={i}
            code={codes[q.id] ?? q.my_answer?.code ?? ''}
            language={langs[q.id] ?? q.my_answer?.language ?? q.language_hint ?? 'python'}
            editable={!answered}
            onCode={(c) => setCodes((s) => ({ ...s, [q.id]: c }))}
            onLang={(l) => setLangs((s) => ({ ...s, [q.id]: l }))}
          />
        ))}
      </div>

      {!answered && (
        <>
          {submit.isError && (
            <p className="mt-2 text-[12px] text-red-600">{t('coding.submitError')}</p>
          )}
          <button
            onClick={() => submit.mutate()}
            disabled={submit.isPending || !anyCode}
            className="mt-4 w-full rounded-full bg-accent px-6 py-3 text-[13.5px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {submit.isPending ? t('coding.reviewing') : t('coding.submit')}
          </button>
        </>
      )}
    </div>
  )
}

function CodingCard({
  q,
  index,
  code,
  language,
  editable,
  onCode,
  onLang,
}: {
  q: CodingQuestion
  index: number
  code: string
  language: string
  editable: boolean
  onCode: (c: string) => void
  onLang: (l: string) => void
}) {
  const { t } = useTranslation()
  const judge = q.my_answer?.judge
  return (
    <div className="rounded-2xl border border-line px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-2">
        <p className="text-[12px] font-medium text-ink">
          {t('coding.problem')} {index + 1}
        </p>
        <span className="text-[10.5px] text-faint">
          · {q.score_full} 分 · AI {t('coding.reviewBadge')}
        </span>
      </div>
      <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{q.stem}</p>
      {q.function_signature && (
        <pre className="mt-2 overflow-x-auto rounded-xl bg-surface px-3.5 py-2 text-[11.5px] text-ink">
          {q.function_signature}
        </pre>
      )}
      {q.examples.length > 0 && (
        <div className="mt-2 space-y-1">
          {q.examples.map((ex, ei) => (
            <p key={ei} className="text-[11px] leading-relaxed text-muted">
              {t('coding.example')} {ei + 1}：{ex.input} → {ex.output}
              {ex.note ? `（${ex.note}）` : ''}
            </p>
          ))}
        </div>
      )}
      {q.constraints && (
        <p className="mt-1 text-[11px] text-faint">
          {t('coding.constraints')}：{q.constraints}
        </p>
      )}

      <div className="mt-3">
        {editable ? (
          <>
            <div className="mb-1.5 flex items-center gap-2">
              <select
                value={language}
                onChange={(e) => onLang(e.target.value)}
                className="rounded-lg border border-line bg-white px-2 py-1 text-[11.5px] text-ink"
              >
                {LANGS.map((l) => (
                  <option key={l} value={l}>
                    {LANG_LABELS[l]}
                  </option>
                ))}
              </select>
            </div>
            <CodeBox initial={code} language={language} onChange={onCode} />
          </>
        ) : (
          q.my_answer?.code && (
            <pre className="overflow-x-auto rounded-xl bg-surface px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink">
              {q.my_answer.code}
            </pre>
          )
        )}
      </div>

      {/* AI 评审结果 */}
      {judge && q.my_answer && (
        <div className="mt-3 rounded-xl bg-surface px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {REVIEW_DIMS.map((d) => (
              <span key={d} className="text-[11px] text-muted">
                {t(`coding.dims.${d}`)}
                <span className="ml-1 tabular-nums text-ink">{judge[d]?.score ?? 0}/10</span>
              </span>
            ))}
            <span className="ml-auto text-[12px] font-medium tabular-nums text-accent">
              {q.my_answer.score}/{q.score_full}
            </span>
          </div>
          {judge.summary && <p className="mt-2 text-[12px] leading-relaxed text-ink">{judge.summary}</p>}
          <div className="mt-2 space-y-1">
            {REVIEW_DIMS.filter((d) => judge[d]?.comment).map((d) => (
              <p key={d} className="text-[11px] leading-relaxed text-muted">
                · {t(`coding.dims.${d}`)}：{judge[d]?.comment}
              </p>
            ))}
            {judge.reason && <p className="text-[11px] text-muted">· {judge.reason}</p>}
          </div>
          {judge.improved_solution && (
            <div className="mt-2.5">
              <p className="text-[11px] font-medium text-muted">{t('coding.improved')}</p>
              <pre className="mt-1 overflow-x-auto rounded-xl bg-white px-3.5 py-2 text-[11px] leading-relaxed text-ink">
                {judge.improved_solution}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
