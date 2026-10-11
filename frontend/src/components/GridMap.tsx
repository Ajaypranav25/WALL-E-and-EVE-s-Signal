import { useMemo, useState } from "react";
import { beliefIntensity, key, knownAt, rayEnd } from "../lib/replay";
import type { Cell, RunBundle } from "../types";

export interface Layers {
  belief: boolean;
  rays: boolean;
  truth: boolean;
}

const TERRAIN_FILL: Record<string, string> = { ".": "#0d0d0d", "~": "#272219", "#": "#3b3b3b" };
const TERRAIN_NAME: Record<string, string> = { ".": "open ground", "~": "rubble", "#": "wall" };
const VIEW_RADIUS = 2;
// SVG presentation attributes cannot read CSS variables, so mirror the theme roles here.
export const C = { walle: "#f26b1d", eve: "#ffffff", clue: "#e3b55b", decoy: "#e66767", charger: "#4fd39a", belief: "#bad0ff" };
const RAY_LENGTH = 40;

interface Props {
  run: RunBundle;
  step: number;
  layers: Layers;
}

export function GridMap({ run, step, layers }: Props) {
  const { world } = run;
  const rec = run.steps[Math.min(step, run.steps.length - 1)];
  const known = useMemo(() => knownAt(run, step), [run, step]);
  const belief = useMemo(() => beliefIntensity(rec), [rec]);
  const [hover, setHover] = useState<Cell | null>(null);

  const seen = useMemo(() => {
    if (world.map_known) return null;
    const s = new Set<string>();
    for (const [px, py] of known.path)
      for (let dy = -VIEW_RADIUS; dy <= VIEW_RADIUS; dy++)
        for (let dx = -VIEW_RADIUS; dx <= VIEW_RADIUS; dx++) s.add(key([px + dx, py + dy]));
    return s;
  }, [world.map_known, known.path]);

  const pos = rec.observation.position;
  const goal = rec.decision.goal;
  const pathPoints = known.path.map(([x, y]) => `${x + 0.5},${y + 0.5}`).join(" ");
  const scanNow = rec.action?.kind === "scan";
  const pings = rec.action?.kind === "listen" ? rec.observation.pings ?? [] : [];
  const showEve = layers.truth || known.eveSeen;
  const hoverIdx = hover ? hover[1] * world.width + hover[0] : -1;

  return (
    <div className="map-frame">
      <svg
        className="grid-map"
        viewBox={`0 0 ${world.width} ${world.height}`}
        role="img"
        aria-label={`Map ${world.width} by ${world.height}. WALL-E at ${pos[0]}, ${pos[1]}.`}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <pattern id="fog" width="0.5" height="0.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="0.5" height="0.5" fill="#050505" />
            <line x1="0" y1="0" x2="0" y2="0.5" stroke="#1a1a1a" strokeWidth="0.12" />
          </pattern>
          <radialGradient id="eve-glow">
            <stop offset="0" stopColor="#ffffff" stopOpacity="0.9" />
            <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
        </defs>

        {world.grid.map((row, y) =>
          row.split("").map((ch, x) => {
            const fogged = seen !== null && !seen.has(key([x, y]));
            return (
              <rect
                key={`t${x}-${y}`}
                x={x}
                y={y}
                width={1}
                height={1}
                fill={fogged ? "url(#fog)" : TERRAIN_FILL[ch]}
                stroke="#000"
                strokeWidth={0.04}
                onMouseEnter={() => setHover([x, y])}
              />
            );
          }),
        )}

        {layers.belief &&
          belief.map((v, i) =>
            v > 0.05 ? (
              <rect
                key={`b${i}`}
                className="belief-cell"
                x={i % world.width}
                y={Math.floor(i / world.width)}
                width={1}
                height={1}
                fill={C.belief}
                fillOpacity={0.04 + 0.8 * v * v}
                pointerEvents="none"
              />
            ) : null,
          )}

        {known.scans.map(([x, y], i) => (
          <circle key={`s${i}`} cx={x + 0.5} cy={y + 0.5} r={world.scan_radius} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={0.05} />
        ))}

        <polyline points={pathPoints} fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth={0.14} strokeLinejoin="round" strokeLinecap="round" />

        {layers.rays &&
          pings.map((p, i) => {
            const [ex, ey] = rayEnd([pos[0] + 0.5, pos[1] + 0.5], p.bearing_deg, RAY_LENGTH);
            return <line key={`r${i}`} x1={pos[0] + 0.5} y1={pos[1] + 0.5} x2={ex} y2={ey} stroke="rgba(186,208,255,0.8)" strokeWidth={0.08} strokeDasharray="0.3 0.2" />;
          })}

        {scanNow && <circle cx={pos[0] + 0.5} cy={pos[1] + 0.5} r={world.scan_radius} fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.7)" strokeWidth={0.08} />}

        {world.chargers.map(([x, y]) => (
          <g key={`c${x}-${y}`} transform={`translate(${x + 0.5} ${y + 0.5})`}>
            <rect x={-0.4} y={-0.4} width={0.8} height={0.8} rx={0.15} fill="none" stroke={C.charger} strokeWidth={0.08} />
            <path d="M0.05 -0.3 L-0.18 0.04 H0 L-0.05 0.3 L0.18 -0.04 H0 Z" fill={C.charger} />
          </g>
        ))}

        {layers.truth &&
          world.clues.map((c) =>
            known.detectedClues.has(c.id) ? null : (
              <rect key={`tc${c.id}`} x={c.position[0] + 0.5 - 0.22} y={c.position[1] + 0.5 - 0.22} width={0.44} height={0.44} transform={`rotate(45 ${c.position[0] + 0.5} ${c.position[1] + 0.5})`} fill="none" stroke={C.clue} strokeWidth={0.06} strokeDasharray="0.12 0.08" opacity={0.7} />
            ),
          )}
        {[...known.detectedClues.entries()].map(([id, [x, y]]) => (
          <rect key={`dc${id}`} x={x + 0.5 - 0.24} y={y + 0.5 - 0.24} width={0.48} height={0.48} transform={`rotate(45 ${x + 0.5} ${y + 0.5})`} fill={known.readClues.has(id) ? C.clue : "none"} stroke={C.clue} strokeWidth={0.08} />
        ))}

        {layers.truth &&
          world.decoys.map((d) =>
            known.decoys.has(d.id) ? null : (
              <circle key={`td${d.id}`} cx={d.position[0] + 0.5} cy={d.position[1] + 0.5} r={0.32} fill="none" stroke={C.decoy} strokeWidth={0.07} strokeDasharray="0.12 0.08" />
            ),
          )}
        {[...known.decoys.entries()].map(([id, [x, y]]) => (
          <g key={`dd${id}`} stroke={C.decoy} strokeWidth={0.12} strokeLinecap="round">
            <line x1={x + 0.22} y1={y + 0.22} x2={x + 0.78} y2={y + 0.78} />
            <line x1={x + 0.78} y1={y + 0.22} x2={x + 0.22} y2={y + 0.78} />
          </g>
        ))}

        {showEve && (
          <g transform={`translate(${world.eve.position[0] + 0.5} ${world.eve.position[1] + 0.5})`} opacity={known.eveSeen ? 1 : 0.6}>
            <circle r={1.1} fill="url(#eve-glow)" />
            <ellipse rx={0.26} ry={0.36} fill={C.eve} />
            <ellipse cx={0} cy={-0.12} rx={0.17} ry={0.07} fill="#0a0a0a" />
          </g>
        )}

        {goal && (goal[0] !== pos[0] || goal[1] !== pos[1]) && (
          <g transform={`translate(${goal[0] + 0.5} ${goal[1] + 0.5})`} stroke="rgba(255,255,255,0.85)" strokeWidth={0.07} fill="none">
            <circle r={0.38} />
            <line x1={-0.6} y1={0} x2={-0.2} y2={0} />
            <line x1={0.2} y1={0} x2={0.6} y2={0} />
            <line x1={0} y1={-0.6} x2={0} y2={-0.2} />
            <line x1={0} y1={0.2} x2={0} y2={0.6} />
          </g>
        )}

        <g className="walle" transform={`translate(${pos[0] + 0.5} ${pos[1] + 0.5})`}>
          <rect x={-0.36} y={-0.32} width={0.72} height={0.64} rx={0.12} fill={C.walle} stroke="#000" strokeWidth={0.06} />
          <circle cx={-0.14} cy={-0.06} r={0.09} fill="#111" />
          <circle cx={0.14} cy={-0.06} r={0.09} fill="#111" />
        </g>

        {hover && <rect x={hover[0]} y={hover[1]} width={1} height={1} fill="none" stroke="#fff" strokeWidth={0.06} pointerEvents="none" />}
      </svg>
      {hover && (
        <div className="map-tip" role="status">
          <strong>
            ({hover[0]}, {hover[1]})
          </strong>{" "}
          {seen && !seen.has(key(hover)) ? "unexplored" : TERRAIN_NAME[world.grid[hover[1]][hover[0]]]}
          <span> · belief {((rec.belief[hoverIdx] ?? 0) / 100).toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
}

export function MapLegend() {
  const items: { label: string; swatch: JSX.Element }[] = [
    { label: "WALL-E", swatch: <rect x={2} y={3} width={12} height={10} rx={2} fill={C.walle} /> },
    { label: "EVE", swatch: <ellipse cx={8} cy={8} rx={4} ry={6} fill={C.eve} /> },
    { label: "Charger", swatch: <rect x={2} y={2} width={12} height={12} rx={3} fill="none" stroke={C.charger} strokeWidth={1.5} /> },
    { label: "Clue (filled = read)", swatch: <rect x={4} y={4} width={8} height={8} transform="rotate(45 8 8)" fill={C.clue} /> },
    { label: "Decoy found", swatch: <path d="M3 3 13 13 M13 3 3 13" stroke={C.decoy} strokeWidth={2} strokeLinecap="round" /> },
    { label: "Belief", swatch: <rect x={1} y={1} width={14} height={14} fill="rgba(186,208,255,0.6)" /> },
    { label: "Goal", swatch: <circle cx={8} cy={8} r={5} fill="none" stroke="#fff" strokeWidth={1.4} /> },
    { label: "Wall / rubble", swatch: <><rect x={1} y={1} width={7} height={14} fill="#3b3b3b" /><rect x={8} y={1} width={7} height={14} fill="#272219" /></> },
  ];
  return (
    <ul className="legend" aria-label="Map legend">
      {items.map((i) => (
        <li key={i.label}>
          <svg width={16} height={16} viewBox="0 0 16 16" aria-hidden="true">
            {i.swatch}
          </svg>
          {i.label}
        </li>
      ))}
    </ul>
  );
}
