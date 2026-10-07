// app.jsx: the shell. Owns state and API calls; the six components do all the visual work.
// Flow: hero -> interview -> matches -> issues -> workspace, plus a Replies tab.

const renderMd = (md) => {
  const html = marked.parse(md || '').replace(/<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g, '<pre class="mermaid">$1</pre>');
  return DOMPurify.sanitize(html, { ADD_ATTR: ['class'] });
};

const FRIENDLY = {
  auth: 'The mentor is resting right now. Please try again in a little while.',
  budget: 'You have used all of your mentor time for this session. Your matches and notes are still here.',
  claude: 'The mentor had a hiccup. Try again in a moment.',
  github: 'GitHub is busy or unreachable. Wait a few seconds and try again.',
};

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({ error: 'Bad response from server' }));
  if (r.status === 401) { const e = new Error('login'); e.login = true; throw e; }
  if (!r.ok) { const e = new Error(FRIENDLY[j.kind] || j.error || j.detail || 'Something went wrong'); e.kind = j.kind; throw e; }
  return j;
}

export default function App() {
  const { HeroSection, InterviewStep, MatchPodium, IssueBoard, WorkspaceView, RepliesInbox } = window.OSS;
  const [view, setView] = React.useState('mentor');
  const [step, setStep] = React.useState('hero');
  const [me, setMe] = React.useState({ hosted: false, login: 'local' });
  const [orgs, setOrgs] = React.useState([]);
  const [qs, setQs] = React.useState([]);
  const [qi, setQi] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [ranking, setRanking] = React.useState([]);
  const [org, setOrg] = React.useState(null);
  const [scout, setScout] = React.useState({ picks: [], skipped: [] });
  const [issue, setIssue] = React.useState(null);
  const [tourHtml, setTourHtml] = React.useState('');
  const [tourMd, setTourMd] = React.useState('');
  const [msgs, setMsgs] = React.useState([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [usage, setUsage] = React.useState(null);
  const [prUrl, setPrUrl] = React.useState('');
  const [drafts, setDrafts] = React.useState(null);
  const [notice, setNotice] = React.useState('');

  const needsLogin = me.hosted && !me.login;

  const refreshUsage = async () => { try { setUsage(await api('/api/usage')); } catch {} };
  const run = async (fn) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { if (e.login) setMe({ hosted: true, login: null }); else setError(e.message); }
    finally { setBusy(false); refreshUsage(); }
  };
  const stage3d = (st, extra) => { if (window.Scene && Scene.available) Scene.setStage(st, extra); };

  // boot
  React.useEffect(() => {
    (async () => {
      try { setMe(await api('/api/me')); } catch {}
      try { const o = await api('/api/orgs'); setOrgs(o); if (window.Scene) Scene.init(o); } catch {}
      refreshUsage();
    })();
  }, []);

  // galaxy reacts to interview answers
  const fit = (o, a) => {
    const l = (a.languages || []).map((x) => x.toLowerCase());
    const i = a.interests || [];
    const okL = !l.length || o.languages.some((x) => l.includes(x.toLowerCase()));
    const okI = !i.length || o.domains.some((x) => i.includes(x));
    return okL && okI;
  };
  const fitCount = orgs.length ? orgs.filter((o) => fit(o, answers)).length : null;
  React.useEffect(() => {
    if (step === 'interview' && window.Scene) Scene.react((o) => fit(o, answers));
  }, [answers, step, orgs]);

  // mermaid diagrams inside the tour
  React.useEffect(() => {
    if (step !== 'work' || !window.mermaid) return;
    const t = setTimeout(() => {
      try { mermaid.initialize({ startOnLoad: false, theme: 'dark' }); mermaid.run({ querySelector: '.tour pre.mermaid' }); } catch {}
    }, 150);
    return () => clearTimeout(t);
  }, [step, tourHtml, msgs.length]);

  const start = () => run(async () => {
    if (!qs.length) setQs(await api('/api/questions'));
    setQi(0); setStep('interview'); stage3d('explore');
  });
  const next = () => {
    if (qi < qs.length - 1) return setQi(qi + 1);
    run(async () => {
      const r = (await api('/api/match', answers)).ranking;
      setRanking(r); setStep('matches');
      stage3d('ranked', { focus: r.map((x) => x.org), scores: Object.fromEntries(r.map((x) => [x.org, x.total])) });
    });
  };
  const choose = (i) => run(async () => {
    const o = ranking[i]; setOrg(o); stage3d('selected', { pick: o.org });
    try { setScout(await api('/api/scout', { org: o.github, profile: answers })); }
    catch (e) { stage3d('ranked', { focus: ranking.map((x) => x.org), scores: Object.fromEntries(ranking.map((x) => [x.org, x.total])) }); throw e; }
    setStep('issues'); stage3d('working', { pick: o.org });
  });
  const pickIssue = (i) => run(async () => {
    const p = scout.picks[i];
    const t = await api('/api/tour', { repo: p.repo, issue_title: p.title, level: answers.skill || 'beginner' });
    setIssue(p); setTourMd(t.markdown); setTourHtml(renderMd(t.markdown)); setMsgs([]); setStep('work');
  });
  const send = (text) => {
    const history = [...msgs.map((m) => ({ role: m.role, content: m.md || m.text })), { role: 'user', content: text }];
    setMsgs((m) => [...m, { role: 'user', text }]);
    run(async () => {
      const r = await api('/api/coach', { mode: answers.mode === 'semi' ? 'semi' : 'learn', context: tourMd.slice(0, 3000) + '\nIssue: ' + issue.title, history });
      setMsgs((m) => [...m, { role: 'assistant', md: r.reply, html: renderMd(r.reply) }]);
    });
  };
  const reset = () => { setStep('hero'); setView('mentor'); setAnswers({}); setRanking([]); setMsgs([]); setIssue(null); stage3d('explore'); };

  const checkPr = () => run(async () => {
    const d = await api('/api/replies/draft', { pr_url: prUrl.trim() });
    setDrafts(d); setNotice(d.drafts.length ? '' : d.note || 'No new comments to answer.');
  });
  const sendReply = (d, text) => run(async () => {
    await api('/api/replies/send', { pr_url: prUrl.trim(), items: [{ id: d.id, source: d.source, reply: text }], disclose: true });
    setDrafts({ ...drafts, drafts: drafts.drafts.filter((x) => x.id !== d.id) });
  });

  const q = qs[qi];
  const pill = usage ? `$${usage.session.cost_usd.toFixed(3)} / $${usage.session_budget_usd.toFixed(2)}` : null;
  const usedPct = usage ? Math.min(100, (usage.session.cost_usd / usage.session_budget_usd) * 100) : 0;

  return (
    <div>
      <header className="sticky top-0 z-40 border-b border-white/10 bg-zinc-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-4 py-3 md:px-8">
          <button onClick={reset} className="text-xl font-black tracking-tighter text-white">
            OSS<span className="bg-gradient-to-r from-violet-400 to-pink-400 bg-clip-text text-transparent">Mentor</span>
          </button>
          <nav className="ml-2 flex gap-1" aria-label="Main">
            {[['mentor', 'Mentor'], ['replies', 'PR replies']].map(([id, label]) => (
              <button key={id} onClick={() => setView(id)} aria-current={view === id ? 'page' : undefined}
                className={`rounded-full px-4 py-1.5 text-sm font-extrabold transition ${view === id ? 'bg-white text-zinc-950' : 'text-zinc-300 hover:bg-white/10'}`}>{label}</button>
            ))}
          </nav>
          <span className="flex-1" />
          {pill && (
            <span className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-bold text-zinc-300 sm:flex" title="Mentor time used this session">
              <span className="h-1.5 w-14 overflow-hidden rounded-full bg-white/10"><span className={`block h-full ${usedPct > 80 ? 'bg-rose-400' : 'bg-emerald-400'}`} style={{ width: usedPct + '%' }} /></span>
              {pill}
            </span>
          )}
          {me.hosted && me.login && (
            <span className="flex items-center gap-2 text-sm font-bold text-zinc-200">
              {me.avatar && <img src={me.avatar} alt="" className="h-7 w-7 rounded-full" />}@{me.login}
              <button onClick={async () => { await fetch('/auth/logout', { method: 'POST' }); setMe({ hosted: true, login: null }); reset(); }} className="rounded-full border border-white/20 px-3 py-1 text-xs font-bold hover:border-white/50">Log out</button>
            </span>
          )}
        </div>
      </header>

      {error && (
        <div role="alert" className="mx-auto mt-4 flex max-w-3xl items-start justify-between gap-4 rounded-2xl border border-rose-400/40 bg-rose-500/10 px-5 py-4 text-base font-semibold text-rose-100">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-sm font-black text-rose-200 hover:text-white" aria-label="Dismiss">✕</button>
        </div>
      )}

      <main>
        {view === 'replies' ? (
          needsLogin ? <HeroSection onLogin={() => (location.href = '/auth/login')} orgCount={orgs.length || 14} /> :
          <RepliesInbox prUrl={prUrl} onPrUrl={setPrUrl} onCheck={checkPr} drafts={drafts ? drafts.drafts : null}
            aiFlags={drafts ? drafts.ai_flags || [] : []} canPost={!!(drafts && drafts.can_post)} notice={notice} busy={busy} onSend={sendReply} />
        ) : step === 'hero' || needsLogin ? (
          <HeroSection onStart={start} onLogin={needsLogin ? () => (location.href = '/auth/login') : null} orgCount={orgs.length || 14} />
        ) : step === 'interview' && q ? (
          <InterviewStep key={q.id} q={q.q} options={q.options} multi={q.multi} index={qi} total={qs.length}
            value={answers[q.id] ?? (q.multi ? [] : '')} fitCount={qi >= 1 ? fitCount : null}
            onChange={(v) => setAnswers({ ...answers, [q.id]: v })} onBack={() => setQi(Math.max(0, qi - 1))} onNext={next} />
        ) : step === 'matches' ? (
          <MatchPodium matches={ranking} busy={busy} onChoose={choose} />
        ) : step === 'issues' ? (
          <IssueBoard issues={scout.picks} org={org ? org.org : ''} skipped={scout.skipped} busy={busy} onPick={pickIssue}
            onBack={() => { setStep('matches'); stage3d('ranked', { focus: ranking.map((x) => x.org), scores: Object.fromEntries(ranking.map((x) => [x.org, x.total])) }); }} />
        ) : step === 'work' && issue ? (
          answers.mode === 'full' ? (
            <section className="mx-auto max-w-3xl px-6 py-20">
              <h2 className="text-5xl font-black tracking-tighter text-white">Full-auto runs in Claude Code.</h2>
              <p className="mt-5 text-lg font-medium text-zinc-300">Agents that clone, fix and open pull requests need your machine and your GitHub login. Open a terminal in the project and run <code className="rounded bg-white/10 px-2 py-0.5">/oss-mentor</code>, then choose Full-auto. Use the PR replies tab here to answer reviewers.</p>
              <button onClick={() => setStep('issues')} className="mt-8 rounded-full bg-white px-8 py-3.5 font-extrabold text-zinc-950">Back to issues</button>
            </section>
          ) : (
            <WorkspaceView issue={issue} tourHtml={tourHtml} messages={msgs} onSend={send} busy={busy}
              mode={answers.mode === 'semi' ? 'semi' : 'learn'} onBack={() => setStep('issues')}
              costNote={usage ? `This session: $${usage.session.cost_usd.toFixed(3)} of $${usage.session_budget_usd.toFixed(2)}` : ''} />
          )
        ) : null}
      </main>
    </div>
  );
}
