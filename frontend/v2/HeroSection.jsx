// HeroSection.jsx
// Customize: headline, subcopy, CTA labels, gradient colors (violet/pink), the three stat chips.
// Self-contained: React only. Transparent background on purpose so the 3D galaxy shows through.
export default function HeroSection({
  onStart = () => {},
  onLogin = null,            // pass a function to show "Continue with GitHub" instead of Start
  orgCount = 14,
}) {
  const stats = [
    ['10', 'questions'],
    [String(orgCount), 'organisations scored'],
    ['3', 'ways to work'],
  ];
  return (
    <section className="relative flex min-h-[86vh] items-center px-6 py-20 md:px-20 pointer-events-none">
      <div className="absolute -left-40 top-10 -z-10 h-96 w-96 rounded-full bg-violet-600 opacity-25 blur-3xl" />
      <div className="absolute left-1/3 bottom-0 -z-10 h-80 w-80 rounded-full bg-pink-500 opacity-20 blur-3xl" />
      <div className="max-w-3xl">
        <span className="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-sm font-semibold text-violet-200 backdrop-blur">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
          Open source, minus the gatekeeping
        </span>
        <h1 className="mt-6 text-6xl font-black leading-[0.95] tracking-tighter text-white sm:text-7xl md:text-8xl">
          Ship your first
          <br />
          <span className="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-pink-400 bg-clip-text text-transparent">
            real PR.
          </span>
        </h1>
        <p className="mt-8 max-w-xl text-xl font-medium leading-snug text-zinc-300 md:text-2xl">
          Answer ten questions. We find the project that fits you, an issue nobody has claimed, and a mentor that
          makes sure you understand every line you submit.
        </p>
        <div className="pointer-events-auto mt-10 flex flex-wrap items-center gap-4">
          {onLogin ? (
            <button
              onClick={onLogin}
              className="rounded-full bg-white px-10 py-4 text-lg font-extrabold text-zinc-950 shadow-[0_0_60px_-10px_rgba(167,139,250,0.9)] transition duration-200 hover:scale-105 hover:brightness-110 focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400"
            >
              Continue with GitHub →
            </button>
          ) : (
            <button
              onClick={onStart}
              className="rounded-full bg-white px-10 py-4 text-lg font-extrabold text-zinc-950 shadow-[0_0_60px_-10px_rgba(167,139,250,0.9)] transition duration-200 hover:scale-105 hover:brightness-110 focus:outline-none focus-visible:ring-4 focus-visible:ring-violet-400"
            >
              Find my first issue →
            </button>
          )}
          <span className="text-sm font-semibold text-zinc-400">Takes about 2 minutes. Drag the galaxy while you wait.</span>
        </div>
        <dl className="mt-14 flex flex-wrap gap-x-12 gap-y-6">
          {stats.map(([n, label]) => (
            <div key={label}>
              <dt className="text-5xl font-black tracking-tight text-white">{n}</dt>
              <dd className="text-sm font-semibold uppercase tracking-widest text-zinc-400">{label}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
