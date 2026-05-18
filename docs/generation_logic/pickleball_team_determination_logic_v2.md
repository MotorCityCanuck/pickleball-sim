# Pickleball Team Determination Logic (Enhanced Persistence Model)

**This document defines the recommended logic for realistic doubles team
determination within a large-scale synthetic pickleball simulation
platform. Special emphasis is placed on maintaining realistic team
persistence and continuity across monthly simulation batches while still
supporting controlled randomness and evolving player relationships.**

## 1. Core Objectives

- Generate realistic doubles partnerships across recreational and
  competitive environments.

- Support both persistent and ad-hoc teams.

- Maintain realistic partner continuity across months.

- Model social, geographic, skill, and club influences.

- Introduce controlled randomness without eliminating long-term
  consistency.

## 1.1 Point-in-Time Team Semantics

- Team state must always be evaluated as of a specific monthly batch
  month.

- A team is active for a point in time when `formation_date` is on or
  before the batch month, `team_status` is active, and
  `dissolution_date` is null or after the point-in-time date.

- Team membership is active for a point in time when `joined_date` is on
  or before the point-in-time date and `left_date` is null or after that
  date.

- Monthly generation must not rebuild all teams from scratch. It should
  load the prior point-in-time team state, retain most eligible teams,
  dissolve or mark dormant a configured minority, and create new teams
  for newly eligible players or replacement demand.

- Dormant teams remain part of team history and may reform later by
  reactivating the same team record and opening new team membership
  periods when the same partnership returns.

## 2. Team Persistence Philosophy

- Real-world pickleball players commonly maintain recurring partners
  over extended periods.

- Competitive players should exhibit higher team persistence rates than
  recreational players.

- Partnership continuity should gradually decay rather than reset each
  month.

- Monthly batch processing should evolve team networks incrementally
  instead of regenerating them entirely.

- New teams should emerge in every monthly batch from new players,
  previously unaffiliated team participants, dissolved teams, and
  stochastic social mixing.

## 3. Persistent Team Modeling

- Persistent teams should be explicitly tracked using a Team
  entity/table.

- Each persistent team should receive a stable Team ID.

- Teams should include start date, active status, chemistry score, and
  persistence probability.

- Historical team participation should directly influence future pairing
  probability.

- Team persistence probability should increase with successful match
  history.

## 4. Monthly Continuity Logic

- Existing teams should always be evaluated first before creating new
  pairings.

- Existing team and membership eligibility must be calculated as of the
  current monthly batch month.

- Monthly batches should preserve the majority of established
  partnerships.

- Only a configurable percentage of partnerships should dissolve
  monthly.

- Recommended recreational partner retention: 65% to 80%.

- Recommended competitive partner retention: 80% to 95%.

## 5. Team Lifecycle States

- New Team: Recently formed partnership with low chemistry confidence.

- Developing Team: Recurring partnership with growing chemistry score.

- Established Team: Long-running consistent partnership.

- Dormant Team: Temporarily inactive but eligible for future reuse.

- Retired Team: Permanently inactive partnership.

- Dissolved teams should not be deleted. The team should receive a
  `dissolution_date`, and active `team_memberships` should receive
  `left_date` values.

- Reforming the same partnership later should prefer reusing the
  historical team identity when the player pair is the same and the team
  is dormant rather than creating an unrelated duplicate team.

## 6. Team Chemistry Scoring

- Chemistry scores should accumulate over time.

- Winning percentage should positively influence chemistry.

- Long-term continuity should increase chemistry stability.

- Frequent inactivity should slowly decay chemistry.

- Chemistry should increase probability of future team reuse.

## 7. Partner Replacement Logic

- Team dissolution should occur probabilistically rather than
  deterministically.

- Rating divergence should increase breakup probability.

- Club transfers should increase breakup probability.

- Long inactivity periods should increase breakup probability.

- Random social noise should occasionally dissolve otherwise successful
  teams.

## 8. Ad-Hoc Team Generation

- Ad-hoc teams should still occur regularly in open play environments.

- Ad-hoc formation rates should be higher among casual players.

- Tournament events should favor persistent teams.

- Open play sessions should generate temporary pairings.

## 9. Cross-Month Consistency Requirements

- The same simulation run should produce coherent evolving team
  histories.

- Player relationships should persist naturally across months.

- Teams should accumulate recognizable histories and records.

- Historical teams should remain queryable for analytics.

- Partnership continuity should support longitudinal rating analysis.

## 10. Recommended Persistence Calculations

- Base retention probability should be assigned by player type.

- Chemistry score should modify retention probability.

- Recent match frequency should modify retention probability.

- Competitive tournament participation should increase persistence.

- Player relocation or inactivity should reduce persistence.

## 11. Suggested Data Model Enhancements

- Persistent Team table.

- Team Membership History table.

- Team Chemistry History table.

- Monthly Team Status Snapshot table.

- Team Dissolution Event table.

## 12. Randomness and Anti-Determinism Controls

- Controlled randomness should prevent repetitive deterministic
  pairings.

- Long-term persistence should still dominate over random reassignment.

- Noise injection should vary by competition level.

- Simulation reruns should produce similar but not identical ecosystems.

## 13. Recommended Processing Sequence

- Generate regions.

- Generate clubs.

- Generate players.

- Assign ratings.

- Load existing active teams.

- Evaluate persistence probabilities.

- Retain most existing teams.

- Dissolve a minority of teams.

- Mark dissolved teams dormant or retired according to configured
  lifecycle rules.

- Reactivate eligible dormant teams when the same partnership reforms.

- Generate replacement partnerships.

- Generate new teams for monthly player growth and unmet team demand.

- Generate matches and schedules.

- Update chemistry and persistence scores.
