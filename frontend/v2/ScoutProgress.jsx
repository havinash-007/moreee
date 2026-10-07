// ScoutProgress.jsx
// Customize: title/copy, colors. A full-screen overlay that shows what the scout is doing, as it happens.
// Props: title, steps (string[]; the last one is "in progress"), onCancel (optional).
export default function ScoutProgress({ title = 'Scouting for you', steps = [], onCancel = null }) {
  const [secs, setSecs] = React.useState(0);
  React.useEffect(() => { const t = setInterval(() => setSecs((s) => s + 1), 1000); return () => clearInterval(t); }, []);
  const endRef = React.useRef(null);
  React.useEffect(() => { if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight; }, [steps.length]);
  return (
    <div role="status" aria-live="polite" className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4 backdrop-blur-md">
      <div className="w-full max-w-xl rounded-3xl border border-white/10 bg-zinc-950/95 p-7 shadow-[0_0_80px_-20px_rgba(125,211,252,0.5)] md:p-9">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-sky-300">Live</p>
          <span className="text-xs font-bold tabular-nums text-zinc-500">{secs}s</span>
        </div>
        <h3 className="mt-2 text-4xl leading-tight text-white md:text-5xl">{title}</h3>
        <ul ref={endRef} className="mt-6 max-h-72 space-y-3 overflow-auto pr-1">
          {steps.length === 0 && <li className="text-zinc-400">Starting…</li>}
          {steps.map((s, i) => {
            const last = i === steps.length - 1;
            return (
              <li key={i} className="flex items-start gap-3 text-base font-semibold">
                {last ? (
                  <span className="mt-1 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-sky-300 border-t-transparent" />
                ) : (
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400 text-xs font-black text-zinc-950">✓</span>
                )}
                <span className={last ? 'text-white' : 'text-zinc-400'}>{s}</span>
              </li>
            );
          })}
        </ul>
        <p className="mt-6 text-xs font-medium text-zinc-500">Every issue is checked right now: open, unassigned, no open pull request, nobody already working on it.</p>
        {onCancel && <button onClick={onCancel} className="mt-5 text-sm font-bold text-zinc-400 hover:text-white">Cancel</button>}
      </div>
    </div>
  );
}
