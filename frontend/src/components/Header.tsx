export type Route = "mission" | "how" | "bench" | "report";

export const ROUTES: { id: Route; label: string }[] = [
  { id: "mission", label: "Mission Replay" },
  { id: "how", label: "How It Works" },
  { id: "bench", label: "Benchmark" },
  { id: "report", label: "Report" },
];

export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <g transform="rotate(-30 12 12)">
        <circle cx="7.3" cy="3.2" r="1.45" />
        <rect x="5.5" y="4.7" width="3.6" height="14.6" rx="1.8" />
        <rect x="14.9" y="4.7" width="3.6" height="14.6" rx="1.8" />
        <circle cx="16.7" cy="20.8" r="1.45" />
      </g>
    </svg>
  );
}

export function Header({ route }: { route: Route }) {
  return (
    <header className="app-header">
      <a className="logo" href="index.html" aria-label="Signal.eve home">
        <LogoMark />
        <span>
          Signal<span className="logo-suffix">.eve</span>
        </span>
      </a>
      <nav className="app-nav" aria-label="Primary">
        {ROUTES.map((r) => (
          <a key={r.id} className="pill" href={`#/${r.id}`} aria-current={route === r.id ? "page" : undefined}>
            {r.label}
          </a>
        ))}
      </nav>
      <a className="btn btn-solid header-cta" href="#/mission">
        Launch Mission
      </a>
    </header>
  );
}
