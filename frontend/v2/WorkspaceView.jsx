// WorkspaceView.jsx
// Customize: the STEP guides (copy, commands), colors, hint buttons.
// Props: issue {repo,number,title,url,legal[]}, tourHtml (sanitised HTML), messages [{role,text?,html?}],
//        onSend(text), busy, mode ('learn'|'semi'), onBack, costNote.
// Click a step on the left to open its guide. The small circle marks it done. Commands use this issue's real repo/number.
function guideFor(issue) {
  const repo = issue.repo, name = repo.split('/')[1], n = issue.number;
  const dco = (issue.legal || []).includes('DCO');
  const sign = dco ? ' -s' : '';
  return [
    {
      name: 'Understand',
      why: 'Reading first saves hours. Maintainers can tell instantly whether you understood the project or just patched a symptom.',
      steps: [
        { text: 'Read the issue top to bottom, including every comment.', link: issue.url },
        { text: "Read the project's contributing guide and any AI or sign-off policy.", link: `https://github.com/${repo}/blob/HEAD/CONTRIBUTING.md` },
        { text: 'Open the Repo tour tab and read the "files to read first". Open each one on GitHub.' },
        { text: 'Write down in two sentences: what is wrong, and where you think it lives.' },
      ],
      watch: ['Do not start coding yet.', 'If the issue is unclear, ask one precise question on the issue instead of guessing.', 'Check nobody opened a PR for it since you picked it.'],
      done: ['I can explain what the project does in one sentence', 'I know which files are involved', 'I read the contributing guide'],
      ask: 'I am on the Understand step. Quiz me on this repo and issue to check I get it.',
    },
    {
      name: 'Reproduce',
      why: 'If you cannot see the bug, you cannot prove you fixed it. Reproducing also teaches you how to run the project.',
      steps: [
        { text: 'Fork and clone the repo.', cmd: `gh repo fork ${repo} --clone\ncd ${name}\ngit remote -v` },
        { text: 'Follow the README or contributing guide to install dependencies and build.' },
        { text: "Run the project's existing tests once, before changing anything, so you know the starting point.", note: 'The test command is in the contributing guide or the CI config under .github/workflows.' },
        { text: 'Trigger the bug, or write down exactly what you expect to see and what you see instead.' },
      ],
      watch: ['If setup fails, copy the exact error into the Coach tab. Setup problems are normal, not a sign you are bad at this.', 'Note your OS and versions; maintainers will ask.'],
      done: ['The project builds on my machine', 'Existing tests run', 'I can describe the bug in my own words'],
      ask: 'I am on the Reproduce step. Ask me what I expect to find before I look.',
    },
    {
      name: 'Fix',
      why: 'The best fix is the smallest one that solves exactly the issue. Small changes get reviewed and merged faster.',
      steps: [
        { text: 'Create a branch from fresh main.', cmd: `git fetch upstream\ngit switch -c fix/${n}-short-description upstream/HEAD` },
        { text: 'Find the code path from your Understand notes. Read the surrounding code and match its style.' },
        { text: 'Make the smallest change that fixes the issue. Resist cleaning up unrelated things.' },
        { text: 'Commit in small steps.', cmd: `git add -p\ngit commit${sign} -m "Short, clear summary (#${n})"`, note: dco ? 'This project uses DCO, so -s adds your sign-off. That is your own legal statement; read what it means first.' : 'Add -s only if the project asks for a DCO sign-off.' },
      ],
      watch: ['Stuck for 20 minutes? Use the Coach hints, they get bigger one step at a time.', 'In semi-auto mode, explain every AI-suggested chunk back before you keep it.', 'Never paste code you cannot explain line by line.'],
      done: ['My change is as small as possible', 'It matches the code style around it', 'I can explain every line'],
      ask: 'I am on the Fix step. I will describe my idea; give me a level-1 hint only.',
    },
    {
      name: 'Test',
      why: 'A test that fails before your fix and passes after is the strongest evidence that you fixed the right thing.',
      steps: [
        { text: 'Write a test for the bug and run it first. It should fail.' },
        { text: 'Run it again with your fix. It should pass.' },
        { text: "Run the project's full test suite, linter and formatter the way CI does.", note: 'Look at .github/workflows to see the exact commands CI runs.' },
        { text: 'Review your own diff like a maintainer.', cmd: 'git diff upstream/HEAD...HEAD' },
      ],
      watch: ['If the project has no tests for this area, say so honestly in the PR.', 'Fix formatting problems now; failing style checks are the most common first-PR failure.'],
      done: ['A test fails before and passes after', 'Full test suite and linters are green locally', 'My diff has no unrelated changes'],
      ask: 'I am on the Test step. Review my test and tell me what edge cases I missed.',
    },
    {
      name: 'Open PR',
      why: 'The description is how a busy maintainer decides whether to review you. Clear and honest beats long.',
      steps: [
        { text: 'Push your branch to your fork.', cmd: 'git push -u origin HEAD' },
        { text: 'Open the pull request form (you write the text, not a tool).', cmd: 'gh pr create --web' },
        { text: `Write the description in your own words. Include "Fixes #${n}", what was wrong, what you changed, and exactly how you tested it.` },
        { text: 'Say what you could not verify. Tick only the checklist items you really did.' },
        ...(issue.legal && issue.legal.length ? [{ text: `Complete the ${issue.legal.join(' / ')} requirement yourself.`, note: 'Agreements are personal and legal. We explain them but never sign for you.' }] : []),
      ],
      watch: ['If the project asks you to disclose AI help, do it plainly.', 'One PR per issue. Do not mix in other changes.', 'Do not ask for a quick review.'],
      done: ['Description is in my own words', 'Fixes #' + n + ' is included', 'Required sign-off is done by me', 'CI has started'],
      ask: 'I am on the Open PR step. Read my PR description and tell me what a maintainer would question.',
    },
    {
      name: 'Review',
      why: 'Review is a conversation, not a verdict. Most merged PRs go through at least one round of changes.',
      steps: [
        { text: 'Watch CI and fix any failure caused by your change.', cmd: 'gh pr checks' },
        { text: 'Read every review comment before answering any.', cmd: 'gh pr view --comments' },
        { text: 'Make requested changes as new commits and push. Do not force-push unless asked.', cmd: 'git add -A\ngit commit -m "Address review feedback"\ngit push' },
        { text: 'Reply to each comment briefly. Use the PR replies tab for draft help, then rewrite in your own voice.' },
        { text: 'Wait at least a week before one polite ping.' },
      ],
      watch: ['Disagreeing is fine if you explain why, kindly.', 'A closed PR is feedback, not failure. Ask what would make a second attempt work.'],
      done: ['CI is green', 'I answered every comment', 'I know what is left before merge'],
      ask: 'I am on the Review step. Help me understand this reviewer comment before I reply.',
    },
  ];
}

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
  const guides = React.useMemo(() => guideFor(issue), [issue.repo, issue.number]);
  const key = `steps:${issue.repo}#${issue.number}`;
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const [tab, setTab] = React.useState('guide');
  const [active, setActive] = React.useState(0);
  const [done, setDone] = React.useState(() => load(key, []));
  const [checks, setChecks] = React.useState(() => load(key + ':c', {}));
  const [text, setText] = React.useState('');
  const [copied, setCopied] = React.useState('');
  const endRef = React.useRef(null);

  React.useEffect(() => { try { localStorage.setItem(key, JSON.stringify(done)); } catch {} }, [done]);
  React.useEffect(() => { try { localStorage.setItem(key + ':c', JSON.stringify(checks)); } catch {} }, [checks]);
  React.useEffect(() => { if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight; }, [messages, busy, tab]);

  const current = guides.findIndex((_, i) => !done.includes(i));
  const g = guides[active];
  const toggleDone = (i) => setDone((d) => (d.includes(i) ? d.filter((x) => x !== i) : [...d, i]));
  const toggleCheck = (c) => { const k = `${active}:${c}`; setChecks((x) => ({ ...x, [k]: !x[k] })); };
  const allChecked = g.done.every((c) => checks[`${active}:${c}`]);
  const send = (t) => { const v = (t ?? text).trim(); if (!v || busy) return; onSend(v); setText(''); setTab('coach'); };
  const copy = (c) => { try { navigator.clipboard.writeText(c); setCopied(c); setTimeout(() => setCopied(''), 1500); } catch {} };
  const pct = Math.round((done.length / guides.length) * 100);
  const tabs = [['guide', `Step ${active + 1}: ${g.name}`], ['tour', 'Repo tour'], ['coach', mode === 'learn' ? 'Coach' : 'Pair programmer']];
  const H = 'h-[calc(100vh-17rem)] min-h-[420px]';

  return (
    <section className="mx-auto max-w-[1400px] px-4 py-10 md:px-8">
      <button onClick={onBack} className="mb-6 text-sm font-bold text-zinc-400 transition hover:text-white">← Back to issues</button>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-amber-300">{issue.repo} #{issue.number}</p>
          <h2 className="mt-2 max-w-3xl text-4xl leading-[1.05] text-white md:text-6xl">{issue.title}</h2>
        </div>
        <div className="w-48">
          <div className="mb-1 flex justify-between text-xs font-bold text-zinc-400"><span>Progress</span><span>{pct}%</span></div>
          <div className="h-2 rounded-full bg-white/10"><div className="h-2 rounded-full bg-gradient-to-r from-amber-100 to-yellow-500 transition-all duration-500" style={{ width: pct + '%' }} /></div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[250px_minmax(0,1fr)_280px]">
        {/* stepper: click = open the guide, circle = mark done */}
        <ol className="space-y-2 lg:sticky lg:top-24 lg:self-start" aria-label="Your journey">
          {guides.map((s, i) => {
            const isDone = done.includes(i), now = i === current, open = i === active && tab === 'guide';
            return (
              <li key={s.name} className={`flex items-stretch gap-2 rounded-2xl border-2 transition duration-150 ${open ? 'border-amber-400 bg-amber-500/20' : now ? 'border-amber-400/50 bg-amber-500/10' : 'border-white/10 bg-zinc-950/70'}`}>
                <button onClick={() => toggleDone(i)} aria-pressed={isDone} aria-label={`Mark ${s.name} ${isDone ? 'not done' : 'done'}`}
                  className="flex items-center pl-3 focus:outline-none focus-visible:ring-4 focus-visible:ring-amber-400 rounded-l-2xl">
                  <span className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-black transition hover:scale-110 ${isDone ? 'bg-emerald-400 text-zinc-950' : now ? 'bg-amber-400 text-zinc-950' : 'bg-white/10 text-zinc-400'}`}>{isDone ? '✓' : i + 1}</span>
                </button>
                <button onClick={() => { setActive(i); setTab('guide'); }} aria-current={open ? 'step' : undefined}
                  className="flex-1 rounded-r-2xl py-3 pr-3 text-left transition hover:brightness-125 focus:outline-none focus-visible:ring-4 focus-visible:ring-amber-400">
                  <span className={`block text-base font-extrabold ${isDone ? 'text-zinc-400 line-through' : 'text-white'}`}>{s.name}</span>
                  <span className="block text-xs font-medium text-zinc-400">{open ? 'Open' : 'Tap for the guide'}</span>
                </button>
              </li>
            );
          })}
        </ol>

        {/* centre */}
        <div className="min-w-0 rounded-3xl border border-white/10 bg-zinc-950/75 backdrop-blur">
          <div role="tablist" className="flex flex-wrap gap-2 border-b border-white/10 p-3">
            {tabs.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={`rounded-full px-5 py-2 text-sm font-extrabold transition ${tab === id ? 'bg-white text-zinc-950' : 'text-zinc-300 hover:bg-white/10'}`}>{label}</button>
            ))}
          </div>

          {tab === 'guide' && (
            <div className={`${H} overflow-auto p-6 md:p-8`}>
              <p className="text-sm font-bold uppercase tracking-[0.2em] text-amber-300">Step {active + 1} of {guides.length}</p>
              <h3 className="mt-1 text-6xl text-white">{g.name}</h3>
              <p className="mt-3 max-w-2xl text-lg font-medium text-zinc-300">{g.why}</p>

              <h4 className="mt-8 text-xs font-black uppercase tracking-widest text-zinc-500">Do this</h4>
              <ol className="mt-3 space-y-4">
                {g.steps.map((s, i) => (
                  <li key={i} className="flex gap-4">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/10 text-sm font-black text-zinc-200">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-base font-semibold text-zinc-100">
                        {s.text} {s.link && <a href={s.link} target="_blank" rel="noopener noreferrer" className="font-bold text-amber-300 hover:underline">Open ↗</a>}
                      </p>
                      {s.cmd && (
                        <div className="relative mt-2">
                          <pre className="overflow-auto rounded-xl border border-white/10 bg-black/60 p-3 pr-20 font-mono text-[13px] leading-relaxed text-emerald-200">{s.cmd}</pre>
                          <button onClick={() => copy(s.cmd)} className="absolute right-2 top-2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-white transition hover:bg-white/25">{copied === s.cmd ? 'Copied' : 'Copy'}</button>
                        </div>
                      )}
                      {s.note && <p className="mt-2 text-sm text-zinc-400">{s.note}</p>}
                    </div>
                  </li>
                ))}
              </ol>

              <h4 className="mt-8 text-xs font-black uppercase tracking-widest text-amber-300">Watch out</h4>
              <ul className="mt-3 space-y-2 rounded-2xl border border-amber-400/25 bg-amber-400/10 p-4">
                {g.watch.map((w) => <li key={w} className="text-sm font-medium text-amber-50/90">• {w}</li>)}
              </ul>

              <h4 className="mt-8 text-xs font-black uppercase tracking-widest text-zinc-500">Done when</h4>
              <ul className="mt-3 space-y-2">
                {g.done.map((c) => {
                  const on = !!checks[`${active}:${c}`];
                  return (
                    <li key={c}>
                      <button onClick={() => toggleCheck(c)} aria-pressed={on} className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:border-white/30">
                        <span className={`flex h-6 w-6 items-center justify-center rounded-md text-xs font-black ${on ? 'bg-emerald-400 text-zinc-950' : 'border-2 border-white/25 text-transparent'}`}>✓</span>
                        <span className={`text-base font-semibold ${on ? 'text-zinc-400 line-through' : 'text-zinc-100'}`}>{c}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-8 flex flex-wrap gap-3">
                <button onClick={() => send(g.ask)} disabled={busy} className="rounded-full border-2 border-white/25 px-6 py-3 font-bold text-white transition hover:border-amber-300 disabled:opacity-40">Ask the coach about this step</button>
                <button
                  onClick={() => { if (!done.includes(active)) toggleDone(active); if (active < guides.length - 1) setActive(active + 1); }}
                  className={`rounded-full px-7 py-3 font-extrabold transition hover:scale-105 ${allChecked ? 'bg-white text-zinc-950' : 'bg-white/10 text-zinc-300'}`}>
                  {active < guides.length - 1 ? 'Mark done, next step →' : 'Mark done'}
                </button>
              </div>
            </div>
          )}

          {tab === 'tour' && <div className={`tour ${H} overflow-auto p-6 md:p-8`} dangerouslySetInnerHTML={{ __html: tourHtml }} />}

          {tab === 'coach' && (
            <div className={`flex ${H} flex-col`}>
              <div ref={endRef} className="flex-1 space-y-3 overflow-auto p-5 md:p-6" aria-live="polite">
                {messages.length === 0 && (
                  <div className="rounded-2xl bg-white/5 p-5 text-zinc-300">
                    <p className="text-lg font-extrabold text-white">Start with your own guess.</p>
                    <p className="mt-1 text-sm">Tell me what you think causes this, or where you would look first. I will ask questions before I point at anything.</p>
                  </div>
                )}
                {messages.map((m, i) => (
                  <div key={i} className={`max-w-[92%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${m.role === 'user' ? 'ml-auto bg-amber-500/25 text-white' : 'tour bg-white/5 text-zinc-100'}`}>
                    {m.html ? <div dangerouslySetInnerHTML={{ __html: m.html }} /> : m.text}
                  </div>
                ))}
                {busy && <div className="w-16 rounded-2xl bg-white/5 px-4 py-3 text-zinc-400"><span className="animate-pulse">•••</span></div>}
              </div>
              <div className="border-t border-white/10 p-4">
                <div className="mb-3 flex flex-wrap gap-2">
                  {[['I am stuck: next hint, please', 'Bigger hint'], ['Quiz me on this code', 'Quiz me'], ['Review what I have so far', 'Review my work']].map(([t, l]) => (
                    <button key={l} onClick={() => send(t)} disabled={busy} className="rounded-full border border-white/20 px-4 py-1.5 text-xs font-bold text-zinc-200 transition hover:border-amber-300 hover:text-white disabled:opacity-40">{l}</button>
                  ))}
                </div>
                <div className="flex gap-3">
                  <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} placeholder="Type your idea or question…"
                    className="min-w-0 flex-1 rounded-full border-2 border-white/15 bg-zinc-900 px-5 py-3 text-base text-white placeholder-zinc-500 focus:border-amber-400 focus:outline-none" />
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
            <a href={issue.url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-base font-bold text-amber-300 hover:underline">Open the issue ↗</a>
            <a href={`https://github.com/${issue.repo}/blob/HEAD/CONTRIBUTING.md`} target="_blank" rel="noopener noreferrer" className="mt-1 block text-base font-bold text-amber-300 hover:underline">Contributing guide ↗</a>
            <a href={`https://github.com/${issue.repo}/pulls`} target="_blank" rel="noopener noreferrer" className="mt-1 block text-base font-bold text-amber-300 hover:underline">Open pull requests ↗</a>
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
