// BrowseCatalogue.jsx
// Customize: copy, filter chips, card layout. Search and filter every organisation we know about.
// Props: data {total, items, facets:{source,language,domain}, page, size}, filters {q, source, language, domain, page},
//        onFilters(partial), onChoose(item), loading, status {size, generated_at, age_days, refreshing, counts}, busy.
const SOURCES = [
  ['', 'All'], ['curated', 'Hand-picked'], ['gsoc', 'Google Summer of Code'], ['lfx', 'LFX Mentorship'],
  ['cncf', 'CNCF'], ['apache', 'Apache'], ['beginner-list', 'Beginner lists'],
];

function badges(o) {
  const b = [];
  (o.gsoc_years || []).slice().sort().slice(-2).forEach((y) => b.push([`GSoC ${y}`, 'bg-sky-400/15 text-sky-200']));
  if (o.lfx) b.push(['LFX Mentorship', 'bg-cyan-400/15 text-cyan-200']);
  if (o.cncf && o.cncf !== 'landscape') b.push([`CNCF ${o.cncf}`, 'bg-emerald-400/15 text-emerald-200']);
  if (o.apache) b.push(['Apache', 'bg-orange-400/15 text-orange-200']);
  if ((o.sources || []).includes('beginner-list')) b.push(['Beginner list', 'bg-white/10 text-zinc-200']);
  return b;
}

export default function BrowseCatalogue({
  data = null, filters = { q: '', source: '', language: '', domain: '', page: 1 }, onFilters = () => {}, onChoose = () => {},
  loading = false, status = null, busy = false,
}) {
  const [q, setQ] = React.useState(filters.q);
  React.useEffect(() => { const t = setTimeout(() => q !== filters.q && onFilters({ q, page: 1 }), 300); return () => clearTimeout(t); }, [q]);
  const f = data ? data.facets : { source: {}, language: {}, domain: {} };
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const Chip = ({ on, children, onClick }) => (
    <button onClick={onClick} aria-pressed={on} className={`rounded-full border px-4 py-1.5 text-sm font-bold transition ${on ? 'border-sky-300 bg-sky-300/15 text-white' : 'border-white/15 text-zinc-300 hover:border-white/40'}`}>{children}</button>
  );
  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Browse everything</p>
      <h2 className="mt-3 text-6xl leading-[0.95] text-white md:text-8xl">
        {status ? status.size.toLocaleString() : 'Every'} <em className="bg-gradient-to-r from-sky-200 via-cyan-200 to-orange-300 bg-clip-text pr-1 text-transparent">open-source projects.</em>
      </h2>
      <p className="mt-5 max-w-3xl text-lg font-medium text-zinc-300">
        Pulled live from Google Summer of Code, LFX Mentorship, the CNCF landscape, Apache and beginner lists, plus our hand-picked favourites.
        {status && status.generated_at ? ` Updated ${status.age_days === 0 ? 'today' : `${status.age_days} day${status.age_days === 1 ? '' : 's'} ago`}.` : ''}
        {status && status.refreshing ? ' Refreshing now…' : ''}
      </p>

      <div className="mt-8">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or topic: kubernetes, music, accessibility…" aria-label="Search organisations"
          className="w-full rounded-full border-2 border-white/15 bg-zinc-950/80 px-6 py-4 text-lg text-white placeholder-zinc-500 focus:border-sky-300 focus:outline-none" />
        <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="Programme">
          {SOURCES.map(([id, label]) => (
            <Chip key={id} on={filters.source === id} onClick={() => onFilters({ source: id, page: 1 })}>
              {label}{id && f.source[id] !== undefined ? <span className="ml-2 text-xs text-zinc-400">{f.source[id]}</span> : null}
            </Chip>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Language">
          <Chip on={!filters.language} onClick={() => onFilters({ language: '', page: 1 })}>Any language</Chip>
          {Object.entries(f.language).slice(0, 14).map(([l, n]) => <Chip key={l} on={filters.language === l} onClick={() => onFilters({ language: l, page: 1 })}>{l}<span className="ml-2 text-xs text-zinc-400">{n}</span></Chip>)}
        </div>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Field">
          <Chip on={!filters.domain} onClick={() => onFilters({ domain: '', page: 1 })}>Any field</Chip>
          {Object.entries(f.domain).map(([d, n]) => <Chip key={d} on={filters.domain === d} onClick={() => onFilters({ domain: d, page: 1 })}>{d}<span className="ml-2 text-xs text-zinc-400">{n}</span></Chip>)}
        </div>
      </div>

      <p className="mt-8 text-sm font-bold text-zinc-400" aria-live="polite">{loading ? 'Searching…' : data ? `${data.total.toLocaleString()} match${data.total === 1 ? '' : 'es'}` : ''}</p>

      <div className={`mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${loading ? 'opacity-60' : ''}`}>
        {(data ? data.items : []).map((o) => (
          <article key={(o.repo || o.github) + o.name} className="flex flex-col rounded-2xl border border-white/10 bg-zinc-950/75 p-5 backdrop-blur transition duration-150 hover:-translate-y-0.5 hover:border-sky-300/50">
            <h3 className="text-2xl leading-tight text-white">{o.name}</h3>
            <p className="mt-1 text-xs font-semibold text-zinc-500">{o.repo || o.github}{o.stars ? ` · ★ ${o.stars >= 1000 ? (o.stars / 1000).toFixed(1) + 'k' : o.stars}` : ''}{o.gfi ? ` · ${o.gfi} beginner issues open` : ''}</p>
            <p className="mt-2 flex-1 text-sm text-zinc-400">{o.notes || 'No description.'}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {badges(o).map(([t, c]) => <span key={t} className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${c}`}>{t}</span>)}
              {o.languages.slice(0, 3).map((l) => <span key={l} className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs font-bold text-zinc-200">{l}</span>)}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button onClick={() => onChoose(o)} disabled={busy} className="rounded-full bg-white px-5 py-2 text-sm font-extrabold text-zinc-950 transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100">Find me an issue →</button>
              {o.ideas_url && <a href={o.ideas_url} target="_blank" rel="noopener noreferrer" className="text-xs font-bold text-sky-300 hover:underline">GSoC ideas ↗</a>}
            </div>
            {o.rated === 'auto' && <p className="mt-2 text-[11px] font-semibold text-zinc-600">Auto-rated from live data</p>}
          </article>
        ))}
      </div>
      {data && data.items.length === 0 && !loading && <p className="mt-6 rounded-2xl bg-white/5 p-6 text-zinc-300">Nothing matches those filters. Try removing one.</p>}

      {pages > 1 && (
        <nav className="mt-10 flex items-center justify-center gap-4" aria-label="Pages">
          <button onClick={() => onFilters({ page: filters.page - 1 })} disabled={filters.page <= 1} className="rounded-full border-2 border-white/20 px-6 py-2.5 font-bold text-white disabled:opacity-30">← Prev</button>
          <span className="text-sm font-bold text-zinc-400">Page {filters.page} of {pages}</span>
          <button onClick={() => onFilters({ page: filters.page + 1 })} disabled={filters.page >= pages} className="rounded-full border-2 border-white/20 px-6 py-2.5 font-bold text-white disabled:opacity-30">Next →</button>
        </nav>
      )}
    </section>
  );
}
