// app.jsx: the shell. Owns state and API calls; the six components do all the visual work.
// Flow: hero -> interview -> matches -> issues -> workspace, plus a Replies tab.

const renderMd = (md) => {
  // The model sometimes forgets the ```mermaid label, so also treat an unlabeled block that starts like a diagram as one.
  const html = marked.parse(md || '')
    .replace(/<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g, '<pre class="mermaid">$1</pre>')
    .replace(/<pre><code(?: class="language-[a-z]*")?>\s*((?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram)[\s\S]*?)<\/code><\/pre>/g, '<pre class="mermaid">$1</pre>');
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
  if (r.status === 404 && j.detail === 'Not Found') { const e = new Error('The server is older than this page. Restart it with ./run.sh and reload.'); e.kind = 'stale'; throw e; }
  if (!r.ok) { const e = new Error(FRIENDLY[j.kind] || j.error || j.detail || 'Something went wrong'); e.kind = j.kind; throw e; }
  return j;
}

// Reads newline-delimited JSON events from the scout: calls onStep for progress, returns the final result.
async function streamScout(body, onStep) {
  const r = await fetch('/api/scout/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (r.status === 401) { const e = new Error('login'); e.login = true; throw e; }
  if (!r.ok || !r.body) { const j = await r.json().catch(() => ({})); throw new Error(FRIENDLY[j.kind] || j.error || 'Scouting failed. Try again.'); }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = '', result = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
      if (!line) continue;
      const ev = JSON.parse(line);
      if (ev.type === 'step') onStep(ev.text);
      else if (ev.type === 'error') throw new Error(FRIENDLY[ev.kind] || ev.error);
      else if (ev.type === 'result') result = ev;
    }
    if (done) break;
  }
  if (!result) throw new Error('Scouting ended unexpectedly. Try again.');
  return result;
}

export default function App() {
  const { HeroSection, InterviewStep, MatchPodium, DiscoverPanel, IssueBoard, WorkspaceView, RepliesInbox, ScoutProgress, BrowseCatalogue } = window.OSS;
  const [view, setView] = React.useState('mentor');
  const [step, setStep] = React.useState('hero');
  const [me, setMe] = React.useState({ hosted: false, login: 'local' });
  const [orgs, setOrgs] = React.useState([]);
  const [qs, setQs] = React.useState([]);
  const [qi, setQi] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [ranking, setRanking] = React.useState([]);
  const [others, setOthers] = React.useState([]);
  const [catSize, setCatSize] = React.useState(0);
  const [found, setFound] = React.useState(null);
  const [discLoading, setDiscLoading] = React.useState(false);
  const [discError, setDiscError] = React.useState('');
  const [org, setOrg] = React.useState(null);
  const [catStatus, setCatStatus] = React.useState(null);
  const [bFilters, setBFilters] = React.useState({ q: '', source: '', language: '', domain: '', page: 1 });
  const [bData, setBData] = React.useState(null);
  const [bLoading, setBLoading] = React.useState(false);
  const [scoutSteps, setScoutSteps] = React.useState([]);
  const [scouting, setScouting] = React.useState(false);
  const [issueNotice, setIssueNotice] = React.useState('');
  const [checking, setChecking] = React.useState(-1);
  const [scout, setScout] = React.useState({ picks: [], skipped: [] });
  const [issue, setIssue] = React.useState(null);
  const [tourHtml, setTourHtml] = React.useState('');
  const [tourMd, setTourMd] = React.useState('');
  const [structure, setStructure] = React.useState([]);
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
      try { setCatStatus(await api('/api/catalogue/status')); } catch {}
      refreshUsage();
    })();
  }, []);

  // an error belongs to the screen it happened on: clear it when the student moves on
  React.useEffect(() => { setError(''); }, [view, step]);

  // browse: refetch whenever the filters change
  React.useEffect(() => {
    if (view !== 'browse') return;
    let live = true;
    setBLoading(true);
    const qs = new URLSearchParams({ q: bFilters.q, source: bFilters.source, language: bFilters.language, domain: bFilters.domain, page: bFilters.page, size: 24 });
    api('/api/catalogue/browse?' + qs).then((d) => live && setBData(d)).catch((e) => live && setError(e.message)).finally(() => live && setBLoading(false));
    return () => { live = false; };
  }, [view, bFilters]);

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

  // blur the galaxy behind content screens; keep it crisp on the hero and during the interview
  React.useEffect(() => {
    if (!window.Scene) return;
    const px = view === 'replies' || view === 'browse' ? 12 : step === 'matches' ? 6 : step === 'issues' ? 10 : step === 'work' ? 12 : 0;
    Scene.setBlur(px);
  }, [view, step, orgs.length]);

  const start = () => run(async () => {
    if (!qs.length) setQs(await api('/api/questions'));
    setQi(0); setStep('interview'); stage3d('explore');
  });
  const next = () => {
    if (qi < qs.length - 1) return setQi(qi + 1);
    run(async () => {
      const m = await api('/api/match', answers);
      const r = m.ranking;
      setRanking(r); setOthers(m.others || []); setCatSize(m.catalogue_size || 0); setFound(null); setDiscError(''); setStep('matches');
      stage3d('ranked', { focus: r.map((x) => x.org), scores: Object.fromEntries(r.map((x) => [x.org, x.total])) });
    });
  };
  const back3d = () => stage3d('ranked', { focus: ranking.map((x) => x.org), scores: Object.fromEntries(ranking.map((x) => [x.org, x.total])) });
  const allOrgs = [...ranking, ...others];
  const scoutOrg = async (o, repo) => {
    setBusy(true); setError(''); setIssueNotice(''); setScoutSteps([]); setScouting(true); setOrg(o); stage3d('selected', { pick: o.org });
    try {
      const fallbacks = repo ? [] : allOrgs.map((x) => x.github).filter((g) => g.toLowerCase() !== o.github.toLowerCase()).slice(0, 2);
      const res = await streamScout({ org: o.github, repo: repo || null, profile: answers, fallback_orgs: fallbacks }, (t) => setScoutSteps((s) => [...s, t]));
      const used = res.org_used ? (allOrgs.find((x) => x.github.toLowerCase() === res.org_used.toLowerCase()) || { org: res.org_used, github: res.org_used }) : o;
      setOrg(used); setScout(res); setStep('issues'); stage3d('working', { pick: used.org });
      if (res.org_used && used.github.toLowerCase() !== o.github.toLowerCase()) setIssueNotice(`${o.org} had nothing free right now, so we searched ${used.org} for you instead.`);
    } catch (e) { back3d(); if (e.login) setMe({ hosted: true, login: null }); else setError(e.message); }
    finally { setScouting(false); setBusy(false); refreshUsage(); }
  };
  const choose = (i) => scoutOrg(ranking[i]);
  const chooseRepo = (r) => scoutOrg({ org: r.repo, github: r.owner }, r.repo);
  const discover = async () => {
    setDiscLoading(true); setDiscError('');
    try { setFound((await api(`/api/discover?languages=${encodeURIComponent((answers.languages || []).join(','))}&interests=${encodeURIComponent((answers.interests || []).join(','))}`)).repos); }
    catch (e) { if (e.login) setMe({ hosted: true, login: null }); else setDiscError(e.message); }
    finally { setDiscLoading(false); }
  };
  const verifyPick = async (i) => {
    const p = scout.picks[i];
    const v = await api('/api/verify', { repo: p.repo, number: p.number });
    if (v.ok) { setScout((sc) => ({ ...sc, picks: sc.picks.map((x, j) => (j === i ? { ...x, verified_at: v.checked_at } : x)) })); return true; }
    setScout((sc) => ({ ...sc, picks: sc.picks.filter((_, j) => j !== i) }));
    setIssueNotice(`#${p.number} in ${p.repo} just changed: ${v.reason}. We removed it so you do not waste time on it.`);
    return false;
  };
  const recheck = async (i) => { setChecking(i); setError(''); try { await verifyPick(i); } catch (e) { setError(e.message); } finally { setChecking(-1); } };
  const pickIssue = (i) => run(async () => {
    if (!(await verifyPick(i))) return;
    const p = scout.picks[i];
    const t = await api('/api/tour', { repo: p.repo, issue_title: p.title, level: answers.skill || 'beginner' });
    setIssue(p); setTourMd(t.markdown); setStructure((t.overview && t.overview.top_level) || []); setTourHtml(renderMd(t.markdown)); setMsgs([]); setStep('work');
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
          <button onClick={reset} className="display text-3xl leading-none text-white">
            OSS <em className="bg-gradient-to-r from-sky-200 via-cyan-200 to-orange-300 bg-clip-text pr-1 text-transparent">Mentor</em>
          </button>
          <nav className="ml-2 flex gap-1" aria-label="Main">
            {[['mentor', 'Mentor'], ['browse', 'Browse'], ['replies', 'PR replies']].map(([id, label]) => (
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

      {scouting && <ScoutProgress title={org ? `Finding your issue in ${org.org}` : 'Scouting for you'} steps={scoutSteps} />}

      {error && (
        <div role="alert" className="mx-auto mt-4 flex max-w-3xl items-start justify-between gap-4 rounded-2xl border border-rose-400/40 bg-rose-500/10 px-5 py-4 text-base font-semibold text-rose-100">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-sm font-black text-rose-200 hover:text-white" aria-label="Dismiss">✕</button>
        </div>
      )}

      <main>
        {view === 'browse' ? (
          <BrowseCatalogue data={bData} filters={bFilters} onFilters={(p) => setBFilters((f) => ({ ...f, ...p }))} loading={bLoading} status={catStatus} busy={busy}
            onChoose={(o) => { setView('mentor'); scoutOrg({ org: o.name, github: o.github }, o.repo); }} />
        ) : view === 'replies' ? (
          needsLogin ? <HeroSection onLogin={() => (location.href = '/auth/login')} orgCount={(catStatus && catStatus.size) || orgs.length || 14} /> :
          <RepliesInbox prUrl={prUrl} onPrUrl={setPrUrl} onCheck={checkPr} drafts={drafts ? drafts.drafts : null}
            aiFlags={drafts ? drafts.ai_flags || [] : []} canPost={!!(drafts && drafts.can_post)} notice={notice} busy={busy} onSend={sendReply} />
        ) : step === 'hero' || needsLogin ? (
          <HeroSection onStart={start} onLogin={needsLogin ? () => (location.href = '/auth/login') : null} orgCount={(catStatus && catStatus.size) || orgs.length || 14} />
        ) : step === 'interview' && q ? (
          <InterviewStep key={q.id} q={q.q} options={q.options} multi={q.multi} index={qi} total={qs.length}
            value={answers[q.id] ?? (q.multi ? [] : '')} fitCount={qi >= 1 ? fitCount : null}
            onChange={(v) => setAnswers({ ...answers, [q.id]: v })} onBack={() => setQi(Math.max(0, qi - 1))} onNext={next} />
        ) : step === 'matches' ? (
          <>
            <MatchPodium matches={ranking} busy={busy} onChoose={choose} />
            <DiscoverPanel others={others} found={found} loading={discLoading} error={discError} catalogueSize={catSize} busy={busy}
              onChooseOrg={(o) => scoutOrg(o)} onChooseRepo={chooseRepo} onDiscover={discover} />
          </>
        ) : step === 'issues' ? (
          <IssueBoard issues={scout.picks} org={org ? org.org : ''} skipped={scout.skipped} stats={scout.stats} notice={issueNotice} checking={checking}
            alternatives={allOrgs.filter((x) => !org || x.github.toLowerCase() !== org.github.toLowerCase()).slice(0, 4)} busy={busy}
            onPick={pickIssue} onRecheck={recheck} onTry={(a) => scoutOrg(a)}
            onBack={() => { setStep('matches'); back3d(); }} />
        ) : step === 'work' && issue ? (
          answers.mode === 'full' ? (
            <section className="mx-auto max-w-3xl px-6 py-20">
              <h2 className="text-5xl font-black tracking-tighter text-white">Full-auto runs in Claude Code.</h2>
              <p className="mt-5 text-lg font-medium text-zinc-300">Agents that clone, fix and open pull requests need your machine and your GitHub login. Open a terminal in the project and run <code className="rounded bg-white/10 px-2 py-0.5">/oss-mentor</code>, then choose Full-auto. Use the PR replies tab here to answer reviewers.</p>
              <button onClick={() => setStep('issues')} className="mt-8 rounded-full bg-white px-8 py-3.5 font-extrabold text-zinc-950">Back to issues</button>
            </section>
          ) : (
            <WorkspaceView issue={issue} tourHtml={tourHtml} structure={structure} messages={msgs} onSend={send} busy={busy}
              mode={answers.mode === 'semi' ? 'semi' : 'learn'} onBack={() => setStep('issues')}
              costNote={usage ? `This session: $${usage.session.cost_usd.toFixed(3)} of $${usage.session_budget_usd.toFixed(2)}` : ''} />
          )
        ) : null}
      </main>
    </div>
  );
}
