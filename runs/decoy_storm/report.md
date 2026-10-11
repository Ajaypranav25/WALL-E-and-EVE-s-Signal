# Mission report: Decoy Storm

**Outcome:** EVE located  
**Planner:** classical · **Seed:** 7 · **Steps:** 187 · **Time:** 213/380  
**Battery:** 221.5 used, 60.0 left, 13 recharge ticks · **Distance:** 129 cells

## Inferred location and status

- Location: **(11, 1)** (cell probability 100.0%, 90% region 1 cells)
- Status: **damaged** (active 0%, dormant 0%, damaged 100%)
- Confidence: high: location confirmed visually; status 100% by posterior

## Recommended next step

Move to EVE at (11, 1) (~2 battery) and stabilise her, avoid jostling the damaged plating, and tow her back for repairs; the round trip needs ~39 and WALL-E has 60.

## Evidence found

- Briefing signal: near (20, 9) ±7.0, None dBm, t=-120
- Listens: 17, pings heard: 46, flagged as suspicious: 16
- clue-3 (scorch_mark) at (18, 5): Fresh blaster scorch. Plasma residue suggests the source is ~8 cells away.
- clue-5 (tracks) at (19, 7): Hover-tracks scored into the dust, heading 308°.
- Decoy transmitter decoy-1 identified at (27, 9)
- Decoy transmitter decoy-2 identified at (17, 21)
- EVE sighted at (11, 1), status read: damaged

## Strategy changes

- t=2 listen → search: No scan yet; sweeping for clues on the way to (16, 12).
- t=28 listen → search: Best value target (24, 12): 15% belief within scan range for 17.6 battery.
- t=49 search → investigate: Standing on clue-3; inspecting it.
- t=50 investigate → search: Best value target (25, 7): 37% belief within scan range for 11.1 battery.
- t=63 search → recharge: Battery 20.5 barely covers the 11.1 needed to reach a charger plus 8 reserve; heading to recharge.
- t=67 listen → recharge: Battery 16.5 barely covers the 6.9 needed to reach a charger plus 8 reserve; heading to recharge.
- t=70 recharge → search: Best value target (21, 14): 0% belief within scan range for 3.0 battery.
- t=72 search → recharge: Battery 10.5 barely covers the 2.0 needed to reach a charger plus 8 reserve; heading to recharge.
- t=81 recharge → search: 9 ticks since the last scan; sweeping for clues on the way to (27, 9).
- t=93 search → search: Best value target (18, 20): 81% belief within scan range for 18.9 battery.
- t=116 listen → search: Best value target (16, 5): 7% belief within scan range for 28.0 battery.
- t=133 search → investigate: Scan revealed clue-5 at (19, 7); detouring 2.5 battery to read it before searching on.
- t=140 search → recharge: Battery 21.5 barely covers the 11.5 needed to reach a charger plus 8 reserve; heading to recharge.
- t=154 listen → search: 14 ticks since the last scan; sweeping for clues on the way to (12, 1).

## Ground truth (evaluation only)

- EVE was at (11, 1), status damaged; location error 0.0 cells; status correct
- Decoys: (27, 9), (17, 21)
