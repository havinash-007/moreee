// MatchPodium.jsx
// Customize: accent gradient, labels, the "why" sentence builder.
// Props: matches [{org, total, max, parts:{language,interest,beginner,goal,setup}, legal, notes, languages, gate}],
//        onChoose(index), busy. Radar chart is hand-drawn SVG: no chart library.
const AXES = [
  ['language', 'Language'],
  ['interest', 'Interest'],
  ['beginner', 'Friendly'],
  ['goal', 'Goal'],
  ['setup', 'Setup'],
];
const PHRASE = {
  language: 'your languages',
  interest: 'your interests',
  beginner: 'a beginner-friendly culture',
  goal: 'your goal',
  setup: 'your machine',
};

function why(parts) {
  const sorted = Object.entries(parts).sort((a, b) => b[1] - a[1]);
  const best = sorted.slice(0, 2).map(([k]) => PHRASE[k]);
  const [wk, wv] = sorted[sorted.length - 1];
  const warn = wv < 3.5 ? ` Watch out: weaker fit on ${PHRASE[wk]}.` : '';
  return `Strong match on ${best[0]} and ${best[1]}.${warn}`;
}

function Radar({ parts, hot }) {
  const R = 54, C = 80;
  const pt = (i, r) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length;
    return [C + Math.cos(a) * r, C + Math.sin(a) * r];
  };
  const poly = AXES.map(([k], i) => pt(i, (Math.min(parts[k], 5) / 5) * R).join(',')).join(' ');
  return (
    <svg viewBox="-22 -6 204 172" className="mx-auto h-44 w-52" role="img" aria-label="Fit across five factors">
      {[0.4, 0.7, 1].map((s) => (
        <polygon key={s} points={AXES.map((_, i) => pt(i, R * s).join(',')).join(' ')} fill="none" stroke="rgba(255,255,255,0.12)" />
      ))}
      <polygon points={poly} fill={hot ? 'rgba(229,192,123,0.30)' : 'rgba(94,234,212,0.20)'} stroke={hot ? '#E5C07B' : '#5EEAD4'} strokeWidth="2" />
      {AXES.map(([k, label], i) => {
        const [x, y] = pt(i, R + 15);
        return (
          <text key={k} x={x} y={y} fontSize="9" fontWeight="700" fill="#a1a1aa" textAnchor="middle" dominantBaseline="middle">
            {label}
          </text>
        );
      })}
    </svg>
  );
}

export default function MatchPodium({ matches = [], onChoose = () => {}, busy = false }) {
  // podium order: #2, #1, #3
  const order = matches.length === 3 ? [1, 0, 2] : matches.map((_, i) => i);
  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-amber-300">Your matches</p>
      <h2 className="mt-3 text-6xl leading-[0.95] text-white md:text-8xl">
        Meet your <em className="bg-gradient-to-r from-amber-100 to-yellow-500 bg-clip-text pr-1 text-transparent">top three.</em>
      </h2>
      <p className="mt-5 max-w-2xl text-lg font-medium text-zinc-300">
        Scored on language, interest, beginner-friendliness, goal and setup. Ratings are our judgement, so we double-check live before you commit.
      </p>
      <div className="mt-14 grid items-end gap-6 md:grid-cols-3">
        {order.map((i) => {
          const m = matches[i];
          const first = i === 0;
          return (
            <article
              key={m.org}
              className={`relative rounded-3xl border p-6 backdrop-blur transition duration-200 hover:-translate-y-1 ${
                first
                  ? 'border-amber-300/60 bg-gradient-to-b from-amber-500/15 to-zinc-950/80 shadow-[0_0_80px_-20px_rgba(229,192,123,0.5)] md:-translate-y-6 md:pb-8'
                  : 'border-white/10 bg-zinc-950/70'
              } ${m.gate ? 'opacity-60' : ''}`}
            >
              <span className="display absolute -top-6 left-6 text-8xl leading-none text-transparent [-webkit-text-stroke:2px_rgba(255,255,255,0.35)]">
                {i + 1}
              </span>
              <div className="mt-8 flex items-start justify-between gap-3">
                <h3 className="text-4xl leading-tight text-white">{m.org}</h3>
                <div className="text-right">
                  <div className="display text-5xl text-white">{m.total}</div>
                  <div className="text-xs font-bold text-zinc-500">of {m.max}</div>
                </div>
              </div>
              {first && (
                <span className="mt-2 inline-block rounded-full bg-emerald-400 px-3 py-1 text-xs font-black uppercase tracking-wider text-zinc-950">
                  Best fit
                </span>
              )}
              <Radar parts={m.parts} hot={first} />
              <p className="text-base font-semibold leading-snug text-zinc-200">{why(m.parts)}</p>
              <p className="mt-2 text-sm text-zinc-400">{m.notes}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {m.languages.slice(0, 4).map((l) => (
                  <span key={l} className="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-zinc-200">{l}</span>
                ))}
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ${
                    m.legal === 'cla' ? 'bg-amber-400/20 text-amber-300' : 'bg-white/10 text-zinc-300'
                  }`}
                >
                  {m.legal === 'none' ? 'no sign-off' : m.legal === 'cla' ? 'CLA required' : m.legal === 'dco' ? 'DCO sign-off' : 'sign-off varies'}
                </span>
              </div>
              {m.gate && <p className="mt-3 text-sm font-bold text-rose-300">{m.gate}</p>}
              <button
                onClick={() => onChoose(i)}
                disabled={busy || !!m.gate}
                className={`mt-6 w-full rounded-full px-6 py-3.5 text-base font-extrabold transition duration-200 hover:scale-[1.03] focus:outline-none focus-visible:ring-4 focus-visible:ring-amber-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 ${
                  first ? 'bg-white text-zinc-950 hover:brightness-110' : 'border-2 border-white/25 text-white hover:border-white/60'
                }`}
              >
                {busy ? 'Scouting…' : `Find me an issue in ${m.org.split(' ')[0]} →`}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
