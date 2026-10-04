import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { java } from '@codemirror/lang-java'
import { javascript } from '@codemirror/lang-javascript'
import { cpp } from '@codemirror/lang-cpp'
import { go } from '@codemirror/lang-go'
import { python } from '@codemirror/lang-python'
import { completeFromList } from '@codemirror/autocomplete'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { basicSetup } from 'codemirror'
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

// 各语言关键字/常用内置 —— 代码补全词条
const KEYWORDS: Record<string, string[]> = {
  python: ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'break', 'continue',
    'import', 'from', 'as', 'try', 'except', 'finally', 'raise', 'with', 'lambda', 'yield',
    'async', 'await', 'pass', 'None', 'True', 'False', 'self', 'print', 'len', 'range',
    'enumerate', 'zip', 'sorted', 'dict', 'list', 'set', 'tuple', 'str', 'int', 'float'],
  java: ['public', 'private', 'protected', 'class', 'interface', 'extends', 'implements',
    'static', 'final', 'void', 'int', 'long', 'double', 'boolean', 'char', 'String', 'new',
    'return', 'if', 'else', 'for', 'while', 'switch', 'case', 'break', 'continue', 'try',
    'catch', 'finally', 'throw', 'throws', 'import', 'package', 'null', 'true', 'false',
    'ArrayList', 'HashMap', 'List', 'Map', 'Set'],
  javascript: ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'do',
    'switch', 'case', 'break', 'continue', 'try', 'catch', 'finally', 'throw', 'new', 'class',
    'extends', 'import', 'export', 'from', 'async', 'await', 'null', 'undefined', 'true',
    'false', 'this', 'typeof', 'instanceof', 'Map', 'Set', 'Promise', 'console', 'log'],
  cpp: ['int', 'long', 'double', 'float', 'char', 'bool', 'void', 'string', 'vector', 'map',
    'unordered_map', 'set', 'unordered_set', 'pair', 'auto', 'const', 'static', 'class',
    'struct', 'public', 'private', 'protected', 'return', 'if', 'else', 'for', 'while',
    'switch', 'case', 'break', 'continue', 'try', 'catch', 'throw', 'new', 'delete',
    'nullptr', 'true', 'false', 'using', 'namespace', 'std', 'size_t'],
  go: ['func', 'package', 'import', 'var', 'const', 'type', 'struct', 'interface', 'map',
    'chan', 'return', 'if', 'else', 'for', 'range', 'switch', 'case', 'default', 'break',
    'continue', 'go', 'defer', 'select', 'nil', 'true', 'false', 'make', 'new', 'len', 'cap',
    'append', 'string', 'int', 'error'],
}

/** CodeMirror 6 编辑器：语法高亮 + 括号自动闭合 + 关键字补全；高度放大便于看补全弹窗。 */
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
    const completions = completeFromList(
      (KEYWORDS[language] ?? KEYWORDS.python).map((w) => ({ label: w, type: 'keyword' })),
    )
    const view = new EditorView({
      state: EditorState.create({
        doc: initial,
        extensions: [
          basicSetup,
          langExt(language),
          EditorState.languageData.of(() => [{ autocomplete: completions }]),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) onChangeRef.current(u.state.doc.toString())
          }),
          EditorView.theme({
            '&': { fontSize: '12.5px', height: 'min(62vh, 560px)' },
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

/** 代码笔试（§5.3②）：LeetCode 式一题一屏（左题目 / 右代码），AI 评审先优点后不足。 */
export default function CodingStage({
  sessionId,
  onGo,
}: {
  sessionId: number
  onGo: (tab: 'quiz' | 'coding' | 'interview') => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [active, setActive] = useState(0)
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
          language: langs[q.id] ?? q.my_answer?.language ?? q.language_hint ?? 'python',
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
  const q = paper.questions[Math.min(active, paper.questions.length - 1)]
  const anyCode = paper.questions.some((x) => (codes[x.id] ?? x.my_answer?.code ?? '').trim())
  const lang = langs[q.id] ?? q.my_answer?.language ?? q.language_hint ?? 'python'

  return (
    <div className="mt-2">
      {answered && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-line px-6 py-4">
          <p className="text-[15px] font-medium text-ink">
            {t('quiz.score', { score: Math.round(paper.total_score ?? 0), full: paper.total_full })}
          </p>
          <p className="text-[11px] text-faint">{t('coding.aiNote')}</p>
          <button
            onClick={() => onGo('interview')}
            className="ml-auto rounded-full bg-accent px-5 py-2 text-[12.5px] font-medium text-white hover:bg-accent-hover"
          >
            {t('coding.nextInterview')} →
          </button>
        </div>
      )}

      {/* 题目切换（一题一屏） */}
      <div className="mt-3 flex flex-wrap gap-2">
        {paper.questions.map((x, i) => (
          <button
            key={x.id}
            onClick={() => setActive(i)}
            className={`rounded-full px-4 py-1.5 text-[12px] transition-colors ${
              i === active ? 'bg-ink text-white' : 'border border-line text-muted hover:text-ink'
            }`}
          >
            {t('coding.problem')} {i + 1}
            {x.my_answer ? ' ✓' : ''}
          </button>
        ))}
      </div>

      {/* LeetCode 式分栏：左题目 / 右代码 */}
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {/* 左：题目 */}
        <div className="rounded-2xl border border-line px-5 py-4">
          <div className="flex flex-wrap items-center gap-x-2">
            <p className="text-[12.5px] font-medium text-ink">
              {t('coding.problem')} {q.seq}
            </p>
            <span className="text-[10.5px] text-faint">
              · {q.score_full} 分 · AI {t('coding.reviewBadge')}
            </span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{q.stem}</p>
          {q.function_signature && (
            <pre className="mt-2.5 overflow-x-auto rounded-xl bg-surface px-3.5 py-2 text-[11.5px] text-ink">
              {q.function_signature}
            </pre>
          )}
          {q.examples.length > 0 && (
            <div className="mt-2.5 space-y-1">
              {q.examples.map((ex, ei) => (
                <p key={ei} className="text-[12px] leading-relaxed text-ink">
                  <span className="text-muted">
                    {t('coding.example')} {ei + 1}：
                  </span>
                  {ex.input} → {ex.output}
                  {ex.note ? `（${ex.note}）` : ''}
                </p>
              ))}
            </div>
          )}
          {q.constraints && (
            <p className="mt-2 text-[12px] leading-relaxed text-ink">
              <span className="font-medium text-muted">{t('coding.constraints')}：</span>
              {q.constraints}
            </p>
          )}
        </div>

        {/* 右：代码 */}
        <div>
          {answered ? (
            <pre className="overflow-x-auto rounded-2xl border border-line bg-white px-4 py-3 text-[12px] leading-relaxed text-ink">
              {q.my_answer?.code || t('coding.notSubmitted')}
            </pre>
          ) : (
            <>
              <div className="mb-1.5 flex items-center gap-2">
                <select
                  value={lang}
                  onChange={(e) => setLangs((s) => ({ ...s, [q.id]: e.target.value }))}
                  className="rounded-lg border border-line bg-white px-2 py-1 text-[11.5px] text-ink"
                >
                  {LANGS.map((l) => (
                    <option key={l} value={l}>
                      {LANG_LABELS[l]}
                    </option>
                  ))}
                </select>
              </div>
              <CodeBox
                initial={codes[q.id] ?? q.my_answer?.code ?? ''}
                language={lang}
                onChange={(c) => setCodes((s) => ({ ...s, [q.id]: c }))}
              />
            </>
          )}
        </div>
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

      {/* AI 评审（先优点后不足 + 带讲解的参考答案） */}
      {q.my_answer?.judge && <ReviewCard q={q} />}
    </div>
  )
}

function ReviewCard({ q }: { q: CodingQuestion }) {
  const { t } = useTranslation()
  const judge = q.my_answer!.judge
  const solution = judge.solution
  return (
    <div className="mt-4 rounded-2xl border border-line px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-[13px] font-medium text-ink">{t('coding.reviewTitle')}</p>
        {REVIEW_DIMS.map((d) => (
          <span key={d} className="text-[11px] text-muted">
            {t(`coding.dims.${d}`)}
            <span className="ml-1 tabular-nums text-ink">{judge[d]?.score ?? 0}/10</span>
          </span>
        ))}
        <span className="ml-auto text-[13px] font-medium tabular-nums text-accent">
          {q.my_answer!.score}/{q.score_full}
        </span>
      </div>
      {judge.summary && <p className="mt-2 text-[12.5px] leading-relaxed text-ink">{judge.summary}</p>}

      {/* 优点 / 不足 */}
      {(judge.strengths ?? []).length > 0 && (
        <>
          <p className="mt-3 text-[11.5px] font-medium text-emerald-700">{t('coding.strengths')}</p>
          <ul className="mt-1 space-y-1">
            {(judge.strengths ?? []).map((s, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-ink">
                · {s}
              </li>
            ))}
          </ul>
        </>
      )}
      {(judge.weaknesses ?? []).length > 0 && (
        <>
          <p className="mt-2.5 text-[11.5px] font-medium text-amber-700">{t('coding.weaknesses')}</p>
          <ul className="mt-1 space-y-1">
            {(judge.weaknesses ?? []).map((w, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-ink">
                · {w}
              </li>
            ))}
          </ul>
        </>
      )}

      {/* 四维批注 */}
      <div className="mt-2.5 space-y-1">
        {REVIEW_DIMS.filter((d) => judge[d]?.comment).map((d) => (
          <p key={d} className="text-[11.5px] leading-relaxed text-muted">
            · {t(`coding.dims.${d}`)}：{judge[d]?.comment}
          </p>
        ))}
      </div>

      {/* 参考答案三件套：解题思路 + 参考代码 + 逐段解释 */}
      {solution && (solution.approach || solution.code || solution.explanation) && (
        <div className="mt-4 rounded-xl bg-surface px-4 py-3.5">
          <p className="text-[12px] font-medium text-ink">{t('coding.solution')}</p>
          {solution.approach && (
            <>
              <p className="mt-2.5 text-[11px] font-medium text-muted">
                {t('coding.solutionApproach')}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-ink">
                {solution.approach}
              </p>
            </>
          )}
          {solution.code && (
            <>
              <p className="mt-2.5 text-[11px] font-medium text-muted">
                {t('coding.solutionCode')}
              </p>
              <pre className="mt-1 overflow-x-auto rounded-xl bg-white px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink">
                {solution.code}
              </pre>
            </>
          )}
          {solution.explanation && (
            <>
              <p className="mt-2.5 text-[11px] font-medium text-muted">
                {t('coding.solutionExplanation')}
              </p>
              <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-ink">
                {solution.explanation}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
