// WorkspaceView.jsx
// Customize: step names + "done when" text, hint button labels, colors.
// Props: issue {repo,number,title,url,legal[]}, tourHtml (already sanitised HTML string),
//        messages [{role:'user'|'assistant', text?, html?}], onSend(text), busy, mode ('learn'|'semi'), onBack, costNote.
// Layout: journey stepper | tabs (Tour, Coach) | context.
const STEPS = [
  ['Understand', 'You can explain what the project does and where the issue lives.'],
  ['Reproduce', 'You saw the bug yourself, or wrote down what you expect to find.'],
  ['Fix', 'You wrote the smallest change that solves it, in your own hands.'],
  ['Test', 'A test fails before and passes after. Project checks are green locally.'],
  ['Open PR', 'Honest description in your own words, sign-off done by you.'],
  ['Review', 'You answered every reviewer comment politely.'],
];

export default function WorkspaceView({
  issue = { repo: 'owner/repo', number: 1, title: 'Example issue', url: '#', legal: [] },
  tourHtml = '<p>Your repo tour appears here.</p>',
  messages = [],
  onSend = () => {},
  busy = false,
  mode = 'learn',
  onBack = () => {},
  costNote = '',
}) {
  const key = `steps:${issue.repo}#${issue.number}`;
  const [tab, setTab] = React.useState('tour');
  const [done, setDone] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem(key)) || []; } catch { return []; }
  });
  const [text, setText] = React.useState('');
  const endRef = React.useRef(null);

  React.useEffect(() => { try { localStorage.setItem(key, JSON.stringify(done)); } catch {} }, [done]);
  React.useEffect(() => { if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight; }, [messages, busy, tab]);

  const current = STEPS.findIndex((_, i) => !done.includes(i));
  const toggle = (i) => setDone((d) => (d.includes(i) ? d.filter((x) => x !== i) : [...d, i]));
  const send = (t) => { const v = (t ?? text).trim(); if (!v || busy) return; onSend(v); setText(''); setTab('coach'); };
  const pct = Math.round((done.length / STEPS.length) * 100);

  return (
    <section className="mx-auto max-w-[1400px] px-4 py-10 md:px-8">
      <button onClick={onBack} className="mb-6 text-sm font-bold text-zinc-400 transition hover:text-white">← Back to issues</button>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-violet-300">{issue.repo} #{issue.number}</p>
          <h2 className="mt-2 max-w-3xl text-3xl font-black leading-tight tracking-tight text-white md:text-5xl">{issue.title}</h2>
        </div>
        <div className="w-48">
          <div className="mb-1 flex justify-between text-xs font-bold text-zinc-400"><span>Progress</span><span>{pct}%</span></div>
          <div className="h-2 rounded-full bg-white/10"><div className="h-2 rounded-full bg-gradient-to-r from-violet-400 to-pink-400 transition-all duration-500" style={{ width: pct + '%' }} /></div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
        {/* stepper */}
        <ol className="space-y-2 lg:sticky lg:top-24 lg:self-start">
          {STEPS.map(([name, hint], i) => {
            const isDone = done.includes(i), now = i === current;
            return (
              <li key={name}>
                <button
                  onClick={() => toggle(i)}
                  aria-pressed={isDone}
                  className={`w-full rounded-2xl border-2 p-3 text-left transition duration-150 hover:scale-[1.02] focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400 ${
                    now ? 'border-violet-400 bg-violet-500/15' : 'border-white/10 bg-zinc-950/70'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-black ${isDone ? 'bg-emerald-400 text-zinc-950' : now ? 'bg-violet-400 text-zinc-950' : 'bg-white/10 text-zinc-400'}`}>
                      {isDone ? '✓' : i + 1}
                    </span>
                    <span className={`text-base font-extrabold ${isDone ? 'text-zinc-400 line-through' : 'text-white'}`}>{name}</span>
                  </div>
                  {now && <p className="mt-2 pl-10 text-xs font-medium text-zinc-300">Done when: {hint}</p>}
                </button>
              </li>
            );
          })}
        </ol>

        {/* centre */}
        <div className="min-w-0 rounded-3xl border border-white/10 bg-zinc-950/75 backdrop-blur">
          <div role="tablist" className="flex gap-2 border-b border-white/10 p-3">
            {[['tour', 'Repo tour'], ['coach', mode === 'learn' ? 'Coach' : 'Pair programmer']].map(([id, label]) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`rounded-full px-5 py-2 text-sm font-extrabold transition ${tab === id ? 'bg-white text-zinc-950' : 'text-zinc-300 hover:bg-white/10'}`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'tour' ? (
            <div className="tour h-[calc(100vh-17rem)] min-h-[420px] overflow-auto p-6 md:p-8" dangerouslySetInnerHTML={{ __html: tourHtml }} />
          ) : (
            <div className="flex h-[calc(100vh-17rem)] min-h-[420px] flex-col">
              <div ref={endRef} className="flex-1 space-y-3 overflow-auto p-5 md:p-6" aria-live="polite">
                {messages.length === 0 && (
                  <div className="rounded-2xl bg-white/5 p-5 text-zinc-300">
                    <p className="text-lg font-extrabold text-white">Start with your own guess.</p>
                    <p className="mt-1 text-sm">Tell me what you think causes this, or where you would look first. I will ask questions before I point at anything.</p>
                  </div>
                )}
                {messages.map((m, i) => (
                  <div key={i} className={`max-w-[92%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${m.role === 'user' ? 'ml-auto bg-violet-500/25 text-white' : 'tour bg-white/5 text-zinc-100'}`}>
                    {m.html ? <div dangerouslySetInnerHTML={{ __html: m.html }} /> : m.text}
                  </div>
                ))}
                {busy && <div className="w-16 rounded-2xl bg-white/5 px-4 py-3 text-zinc-400"><span className="animate-pulse">•••</span></div>}
              </div>
              <div className="border-t border-white/10 p-4">
                <div className="mb-3 flex flex-wrap gap-2">
                  {[['I am stuck: next hint, please', 'Bigger hint'], ['Quiz me on this code', 'Quiz me'], ['Review what I have so far', 'Review my work']].map(([t, l]) => (
                    <button key={l} onClick={() => send(t)} disabled={busy} className="rounded-full border border-white/20 px-4 py-1.5 text-xs font-bold text-zinc-200 transition hover:border-violet-300 hover:text-white disabled:opacity-40">{l}</button>
                  ))}
                </div>
                <div className="flex gap-3">
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && send()}
                    placeholder="Type your idea or question…"
                    className="min-w-0 flex-1 rounded-full border-2 border-white/15 bg-zinc-900 px-5 py-3 text-base text-white placeholder-zinc-500 focus:border-violet-400 focus:outline-none"
                  />
                  <button onClick={() => send()} disabled={busy || !text.trim()} className="rounded-full bg-white px-7 py-3 text-base font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100">Send</button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* context */}
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="rounded-3xl border border-white/10 bg-zinc-950/75 p-5 backdrop-blur">
            <p className="text-xs font-black uppercase tracking-widest text-zinc-500">Quick links</p>
            <a href={issue.url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-base font-bold text-violet-300 hover:underline">Open the issue ↗</a>
            <a href={`https://github.com/${issue.repo}/blob/HEAD/CONTRIBUTING.md`} target="_blank" rel="noopener noreferrer" className="mt-1 block text-base font-bold text-violet-300 hover:underline">Contributing guide ↗</a>
          </div>
          <div className="rounded-3xl border border-amber-400/30 bg-amber-400/10 p-5">
            <p className="text-xs font-black uppercase tracking-widest text-amber-300">Before you open the PR</p>
            <ul className="mt-2 space-y-1.5 text-sm font-medium text-amber-50/90">
              {(issue.legal || []).length > 0 && <li>• Sign the {issue.legal.join(' / ')} yourself. We never do it for you.</li>}
              <li>• Explain every changed line without help.</li>
              <li>• Write the description in your own words.</li>
              <li>• Say if AI helped, if the project asks.</li>
            </ul>
          </div>
          {costNote && <p className="px-2 text-xs font-semibold text-zinc-500">{costNote}</p>}
        </aside>
      </div>
    </section>
  );
}
