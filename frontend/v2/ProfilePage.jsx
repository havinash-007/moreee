// ProfilePage.jsx
// Customize: copy, sections. Self-contained: identity + sign-in state, the saved learning profile (editable),
// activity, settings, and privacy controls (export / delete).
// Props: profile {identity, answers, settings, updated, activity:{jobs,prs}, usage, auth, stored}, questions [{id,q,multi,options}],
//        busy, error, notice, onSave({answers, settings}), onUse(), onExport(), onDelete(), onLogout().
const STATUS_TONE = { done: 'bg-emerald-400/15 text-emerald-200', failed: 'bg-rose-400/15 text-rose-200', cancelled: 'bg-white/10 text-zinc-300', expired: 'bg-white/10 text-zinc-300' };

export default function ProfilePage({
  profile = null, questions = [], busy = false, error = '', notice = '',
  onSave = () => {}, onUse = () => {}, onExport = () => {}, onDelete = () => {}, onLogout = () => {},
}) {
  const [answers, setAnswers] = React.useState({});
  const [signoff, setSignoff] = React.useState(false);
  const [confirm, setConfirm] = React.useState('');
  const [asking, setAsking] = React.useState(false);
  React.useEffect(() => { if (profile) { setAnswers(profile.answers || {}); setSignoff(!!(profile.settings && profile.settings.signoff_default)); } }, [profile && profile.updated, profile && profile.identity && profile.identity.login]);
  if (!profile) return <section className="mx-auto max-w-4xl px-6 py-20"><p className="text-zinc-400">Loading your profile…</p></section>;

  const id = profile.identity, hosted = profile.auth.mode === 'github';
  const set = (q, v) => setAnswers((a) => {
    if (q.multi) { const cur = a[q.id] || []; return { ...a, [q.id]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] }; }
    return { ...a, [q.id]: v };
  });
  const dirty = JSON.stringify(answers) !== JSON.stringify(profile.answers || {}) || signoff !== !!profile.settings.signoff_default;
  const complete = questions.length > 0 && questions.every((q) => (q.multi ? (answers[q.id] || []).length : answers[q.id]));
  const used = profile.usage.session.cost_usd, cap = profile.usage.session_budget_usd;
  const Card = ({ title, children, tone }) => (
    <div className={`rounded-3xl border p-6 backdrop-blur md:p-8 ${tone === 'danger' ? 'border-rose-400/30 bg-rose-500/5' : 'border-white/10 bg-zinc-950/75'}`}>
      <h3 className="text-3xl text-white">{title}</h3>{children}
    </div>
  );

  return (
    <section className="mx-auto max-w-4xl px-6 py-14">
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Your profile</p>
      <h2 className="mt-2 text-6xl leading-[0.95] text-white md:text-8xl">{id.name || id.login}</h2>
      {error && <p role="alert" className="mt-6 rounded-2xl border border-rose-400/40 bg-rose-500/10 px-5 py-4 font-semibold text-rose-100">{error}</p>}
      {notice && <p role="status" className="mt-6 rounded-2xl border border-emerald-400/40 bg-emerald-500/10 px-5 py-4 font-semibold text-emerald-100">{notice}</p>}

      <div className="mt-10 space-y-6">
        <Card title="Account">
          <div className="mt-5 flex flex-wrap items-center gap-5">
            {id.avatar ? <img src={id.avatar} alt="" width="72" height="72" className="h-18 w-18 rounded-full border border-white/15" style={{ width: 72, height: 72 }} />
              : <span className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-white/10 text-3xl font-black text-white">{(id.login || '?')[0].toUpperCase()}</span>}
            <div className="min-w-0 flex-1">
              <p className="text-xl font-extrabold text-white">{id.name || id.login}</p>
              {id.url ? <a href={id.url} target="_blank" rel="noopener noreferrer" className="text-base font-bold text-sky-300 hover:underline">@{id.login} ↗</a> : <p className="text-base font-bold text-zinc-400">@{id.login}</p>}
              <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-zinc-200">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />{hosted ? `Signed in with GitHub · session lasts ${profile.auth.session_days} days` : 'Local mode · using the GitHub account logged in on this computer'}
              </p>
            </div>
            {hosted && <button onClick={onLogout} className="rounded-full border-2 border-white/20 px-6 py-2.5 font-bold text-white transition hover:border-white/50">Log out</button>}
          </div>
          {!hosted && <p className="mt-4 text-sm text-zinc-500">Sign-in is off because this copy runs for one person. To require GitHub sign-in for everyone, create a GitHub OAuth App and set <code className="rounded bg-white/10 px-1.5">GITHUB_CLIENT_ID</code> and <code className="rounded bg-white/10 px-1.5">GITHUB_CLIENT_SECRET</code>. See docs/AUTH_SETUP.md.</p>}
        </Card>

        <Card title="Your learning profile">
          <p className="mt-2 text-zinc-400">{profile.updated ? 'Saved from your last quiz. Edit it here and returning to the app skips the interview.' : 'Nothing saved yet. Finish the quiz once, or fill this in.'}</p>
          <div className="mt-6 space-y-6">
            {questions.map((q) => (
              <fieldset key={q.id}>
                <legend className="text-sm font-bold text-zinc-300">{q.q}{q.multi ? ' (pick any)' : ''}</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {q.options.map(([v, label]) => {
                    const on = q.multi ? (answers[q.id] || []).includes(v) : answers[q.id] === v;
                    return <button key={v} type="button" onClick={() => set(q, v)} aria-pressed={on} className={`rounded-full border px-4 py-1.5 text-sm font-bold transition ${on ? 'border-sky-300 bg-sky-300/15 text-white' : 'border-white/15 text-zinc-300 hover:border-white/40'}`}>{label}</button>;
                  })}
                </div>
              </fieldset>
            ))}
          </div>
          <label className="mt-6 flex cursor-pointer items-start gap-3 text-base font-semibold text-zinc-100">
            <input type="checkbox" checked={signoff} onChange={(e) => setSignoff(e.target.checked)} className="mt-1 h-5 w-5 accent-sky-400" />
            Pre-tick the DCO sign-off option in Full-auto (you still confirm it each time).
          </label>
          <div className="mt-6 flex flex-wrap gap-3">
            <button onClick={() => onSave({ answers, settings: { signoff_default: signoff } })} disabled={!dirty || busy} className="rounded-full bg-white px-7 py-3 font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100">{busy ? 'Saving…' : 'Save profile'}</button>
            <button onClick={onUse} disabled={!complete || dirty || busy} title={dirty ? 'Save first' : ''} className="rounded-full border-2 border-white/25 px-7 py-3 font-bold text-white transition hover:border-sky-300 disabled:opacity-40">Find matches with this profile →</button>
          </div>
        </Card>

        <Card title="Activity">
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <div className="rounded-2xl bg-white/5 p-4"><p className="text-xs font-bold uppercase tracking-widest text-zinc-500">PRs opened</p><p className="display mt-1 text-5xl text-white">{profile.activity.prs.length}</p></div>
            <div className="rounded-2xl bg-white/5 p-4"><p className="text-xs font-bold uppercase tracking-widest text-zinc-500">Automated jobs</p><p className="display mt-1 text-5xl text-white">{profile.activity.jobs.length}</p></div>
            <div className="rounded-2xl bg-white/5 p-4"><p className="text-xs font-bold uppercase tracking-widest text-zinc-500">Mentor time used</p><p className="display mt-1 text-5xl text-white">${used.toFixed(2)}</p>
              <div className="mt-2 h-1.5 rounded-full bg-white/10"><div className={`h-1.5 rounded-full ${used / cap > 0.8 ? 'bg-rose-400' : 'bg-emerald-400'}`} style={{ width: Math.min(100, (used / cap) * 100) + '%' }} /></div><p className="mt-1 text-xs text-zinc-500">of ${cap.toFixed(2)} this session</p></div>
          </div>
          {profile.activity.jobs.length > 0 ? (
            <ul className="mt-6 divide-y divide-white/10">
              {profile.activity.jobs.map((j) => (
                <li key={j.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0"><p className="truncate font-bold text-white">{j.title || `${j.repo} #${j.number}`}</p><p className="text-xs text-zinc-500">{j.repo} #{j.number} · {new Date(j.created * 1000).toLocaleDateString()}</p></div>
                  <div className="flex items-center gap-3">
                    <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_TONE[j.status] || 'bg-sky-400/15 text-sky-200'}`}>{j.status}</span>
                    {j.pr_url && <a href={j.pr_url} target="_blank" rel="noopener noreferrer" className="text-sm font-bold text-sky-300 hover:underline">PR ↗</a>}
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-5 text-zinc-500">No automated jobs yet.</p>}
        </Card>

        <Card title="Privacy and your data" tone="danger">
          <p className="mt-2 text-zinc-300">This is everything we keep about you:</p>
          <ul className="mt-3 space-y-1.5 text-sm text-zinc-300">{profile.stored.map((s) => <li key={s}>• {s}</li>)}</ul>
          <div className="mt-6 flex flex-wrap gap-3">
            <button onClick={onExport} className="rounded-full border-2 border-white/25 px-6 py-3 font-bold text-white transition hover:border-white/60">Download my data (JSON)</button>
            {!asking && <button onClick={() => setAsking(true)} className="rounded-full border-2 border-rose-400/50 px-6 py-3 font-bold text-rose-200 transition hover:border-rose-300">Delete my data…</button>}
          </div>
          {asking && (
            <div className="mt-5 rounded-2xl border border-rose-400/40 bg-rose-500/10 p-5">
              <p className="font-bold text-rose-100">This permanently deletes your saved profile, your automated jobs and your usage{hosted ? ', and signs you out' : ''}. It cannot be undone.</p>
              <label htmlFor="del" className="mt-3 block text-sm font-bold text-rose-100">Type DELETE to confirm</label>
              <div className="mt-2 flex flex-wrap gap-3">
                <input id="del" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="w-48 rounded-xl border-2 border-rose-400/40 bg-zinc-900 px-4 py-2 text-white focus:border-rose-300 focus:outline-none" />
                <button onClick={() => onDelete()} disabled={confirm !== 'DELETE' || busy} className="rounded-full bg-rose-400 px-6 py-2.5 font-extrabold text-zinc-950 disabled:opacity-40">Delete everything</button>
                <button onClick={() => { setAsking(false); setConfirm(''); }} className="rounded-full border-2 border-white/20 px-5 py-2.5 font-bold text-white">Keep my data</button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </section>
  );
}
