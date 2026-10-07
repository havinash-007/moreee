// FullAutoJob.jsx
// Customize: copy, colors, the consent wording. The whole Full-auto journey in one self-contained component:
//   consent -> run the local runner -> live progress -> REVIEW the diff -> approve -> PR link.
// Props: issue {repo,number,title,url,legal[]}, job (null | server job), command (string, shown once), error, busy,
//        onCreate({consent, signoff}), onApprove({pr_title, pr_body, cla_confirmed}), onCancel(), onBack(), onLearn().
function splitDiff(diff) {
  return (diff || '').split(/^diff --git /m).filter(Boolean).map((chunk) => {
    const lines = chunk.split('\n');
    const m = /^a\/(.+?) b\/(.+)$/.exec(lines[0]);
    return { name: m ? m[2] : lines[0], lines: lines.slice(1) };
  });
}

function DiffView({ diff }) {
  const files = React.useMemo(() => splitDiff(diff), [diff]);
  const [open, setOpen] = React.useState(() => ({ 0: true }));
  if (!files.length) return <p className="text-sm text-zinc-500">No changes.</p>;
  return (
    <div className="space-y-3">
      {files.map((f, i) => {
        const add = f.lines.filter((l) => l.startsWith('+') && !l.startsWith('+++')).length, del = f.lines.filter((l) => l.startsWith('-') && !l.startsWith('---')).length;
        return (
          <div key={f.name + i} className="overflow-hidden rounded-xl border border-white/10 bg-black/50">
            <button onClick={() => setOpen({ ...open, [i]: !open[i] })} aria-expanded={!!open[i]} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/5">
              <span className="truncate font-mono text-sm font-semibold text-white">{f.name}</span>
              <span className="shrink-0 text-xs font-bold"><span className="text-emerald-300">+{add}</span> <span className="text-rose-300">-{del}</span></span>
            </button>
            {open[i] && (
              <pre className="max-h-96 overflow-auto border-t border-white/10 p-3 font-mono text-[12.5px] leading-relaxed">
                {f.lines.map((l, j) => (
                  <div key={j} className={l.startsWith('+') && !l.startsWith('+++') ? 'bg-emerald-400/10 text-emerald-200' : l.startsWith('-') && !l.startsWith('---') ? 'bg-rose-400/10 text-rose-200' : l.startsWith('@@') ? 'text-sky-300' : 'text-zinc-400'}>{l || ' '}</div>
                ))}
              </pre>
            )}
          </div>
        );
      })}
    </div>
  );
}

const Box = ({ children, tone = 'plain' }) => (
  <div className={`rounded-3xl border p-6 backdrop-blur md:p-8 ${tone === 'warn' ? 'border-amber-400/30 bg-amber-400/10' : tone === 'ok' ? 'border-emerald-400/30 bg-emerald-400/5' : 'border-white/10 bg-zinc-950/75'}`}>{children}</div>
);

export default function FullAutoJob({
  issue = { repo: 'owner/repo', number: 1, title: 'Example', url: '#', legal: [] }, job = null, command = '', error = '', busy = false,
  onCreate = () => {}, onApprove = () => {}, onCancel = () => {}, onBack = () => {}, onLearn = () => {},
}) {
  const [consent, setConsent] = React.useState(false);
  const [signoff, setSignoff] = React.useState(false);
  const [understood, setUnderstood] = React.useState(false);
  const [cla, setCla] = React.useState(false);
  const [title, setTitle] = React.useState('');
  const [body, setBody] = React.useState('');
  const [copied, setCopied] = React.useState(false);
  const feed = React.useRef(null);
  const status = job ? job.status : 'none';

  React.useEffect(() => { if (status === 'review') { setTitle(job.pr_title || issue.title); setBody(job.pr_body || ''); } }, [status]);
  React.useEffect(() => { if (feed.current) feed.current.scrollTop = feed.current.scrollHeight; }, [job && job.events && job.events.length]);

  const Feed = () => (
    <ul ref={feed} className="mt-5 max-h-72 space-y-2 overflow-auto pr-1" aria-live="polite">
      {(job.events || []).map((e) => (
        <li key={e.id} className="flex gap-3 text-sm font-medium"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-sky-300" /><span className="text-zinc-300">{e.text}</span></li>
      ))}
    </ul>
  );
  const dco = job && job.legal && job.legal.includes('DCO');
  const needsCla = job && job.legal && job.legal.includes('CLA');
  const r = (job && job.result) || {};
  const secret = job && (job.warnings || []).some((w) => w.startsWith('secret:'));
  const canApprove = understood && title.trim() && body.trim().length >= 20 && (!needsCla || cla) && !secret && !busy;

  return (
    <section className="mx-auto max-w-4xl px-6 py-14">
      <button onClick={onBack} className="mb-6 text-sm font-bold text-zinc-400 transition hover:text-white">← Back to issues</button>
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Full-auto · {issue.repo} #{issue.number}</p>
      <h2 className="mt-2 text-5xl leading-[1] text-white md:text-7xl">{issue.title}</h2>
      {error && <p role="alert" className="mt-6 rounded-2xl border border-rose-400/40 bg-rose-500/10 px-5 py-4 text-base font-semibold text-rose-100">{error}</p>}

      <div className="mt-10 space-y-6">
        {status === 'none' && (
          <Box>
            <h3 className="text-3xl text-white">Before an AI writes anything</h3>
            <ul className="mt-4 space-y-2 text-base text-zinc-300">
              <li>• We re-check that the issue is still free and that the project allows AI-assisted contributions.</li>
              <li>• The AI works <b className="text-white">on your computer</b>, in a fork under <b className="text-white">your</b> GitHub account.</li>
              <li>• Nothing is opened until you read the change and click Approve.</li>
              <li>• You are the author. Any CLA or sign-off is your own legal act, never ours.</li>
              <li>• The AI runs the project's build and test commands on your machine. Use a throwaway VM for projects you do not trust.</li>
            </ul>
            <label className="mt-6 flex cursor-pointer items-start gap-3 text-base font-semibold text-zinc-100">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1 h-5 w-5 accent-sky-400" />
              I understand an AI will write this change, I will review it myself, and I am responsible for what I submit.
            </label>
            {(issue.legal || []).includes('DCO') && (
              <label className="mt-3 flex cursor-pointer items-start gap-3 text-base font-semibold text-zinc-100">
                <input type="checkbox" checked={signoff} onChange={(e) => setSignoff(e.target.checked)} className="mt-1 h-5 w-5 accent-sky-400" />
                This project uses a DCO. Add my "Signed-off-by" using my own git name and email (I have read what it means).
              </label>
            )}
            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={() => onCreate({ consent, signoff })} disabled={!consent || busy} className="rounded-full bg-white px-8 py-3.5 text-base font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100">{busy ? 'Checking…' : 'Run pre-flight checks →'}</button>
              <button onClick={onLearn} className="rounded-full border-2 border-white/20 px-6 py-3.5 text-base font-bold text-white hover:border-white/50">I would rather learn by hand</button>
            </div>
          </Box>
        )}

        {status === 'ready' && (
          <Box>
            <h3 className="text-3xl text-white">Checks passed. Start the worker on your machine.</h3>
            {command ? (
              <>
                <p className="mt-3 text-zinc-300">Open a terminal and paste this. It needs the <code className="rounded bg-white/10 px-1.5">gh</code> CLI (logged in) and Claude Code installed.</p>
                <div className="relative mt-4">
                  <pre className="overflow-auto rounded-xl border border-white/10 bg-black/60 p-4 pr-24 font-mono text-[13px] text-emerald-200">{command}</pre>
                  <button onClick={() => { try { navigator.clipboard.writeText(command); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {} }} className="absolute right-2 top-2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-white hover:bg-white/25">{copied ? 'Copied' : 'Copy'}</button>
                </div>
                <p className="mt-3 text-sm text-zinc-500">The token in that command works once, for this job only, and expires in 2 hours.</p>
              </>
            ) : <p className="mt-3 text-amber-200">The runner command is only shown when the job is created. Cancel this job and start a new one.</p>}
            <p className="mt-5 flex items-center gap-3 text-base font-semibold text-sky-200"><span className="h-4 w-4 animate-spin rounded-full border-2 border-sky-300 border-t-transparent" />Waiting for the runner to connect…</p>
            <Feed />
            <button onClick={onCancel} className="mt-5 text-sm font-bold text-zinc-400 hover:text-white">Cancel job</button>
          </Box>
        )}

        {status === 'running' && (
          <Box>
            <p className="text-sm font-bold uppercase tracking-widest text-sky-300">{job.stage || 'working'}</p>
            <h3 className="mt-1 flex items-center gap-3 text-3xl text-white"><span className="h-5 w-5 animate-spin rounded-full border-2 border-sky-300 border-t-transparent" />The worker is on it</h3>
            <p className="mt-2 text-zinc-400">It reproduces the bug, writes a failing test, then the smallest fix. This can take several minutes.</p>
            <Feed />
            <button onClick={onCancel} className="mt-5 text-sm font-bold text-zinc-400 hover:text-white">Cancel and discard</button>
          </Box>
        )}

        {status === 'review' && (
          <>
            <Box tone="warn">
              <h3 className="text-3xl text-white">Review before anything is opened</h3>
              <p className="mt-2 text-amber-50/90">The AI finished. Nothing has left your computer yet. Read every changed line: you are the author.</p>
              {secret && <p className="mt-3 rounded-xl bg-rose-500/20 p-3 font-bold text-rose-100">The change appears to contain a secret (key or token). It cannot be opened. Cancel this job.</p>}
            </Box>
            <Box>
              <h4 className="text-xs font-black uppercase tracking-widest text-zinc-500">What the worker says</h4>
              <p className="mt-2 text-lg text-zinc-100">{r.summary}</p>
              {(r.tests_run || []).length > 0 && <><h4 className="mt-5 text-xs font-black uppercase tracking-widest text-zinc-500">Tests it ran</h4><ul className="mt-2 space-y-1 font-mono text-sm text-emerald-200">{r.tests_run.map((t) => <li key={t}>✓ {t}</li>)}</ul></>}
              {(r.not_verified || []).length > 0 && <><h4 className="mt-5 text-xs font-black uppercase tracking-widest text-amber-300">Not verified</h4><ul className="mt-2 space-y-1 text-sm text-amber-100">{r.not_verified.map((t) => <li key={t}>• {t}</li>)}</ul></>}
              <p className="mt-5 text-xs font-semibold text-zinc-500">{(r.files || []).length} file(s) changed{r.cost_usd ? ` · worker cost about $${Number(r.cost_usd).toFixed(2)} on your Claude account` : ''}</p>
            </Box>
            <Box><h4 className="mb-3 text-xs font-black uppercase tracking-widest text-zinc-500">The change</h4><DiffView diff={r.diff} /></Box>
            <Box>
              <h4 className="text-xs font-black uppercase tracking-widest text-zinc-500">Your pull request</h4>
              <label htmlFor="prt" className="mt-3 block text-sm font-bold text-zinc-300">Title</label>
              <input id="prt" value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 w-full rounded-xl border-2 border-white/15 bg-zinc-900 px-4 py-3 text-white focus:border-sky-300 focus:outline-none" />
              <label htmlFor="prb" className="mt-4 block text-sm font-bold text-zinc-300">Description: rewrite it in your own words</label>
              <textarea id="prb" value={body} onChange={(e) => setBody(e.target.value)} rows={8} className="mt-1 w-full rounded-xl border-2 border-white/15 bg-zinc-900 p-4 text-white focus:border-sky-300 focus:outline-none" />
              <p className="mt-2 text-xs text-zinc-500">"Fixes #{issue.number}" and an AI-assistance note are added for you.</p>
              <label className="mt-5 flex cursor-pointer items-start gap-3 text-base font-semibold text-zinc-100"><input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} className="mt-1 h-5 w-5 accent-sky-400" />I read every changed line and I can explain it to a maintainer.</label>
              {needsCla && <label className="mt-3 flex cursor-pointer items-start gap-3 text-base font-semibold text-amber-100"><input type="checkbox" checked={cla} onChange={(e) => setCla(e.target.checked)} className="mt-1 h-5 w-5 accent-sky-400" />This project needs a CLA and I have signed it myself.</label>}
              {dco && job.signoff && <p className="mt-3 text-sm text-zinc-400">The commit will carry your DCO sign-off, using your git name and email.</p>}
              <div className="mt-6 flex flex-wrap gap-3">
                <button onClick={() => onApprove({ pr_title: title, pr_body: body, cla_confirmed: cla })} disabled={!canApprove} className="rounded-full bg-white px-8 py-3.5 text-base font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100">Approve and open the PR →</button>
                <button onClick={onCancel} disabled={busy} className="rounded-full border-2 border-white/20 px-6 py-3.5 text-base font-bold text-white hover:border-white/50">Discard</button>
              </div>
            </Box>
          </>
        )}

        {(status === 'approved' || status === 'opening') && (
          <Box><h3 className="flex items-center gap-3 text-3xl text-white"><span className="h-5 w-5 animate-spin rounded-full border-2 border-sky-300 border-t-transparent" />Opening your pull request</h3><p className="mt-2 text-zinc-400">The runner is committing, pushing to your fork and opening the PR with your GitHub login. Keep the terminal open.</p><Feed /></Box>
        )}

        {status === 'done' && (
          <Box tone="ok">
            <h3 className="text-4xl text-white">Your PR is open.</h3>
            <a href={job.pr_url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block break-all text-lg font-bold text-sky-300 hover:underline">{job.pr_url} ↗</a>
            <ul className="mt-5 space-y-1.5 text-zinc-300"><li>• Watch the CI checks and fix anything your change broke.</li><li>• Answer reviewers politely. The PR replies tab helps you draft, then you write it in your own voice.</li><li>• Wait at least a week before one polite ping.</li></ul>
          </Box>
        )}

        {(status === 'failed' || status === 'cancelled' || status === 'expired') && (
          <Box tone={status === 'failed' ? 'warn' : 'plain'}>
            <h3 className="text-3xl text-white">{status === 'failed' ? 'No verified fix this time' : status === 'cancelled' ? 'Job cancelled' : 'Job expired'}</h3>
            {job.error && <p className="mt-3 text-lg text-zinc-200">{job.error}</p>}
            <p className="mt-2 text-zinc-400">Nothing was pushed or opened. That is a normal outcome for hard or unclear issues.</p>
            <Feed />
            <div className="mt-5 flex flex-wrap gap-3"><button onClick={onBack} className="rounded-full bg-white px-6 py-3 font-extrabold text-zinc-950">Pick another issue</button><button onClick={onLearn} className="rounded-full border-2 border-white/20 px-6 py-3 font-bold text-white hover:border-white/50">Try it by hand with a coach</button></div>
          </Box>
        )}
      </div>
    </section>
  );
}
