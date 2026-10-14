# Mission report: Signal in the Dust

**Outcome:** EVE located  
**Planner:** classical · **Seed:** 42 · **Steps:** 94 · **Time:** 111/350  
**Battery:** 106.0 used, 67.0 left, 6 recharge ticks · **Distance:** 61 cells

## Inferred location and status

- Location: **(24, 6)** (cell probability 100.0%, 90% region 1 cells)
- Status: **dormant** (active 0%, dormant 100%, damaged 0%)
- Confidence: high: location confirmed visually; status 100% by posterior

## Recommended next step

Move to EVE at (24, 6) (~4 battery) and wake her with a close-range beacon pulse, then tow her back to recharge; the round trip needs ~24 and WALL-E has 67.

## Evidence found

- Briefing signal: bearing 62.0°, -82.0 dBm, t=-40
- Listens: 9, pings heard: 16, flagged as suspicious: 4
- clue-3 (scorch_mark) at (22, 2): Fresh blaster scorch. Plasma residue suggests the source is ~24 cells away.
- Decoy transmitter decoy-1 identified at (12, 4)
- EVE sighted at (24, 6), status read: active
  - The visual read disagrees with the accumulated evidence; signal strength history favours **dormant**.

## Strategy changes

- step 2: listen → search: No scan yet; sweeping for clues on the way to (10, 13).
- step 36: search → search: Best value target (26, 5): 38% belief within scan range for 25.0 battery.
- step 63: search → investigate: Scan revealed clue-3 at (22, 2); detouring 3.5 battery to read it before searching on.
- step 66: investigate → search: Reached target (22, 2); scanning.
- step 69: search → recharge: Battery 9.0 barely covers the 2.0 needed to reach a charger plus 6 reserve; heading to recharge.
- step 77: recharge → search: 8 ticks since the last scan; sweeping for clues on the way to (25, 5).

## Ground truth (evaluation only)

- EVE was at (24, 6), status dormant; location error 0.0 cells; status correct
- Decoys: (12, 4)
