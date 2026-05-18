# Pickleball Match and Game Identification Logic

**This document defines the recommended architecture and logic for
identifying, constructing, sequencing, and uniquely tracking pickleball
matches and games within a large-scale synthetic simulation platform.**

## 1. Objectives

- Generate realistic and scalable match activity across all regions.

- Support both recreational and tournament play.

- Model realistic player participation frequency.

- Maintain historical traceability of matches and games.

- Enable analytics, rankings, confidence scoring, and simulations.

## 2. Core Definitions

- Match: A competitive event between two doubles teams.

- Game: An individual scoring unit within a match.

- Tournament Match: Match associated with a formal tournament bracket.

- Recreational Match: Informal or league/open-play competition.

- Session: A grouped set of matches occurring during one play event.

## 3. Match Identification Strategy

- Every match should receive a globally unique Match ID.

- Match IDs should remain immutable once created.

- IDs should support distributed generation across regions.

- Recommended format: MATCH\_\<REGION\>\_\<YYYYMM\>\_\<SEQUENCE\>.

- Sequence counters should reset monthly by region.

## 4. Game Identification Strategy

- Each game should receive a unique Game ID.

- Game IDs should reference the parent Match ID.

- Best-of-three matches should contain multiple game records.

- Recommended format: GAME\_\<MATCH_ID\>\_\<GAME_NUMBER\>.

## 5. Match Construction Logic

- Matches should be generated after team determination.

- Player availability should be considered.

- Geographic proximity should strongly influence recreational play.

- Tournament matches should prioritize bracket logic over proximity.

- Skill proximity should influence match quality realism.

## 6. Participation Frequency Modeling

- Players should have configurable activity profiles.

- Competitive players should participate more frequently.

- Retired or older players should have lower participation frequency.

- Seasonality should influence outdoor participation rates.

- Regional weather modifiers should impact scheduling.

## 7. Match Type Distribution

- Most matches should be recreational.

- League play should occur on recurring schedules.

- Tournament events should occur periodically.

- Skill-level divisions should influence tournament assignment.

- Regional competitiveness should affect tournament density.

## 8. Realistic Match Scheduling

- Players should not appear in overlapping matches.

- Travel constraints should limit unrealistic same-day movement.

- Sessions should contain multiple matches for active players.

- Weekends should generate higher participation rates.

- Peak evening hours should produce the highest recreational density.

## 9. Team vs Match Balancing

- Extremely imbalanced matches should be uncommon.

- Expected win probabilities should be calculated from team ratings.

- The match row should persist a no-noise predicted winner using
  `predicted_winning_team_number` and `predicted_win_probability` before
  stochastic game outcomes are generated.

- Controlled random noise should occasionally produce mismatches.

- Tournament seeding should influence pairing quality.

## 10. Score Generation Logic

- Game scores should reflect expected rating differentials.

- Better teams should win more frequently but not deterministically.

- Close ratings should produce tighter game scores.

- Blowouts should remain relatively uncommon.

- Noise injection should occasionally generate upset results.

- Game rows should persist both expected score share and expected raw
  scores (`expected_team_one_score`, `expected_team_two_score`) so the
  rating engine can compare rating-derived expectations to actual
  points.

- When `win_by_two_rule_enabled` is true, a configured
  `win_by_two_extension_rate` should allow a minority of games to
  extend beyond the target score.

## 11. Multi-Game Match Logic

- Tournament matches may use best-of-three formatting.

- Recreational play may use single-game matches.

- Current implementation applies one rating-derived expected win
  probability across all games in the match; dynamic between-game
  probability updates are a future enhancement.

- Player fatigue can slightly influence later games.

## 12. Historical Persistence

- All matches and games should remain historically queryable.

- Rating calculations should consume historical match results.

- Confidence calculations should consider recency and volume.

- Deleted matches should be extremely rare.

## 13. Monthly Batch Processing

- New match files should be processed monthly.

- Monthly batches should contain new registrations and matches.

- Ratings should update incrementally after match processing.

- Historical records should never be regenerated retroactively in
  normal incremental operation. Full reseeding or local test-data
  rebuilds may regenerate prior synthetic history.

## 14. Anti-Determinism Controls

- Weighted randomization should be applied throughout scheduling.

- Regional and social randomness should vary opponent selection.

- Noise should occasionally override ideal skill balancing.

- No two simulation runs should produce identical histories.

## 15. Recommended Processing Sequence

- Generate regions.

- Generate clubs.

- Generate players.

- Assign ratings.

- Determine teams.

- Generate player availability.

- Construct sessions. This remains a future enhancement; current match
  generation schedules directly at the match date level.

- Generate matches.

- Generate games.

- Generate scores.

- Update ratings and confidence.
