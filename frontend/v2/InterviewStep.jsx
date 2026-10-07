// InterviewStep.jsx
// Customize: accent colors, copy, keyboard shortcuts. One question per screen.
// Props: q (text), options [[value,label]], multi, value (string | string[]), index, total, fitCount,
//        onChange(value), onBack, onNext. Press 1-9 to choose, Enter to continue.
export default function InterviewStep({
  q = 'Which languages can you read comfortably?',
  options = [['Python', 'Python'], ['JavaScript', 'JavaScript'], ['Go', 'Go']],
  multi = false,
  value = multi ? [] : '',
  index = 0,
  total = 10,
  fitCount = null,
  onChange = () => {},
  onBack = () => {},
  onNext = () => {},
}) {
  const selected = multi ? value : [value];
  const ready = multi ? value.length > 0 : !!value;
  const toggle = (v) => onChange(multi ? (value.includes(v) ? value.filter((x) => x !== v) : [...value, v]) : v);

  React.useEffect(() => {
    const h = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      const n = parseInt(e.key, 10);
      if (n >= 1 && n <= options.length) toggle(options[n - 1][0]);
      if (e.key === 'Enter' && ready) onNext();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  });

  return (
    <section className="pointer-events-none flex min-h-[80vh] flex-col justify-center px-4 py-12 md:px-0 md:pl-[6vw]">
      <div className="pointer-events-auto max-w-2xl rounded-3xl bg-zinc-950/55 p-6 backdrop-blur-md md:p-10">
      <div className="mb-10 flex gap-1.5" role="progressbar" aria-valuemin={1} aria-valuemax={total} aria-valuenow={index + 1}>
        {Array.from({ length: total }).map((_, i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-all duration-300 ${
              i < index ? 'bg-violet-400' : i === index ? 'bg-gradient-to-r from-violet-400 to-pink-400' : 'bg-white/15'
            }`}
          />
        ))}
      </div>
      <p className="text-sm font-bold uppercase tracking-[0.2em] text-violet-300">
        Question {index + 1} of {total}
      </p>
      <h2 className="mt-3 text-4xl font-black leading-[1.02] tracking-tighter text-white sm:text-5xl md:text-6xl">{q}</h2>
      {multi && <p className="mt-3 text-base font-medium text-zinc-400">Pick as many as you like.</p>}

      <div className="mt-10 grid gap-3 sm:grid-cols-2">
        {options.map(([v, label], i) => {
          const on = selected.includes(v);
          return (
            <button
              key={v}
              onClick={() => toggle(v)}
              aria-pressed={on}
              className={`group flex items-center gap-4 rounded-2xl border-2 px-5 py-4 text-left text-lg font-bold transition duration-150 hover:scale-[1.02] focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400 ${
                on
                  ? 'border-violet-400 bg-violet-500/20 text-white shadow-[0_0_40px_-12px_rgba(167,139,250,1)]'
                  : 'border-white/10 bg-zinc-900/70 text-zinc-200 backdrop-blur hover:border-white/30'
              }`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-black ${
                  on ? 'bg-violet-400 text-zinc-950' : 'bg-white/10 text-zinc-400'
                }`}
              >
                {on ? '✓' : i + 1}
              </span>
              {label}
            </button>
          );
        })}
      </div>

      <div className="mt-10 flex flex-wrap items-center gap-4">
        <button
          onClick={onBack}
          disabled={index === 0}
          className="rounded-full border-2 border-white/20 px-7 py-3.5 text-base font-bold text-white transition hover:border-white/50 disabled:opacity-30"
        >
          Back
        </button>
        <button
          onClick={onNext}
          disabled={!ready}
          className="rounded-full bg-white px-10 py-3.5 text-lg font-extrabold text-zinc-950 transition duration-200 hover:scale-105 hover:brightness-110 focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
        >
          {index === total - 1 ? 'Show my matches →' : 'Next →'}
        </button>
        {fitCount !== null && (
          <span className="rounded-full bg-emerald-400/15 px-4 py-2 text-sm font-bold text-emerald-300">
            {fitCount} {fitCount === 1 ? 'organisation fits' : 'organisations still fit'} you
          </span>
        )}
      </div>
      </div>
    </section>
  );
}
