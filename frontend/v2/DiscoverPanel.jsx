// DiscoverPanel.jsx
// Customize: copy, card styling. Shows (1) runner-up organisations from our catalogue and (2) projects found live on GitHub.
// Props: others [{org,github,total,max,languages,domains,notes,legal}], found (null | [{repo,owner,description,language,stars,pushed,topics,license,url}]),
//        loading, error, catalogueSize, onChooseOrg(org), onChooseRepo(repo), onDiscover(), busy.
export default function DiscoverPanel({
  others = [], found = null, loading = false, error = '', catalogueSize = 0,
  onChooseOrg = () => {}, onChooseRepo = () => {}, onDiscover = () => {}, busy = false,
}) {
  const [showAll, setShowAll] = React.useState(false);
  const list = showAll ? others : others.slice(0, 6);
  const stars = (n) => (n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n));
  return (
    <section className="mx-auto max-w-6xl px-6 pb-24">
      <div className="border-t border-white/10 pt-14">
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">More to explore</p>
        <h3 className="mt-3 text-5xl leading-[0.95] text-white md:text-7xl">
          Not feeling the top three?
        </h3>
        <p className="mt-4 max-w-2xl text-lg font-medium text-zinc-300">
          We scored {catalogueSize || 'many'} organisations for you. Here are the next best, and we can search GitHub live for projects with open good-first issues that match your languages and interests.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((o, i) => (
            <article key={o.org} className="flex flex-col rounded-2xl border border-white/10 bg-zinc-950/70 p-5 backdrop-blur transition duration-150 hover:-translate-y-0.5 hover:border-sky-400/50">
              <div className="flex items-start justify-between gap-3">
                <h4 className="text-xl font-black leading-tight text-white"><span className="mr-2 text-zinc-500">#{i + 4}</span>{o.org}</h4>
                <span className="text-2xl font-black text-white">{o.total}<span className="text-xs font-bold text-zinc-500">/{o.max}</span></span>
              </div>
              <p className="mt-2 flex-1 text-sm text-zinc-400">{o.notes}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {o.languages.slice(0, 3).map((l) => <span key={l} className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-bold text-zinc-200">{l}</span>)}
                {o.domains.slice(0, 2).map((d) => <span key={d} className="rounded-full bg-sky-500/15 px-2.5 py-0.5 text-xs font-bold text-sky-200">{d}</span>)}
              </div>
              <button onClick={() => onChooseOrg(o)} disabled={busy} className="mt-4 rounded-full border-2 border-white/25 px-5 py-2.5 text-sm font-extrabold text-white transition hover:border-white/60 disabled:opacity-40">Find me an issue here →</button>
            </article>
          ))}
        </div>
        {others.length > 6 && (
          <button onClick={() => setShowAll(!showAll)} className="mt-6 text-sm font-extrabold text-sky-300 hover:underline">{showAll ? 'Show fewer' : `Show ${others.length - 6} more matches`}</button>
        )}

        <div className="mt-14 rounded-3xl border border-emerald-400/30 bg-emerald-400/5 p-6 md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h4 className="text-2xl font-black text-white">Search GitHub live</h4>
              <p className="mt-1 max-w-xl text-sm text-zinc-400">Active projects (pushed in the last 90 days) with several open good-first issues, in your languages and topics. They are not rated or policy-checked until you pick one.</p>
            </div>
            <button onClick={onDiscover} disabled={loading} className="rounded-full bg-emerald-300 px-7 py-3 font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-50 disabled:hover:scale-100">{loading ? 'Searching…' : found ? 'Search again' : 'Find more projects →'}</button>
          </div>
          {error && <p className="mt-4 text-sm font-semibold text-rose-300">{error}</p>}
          {found && found.length === 0 && <p className="mt-6 text-zinc-400">Nothing new turned up for that mix. Try changing your languages or interests.</p>}
          {found && found.length > 0 && (
            <ul className="mt-6 grid gap-3 md:grid-cols-2">
              {found.map((r) => (
                <li key={r.repo} className="flex flex-col rounded-2xl border border-white/10 bg-zinc-950/70 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-lg font-black text-white hover:underline">{r.repo} ↗</a>
                    <span className="shrink-0 text-sm font-bold text-amber-300">★ {stars(r.stars)}</span>
                  </div>
                  <p className="mt-1 flex-1 text-sm text-zinc-400">{r.description || 'No description.'}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs font-bold">
                    {r.language && <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-zinc-200">{r.language}</span>}
                    {r.license && <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-zinc-300">{r.license}</span>}
                    {r.pushed && <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-zinc-400">pushed {r.pushed}</span>}
                    {r.topics.slice(0, 3).map((t) => <span key={t} className="rounded-full bg-emerald-400/15 px-2.5 py-0.5 text-emerald-200">{t}</span>)}
                  </div>
                  <button onClick={() => onChooseRepo(r)} disabled={busy} className="mt-3 rounded-full border-2 border-white/25 px-5 py-2 text-sm font-extrabold text-white transition hover:border-white/60 disabled:opacity-40">Check this project →</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
