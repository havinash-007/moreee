// IssueBoard.jsx
// Customize: copy, colors, checklist labels.
// Props: issues [{repo,number,title,url,fit,learn,hours,risk,labels,legal:[],ai_flags:[{file,line}]}],
//        org, skipped [{repo,reason}], onPick(index), onBack, busy.
function ago(iso, now) {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return s < 5 ? 'just now' : s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${Math.floor(s / 3600)} h ago`;
}

export default function IssueBoard({
  issues = [], org = '', skipped = [], stats = null, alternatives = [], notice = '', checking = -1,
  onPick = () => {}, onBack = () => {}, onRecheck = () => {}, onTry = () => {}, busy = false,
}) {
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => { const t = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(t); }, []);
  const Check = ({ ok, children }) => (
    <li className="flex items-center gap-2 text-sm font-semibold">
      <span className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-black ${ok ? 'bg-emerald-400 text-zinc-950' : 'bg-amber-400 text-zinc-950'}`}>
        {ok ? '✓' : '!'}
      </span>
      <span className={ok ? 'text-zinc-200' : 'text-amber-200'}>{children}</span>
    </li>
  );
  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <button onClick={onBack} className="mb-8 text-sm font-bold text-zinc-400 transition hover:text-white">← Back to matches</button>
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Checked live against GitHub</p>
      <h2 className="mt-3 text-6xl leading-[0.95] text-white md:text-8xl">
        {issues.length === 0 ? 'Nothing free here, yet. ' : `${['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight'][Math.min(issues.length, 8)]} ${issues.length === 1 ? 'issue' : 'issues'}. `}
        <em className="bg-gradient-to-r from-sky-200 via-cyan-200 to-orange-300 bg-clip-text pr-1 text-transparent">
          {issues.length === 0 ? 'Let us look elsewhere.' : issues.length === 1 ? 'Yours to take.' : 'All yours to take.'}
        </em>
      </h2>
      <p className="mt-5 max-w-2xl text-lg font-medium text-zinc-300">
        {issues.length ? `Open, unassigned, and no pull request attached, in ${org}. Pick the one that excites you.` : `We checked ${org} just now.`}
      </p>

      {notice && <p role="alert" className="mt-8 rounded-2xl border border-amber-400/40 bg-amber-400/10 px-5 py-4 text-base font-semibold text-amber-100">{notice}</p>}

      {issues.length === 0 && (
        <div className="mt-12 rounded-3xl border border-white/10 bg-zinc-950/70 p-8 md:p-10">
          <h3 className="text-4xl text-white">Everything here is taken right now.</h3>
          <p className="mt-3 max-w-2xl text-lg text-zinc-300">
            Popular projects get their easy issues claimed within hours, so this is normal. We looked, and we only show issues that are genuinely free.
          </p>
          {stats && (
            <ul className="mt-6 flex flex-wrap gap-3 text-sm font-bold">
              <li className="rounded-full bg-white/10 px-4 py-2 text-zinc-200">Searched: {(stats.tried || []).join(', ')}</li>
              <li className="rounded-full bg-white/10 px-4 py-2 text-zinc-200">{stats.found} open and unassigned</li>
              {stats.has_pr > 0 && <li className="rounded-full bg-white/10 px-4 py-2 text-zinc-200">{stats.has_pr} already have an open PR</li>}
              {stats.claimed > 0 && <li className="rounded-full bg-white/10 px-4 py-2 text-zinc-200">{stats.claimed} claimed in comments</li>}
              {stats.policy_skipped > 0 && <li className="rounded-full bg-white/10 px-4 py-2 text-zinc-200">{stats.policy_skipped} skipped for AI policy</li>}
            </ul>
          )}
          {alternatives.length > 0 && (
            <>
              <p className="mt-8 text-sm font-bold uppercase tracking-widest text-zinc-500">Try one of your next best matches</p>
              <div className="mt-3 flex flex-wrap gap-3">
                {alternatives.map((a) => (
                  <button key={a.github} onClick={() => onTry(a)} disabled={busy} className="rounded-full border-2 border-white/25 px-6 py-3 text-base font-extrabold text-white transition hover:border-sky-300 disabled:opacity-40">{a.org} →</button>
                ))}
              </div>
            </>
          )}
          <button onClick={onBack} className="mt-6 text-sm font-bold text-zinc-400 hover:text-white">← Back to all matches</button>
        </div>
      )}

      <div className="mt-12 grid gap-6 lg:grid-cols-3">
        {issues.map((p, i) => {
          const flagged = (p.ai_flags || []).length > 0;
          return (
            <article key={`${p.repo}#${p.number}`} className="flex flex-col rounded-3xl border border-white/10 bg-zinc-950/75 p-6 backdrop-blur transition duration-200 hover:-translate-y-1 hover:border-sky-400/60">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-amber-500/20 px-3 py-1 text-xs font-black uppercase tracking-wider text-amber-200">~{p.hours}h</span>
                <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-zinc-400 underline-offset-4 hover:text-white hover:underline">
                  {p.repo}#{p.number} ↗
                </a>
              </div>
              <h3 className="mt-5 text-2xl font-black leading-tight tracking-tight text-white">{p.title}</h3>
              <p className="mt-3 text-base font-medium text-zinc-300">{p.fit}</p>
              <p className="mt-3 text-sm text-zinc-400"><b className="text-zinc-200">You will learn:</b> {p.learn}</p>
              <p className="mt-2 text-sm text-zinc-400"><b className="text-zinc-200">Watch for:</b> {p.risk}</p>

              <div className="mt-4 flex items-center justify-between text-xs font-bold text-zinc-500">
                <span>Verified {p.verified_at ? ago(p.verified_at, now) : 'just now'}</span>
                <button onClick={() => onRecheck(i)} disabled={checking === i || busy} className="rounded-full border border-white/15 px-3 py-1 text-zinc-300 transition hover:border-sky-300 hover:text-white disabled:opacity-40">{checking === i ? 'Checking…' : 'Re-check now'}</button>
              </div>
              <ul className="mt-3 space-y-2 rounded-2xl bg-white/5 p-4">
                <Check ok>Unassigned</Check>
                <Check ok>No linked pull request</Check>
                <Check ok={!flagged}>{flagged ? 'AI policy found: read it first' : 'No AI restriction found in policy files'}</Check>
                {(p.legal || []).length > 0 && <Check ok={false}>{p.legal.join(' + ')} sign-off required (you sign it, not us)</Check>}
              </ul>

              {flagged && (
                <div className="mt-4 rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4">
                  <p className="text-sm font-black text-amber-200">What this means for you</p>
                  <p className="mt-1 text-sm text-amber-100/90">Write and understand every line yourself, and do not post AI-written comments to maintainers.</p>
                  <p className="mt-2 border-l-2 border-amber-400/60 pl-3 text-xs italic text-amber-100/80">“{p.ai_flags[0].line}” ({p.ai_flags[0].file})</p>
                </div>
              )}

              <button
                onClick={() => onPick(i)}
                disabled={busy}
                className="mt-6 w-full rounded-full bg-white px-6 py-3.5 text-base font-extrabold text-zinc-950 transition duration-200 hover:scale-[1.03] hover:brightness-110 focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400 disabled:opacity-50 disabled:hover:scale-100 mt-auto"
              >
                {busy ? 'Preparing your tour…' : 'Start working on this →'}
              </button>
            </article>
          );
        })}
      </div>

      {skipped.length > 0 && (
        <p className="mt-8 text-sm text-zinc-500">Skipped for policy: {skipped.map((s) => s.repo).join(', ')}.</p>
      )}
    </section>
  );
}
