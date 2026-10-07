// IssueBoard.jsx
// Customize: copy, colors, checklist labels.
// Props: issues [{repo,number,title,url,fit,learn,hours,risk,labels,legal:[],ai_flags:[{file,line}]}],
//        org, skipped [{repo,reason}], onPick(index), onBack, busy.
export default function IssueBoard({ issues = [], org = '', skipped = [], onPick = () => {}, onBack = () => {}, busy = false }) {
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
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-violet-300">Verified just now</p>
      <h2 className="mt-3 text-5xl font-black leading-none tracking-tighter text-white md:text-7xl">
        Three issues. <span className="bg-gradient-to-r from-emerald-300 to-cyan-400 bg-clip-text text-transparent">All yours to take.</span>
      </h2>
      <p className="mt-5 max-w-2xl text-lg font-medium text-zinc-300">
        Open, unassigned, and no pull request attached, in {org}. Pick the one that excites you.
      </p>

      {issues.length === 0 && (
        <div className="mt-12 rounded-3xl border border-white/10 bg-zinc-950/70 p-10 text-center">
          <p className="text-2xl font-black text-white">Nothing free passed the checks.</p>
          <p className="mt-2 text-zinc-400">That happens with popular projects. Try another organisation.</p>
        </div>
      )}

      <div className="mt-12 grid gap-6 lg:grid-cols-3">
        {issues.map((p, i) => {
          const flagged = (p.ai_flags || []).length > 0;
          return (
            <article key={`${p.repo}#${p.number}`} className="flex flex-col rounded-3xl border border-white/10 bg-zinc-950/75 p-6 backdrop-blur transition duration-200 hover:-translate-y-1 hover:border-violet-400/60">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-violet-500/20 px-3 py-1 text-xs font-black uppercase tracking-wider text-violet-200">~{p.hours}h</span>
                <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-zinc-400 underline-offset-4 hover:text-white hover:underline">
                  {p.repo}#{p.number} ↗
                </a>
              </div>
              <h3 className="mt-5 text-2xl font-black leading-tight tracking-tight text-white">{p.title}</h3>
              <p className="mt-3 text-base font-medium text-zinc-300">{p.fit}</p>
              <p className="mt-3 text-sm text-zinc-400"><b className="text-zinc-200">You will learn:</b> {p.learn}</p>
              <p className="mt-2 text-sm text-zinc-400"><b className="text-zinc-200">Watch for:</b> {p.risk}</p>

              <ul className="mt-5 space-y-2 rounded-2xl bg-white/5 p-4">
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
                className="mt-6 w-full rounded-full bg-white px-6 py-3.5 text-base font-extrabold text-zinc-950 transition duration-200 hover:scale-[1.03] hover:brightness-110 focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400 disabled:opacity-50 disabled:hover:scale-100 mt-auto"
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
