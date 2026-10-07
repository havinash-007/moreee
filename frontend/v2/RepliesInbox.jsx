// RepliesInbox.jsx
// Customize: copy, colors. Drafts are suggestions: students edit them into their own words.
// Props: prUrl, onPrUrl(v), onCheck(), drafts [{id,user,comment,path,kind,needs_code,reply,source}],
//        aiFlags [{file,line}], canPost, notice, busy, onSend(draft, editedText).
export default function RepliesInbox({
  prUrl = '', onPrUrl = () => {}, onCheck = () => {}, drafts = null, aiFlags = [], canPost = false,
  notice = '', busy = false, onSend = () => {},
}) {
  const [sel, setSel] = React.useState(0);
  const [edits, setEdits] = React.useState({});
  const list = drafts || [];
  const d = list[Math.min(sel, list.length - 1)];
  const text = d ? (edits[d.id] ?? d.reply) : '';
  const tone = { actionable: 'bg-rose-400/20 text-rose-200', question: 'bg-cyan-400/20 text-cyan-200', nit: 'bg-zinc-400/20 text-zinc-200', praise: 'bg-emerald-400/20 text-emerald-200', other: 'bg-white/10 text-zinc-200' };

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Reviewer replies</p>
      <h2 className="mt-3 text-6xl leading-[0.95] text-white md:text-8xl">
        Answer like <em className="bg-gradient-to-r from-sky-200 via-cyan-200 to-orange-300 bg-clip-text pr-1 text-transparent">you mean it.</em>
      </h2>
      <p className="mt-5 max-w-2xl text-lg font-medium text-zinc-300">Paste your pull request. We read the new comments and draft replies. You rewrite them in your own voice.</p>

      <div className="mt-10 flex flex-wrap gap-3">
        <input value={prUrl} onChange={(e) => onPrUrl(e.target.value)} placeholder="https://github.com/owner/repo/pull/123"
          className="min-w-0 flex-1 rounded-full border-2 border-white/15 bg-zinc-900/80 px-6 py-4 text-base text-white placeholder-zinc-500 focus:border-sky-400 focus:outline-none" />
        <button onClick={onCheck} disabled={busy || !prUrl.trim()} className="rounded-full bg-white px-9 py-4 text-base font-extrabold text-zinc-950 transition hover:scale-105 hover:brightness-110 disabled:opacity-40 disabled:hover:scale-100">
          {busy ? 'Reading…' : 'Check comments →'}
        </button>
      </div>

      {notice && <p className="mt-6 rounded-2xl bg-white/5 p-4 text-base font-semibold text-zinc-300">{notice}</p>}

      {aiFlags.length > 0 && (
        <div className="mt-6 rounded-2xl border border-amber-400/40 bg-amber-400/10 p-5">
          <p className="font-black text-amber-200">This project restricts AI-written messages, so sending is off.</p>
          <p className="mt-1 text-sm text-amber-100/90">Use the drafts as ideas only. Write your own reply and post it yourself.</p>
          <p className="mt-2 border-l-2 border-amber-400/60 pl-3 text-xs italic text-amber-100/80">“{aiFlags[0].line}” ({aiFlags[0].file})</p>
        </div>
      )}

      {list.length > 0 && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <ul className="space-y-2">
            {list.map((x, i) => (
              <li key={x.id}>
                <button onClick={() => setSel(i)} className={`w-full rounded-2xl border-2 p-4 text-left transition hover:scale-[1.01] ${i === sel ? 'border-sky-400 bg-sky-500/15' : 'border-white/10 bg-zinc-950/70'}`}>
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-white">@{x.user}</span>
                    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-black uppercase ${tone[x.kind] || tone.other}`}>{x.kind}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-zinc-400">{x.comment}</p>
                </button>
              </li>
            ))}
          </ul>
          {d && (
            <div className="rounded-3xl border border-white/10 bg-zinc-950/75 p-6 backdrop-blur">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-extrabold text-white">@{d.user}</span>
                {d.needs_code && <span className="rounded-full bg-amber-400/20 px-3 py-0.5 text-xs font-black text-amber-200">needs a code change from you</span>}
                {d.path && <span className="text-xs font-semibold text-zinc-500">{d.path}</span>}
              </div>
              <p className="mt-3 whitespace-pre-wrap border-l-4 border-white/15 pl-4 text-zinc-300">{d.comment}</p>
              {d.reply ? (
                <>
                  <label className="mt-6 block text-xs font-black uppercase tracking-widest text-zinc-500" htmlFor="reply-box">Draft reply (edit it!)</label>
                  <textarea id="reply-box" value={text} onChange={(e) => setEdits({ ...edits, [d.id]: e.target.value })} rows={6}
                    className="mt-2 w-full rounded-2xl border-2 border-white/15 bg-zinc-900 p-4 text-base text-white focus:border-sky-400 focus:outline-none" />
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button onClick={() => navigator.clipboard && navigator.clipboard.writeText(text)} className="rounded-full border-2 border-white/25 px-6 py-3 font-bold text-white transition hover:border-white/60">Copy</button>
                    {canPost && <button onClick={() => onSend(d, text)} disabled={busy} className="rounded-full bg-white px-7 py-3 font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40">Approve and send</button>}
                  </div>
                </>
              ) : <p className="mt-6 text-zinc-500">No reply needed for this one.</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
