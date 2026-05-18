# Pickleball Match and Game Identification Logic for Monthly Batch Simulation

**This document defines the authoritative design specifications for
match and game identification, scheduling, persistence, configuration,
and simulation within a large-scale synthetic pickleball ecosystem. The
design supports realistic monthly batch generation, configurable
participation behavior, multiple match formats, longitudinal historical
analytics, and controlled randomness to reduce deterministic simulation
behavior.**

## 1. Architectural Objectives

- Support scalable monthly generation of match and game activity.

- Maintain realistic longitudinal player histories across months and
  years.

- Allow configurable match frequency, match type distribution, and
  games-per-match settings.

- Support tournament, league, recreational, ladder, and open-play
  ecosystems.

- Introduce configurable stochastic noise to reduce deterministic
  behavior.

- Enable replayable but non-identical simulation runs.

- Provide audit-friendly traceability of all generated matches and
  games.

## 2. Core Definitions

- Match: A competitive encounter between two doubles teams.

- Game: A scoring unit contained within a match.

- Session: A collection of matches played during a single event window.

- Monthly Batch: A processing unit containing newly generated matches,
  players, teams, and updates.

- Persistent Team: Recurring partnership maintained across months.

- Ad-Hoc Team: Temporary partnership formed for a specific event or
  session.

## 3. Monthly Batch Processing Philosophy

- The simulation should evolve incrementally month-over-month rather
  than regenerate history.

- Monthly batches should append new activity to historical records.

- Existing player ratings, chemistry, confidence, and team persistence
  should carry forward.

- Historical matches and games should never be regenerated retroactively
  except during full reseeding operations.

- Monthly batches should contain both new player registration events and
  newly generated match activity.

## 4. Match Identification Strategy

- Every match must receive a globally unique immutable Match ID.

- Match IDs should support distributed regional generation.

- Recommended format: MATCH\_\<REGION\>\_\<YYYYMM\>\_\<SEQUENCE\>.

- Match identifiers should encode generation month for operational
  traceability.

- Sequence counters should reset monthly within each region.

## 5. Game Identification Strategy

- Every game must receive a unique immutable Game ID.

- Games should reference the parent Match ID.

- Recommended format: GAME\_\<MATCH_ID\>\_\<GAME_NUMBER\>.

- Games must support independent statistical analysis.

- Best-of-three or multi-game formats should create multiple game
  records under one match.

## 6. Configurable Match Types

- The simulation engine should support configurable distributions of
  match types.

- Supported types should include recreational, ladder, league,
  tournament, challenge, clinic, and open play.

- Each region should support independent configuration of match-type
  distributions.

- Tournament-heavy regions should generate more persistent competitive
  matches.

- Casual recreational regions should generate more ad-hoc pairings.

## 7. Configurable Match Frequency

- Player participation frequency should be configurable using weighted
  probability distributions.

- Participation profiles should vary by age, competitiveness, club size,
  and player type.

- Highly competitive players should participate more frequently than
  casual players.

- Weekend participation should exceed weekday participation for
  recreational players.

- Weather modifiers should impact outdoor-region participation
  frequency.

## 8. Games Per Match Configuration

- Games-per-match should be configurable by event type.

- Tournament matches should commonly use best-of-three formats.

- Recreational sessions may use single-game formats.

- League play may use fixed multi-game structures.

- Games-per-match configuration should influence fatigue and scheduling
  calculations.

## 9. Session Generation Logic

- Matches should be grouped into realistic player sessions.

- Players should commonly participate in multiple matches during a
  session.

- Session duration should vary probabilistically.

- Large tournaments should create dense clustered session schedules.

- Open-play environments should create highly variable participation
  structures.

## 10. Match Scheduling Logic

- Players must never appear in overlapping matches.

- Travel constraints should prevent unrealistic same-day regional
  movement.

- Club-based recreational play should strongly favor geographic
  proximity.

- Tournament scheduling should prioritize bracket integrity.

- Rest windows should occasionally exist between matches.

## 11. Team Selection for Matches

- Persistent teams should be preferentially reused across monthly
  batches.

- Tournament play should strongly favor established partnerships.

- Open-play environments should permit more ad-hoc pairings.

- Compatibility scores should influence partner assignment.

- Controlled randomness should occasionally create unlikely pairings.

## 12. Match Balance Logic

- Extremely imbalanced matches should remain uncommon.

- Expected win probabilities should derive from combined team ratings.

- The selected match-level expected winner should be stored before
  outcome noise using `predicted_winning_team_number` and
  `predicted_win_probability`.

- Small rating gaps should produce highly competitive outcomes.

- Noise injection should occasionally override expected balancing.

- Tournament seeding should influence pairing quality.

## 13. Score Generation Logic

- Score generation should reflect underlying team strength differences.

- Better teams should win more often but not deterministically.

- Tightly matched teams should generate close scores more frequently.

- Blowouts should remain statistically uncommon.

- Noise injection should occasionally generate upset victories.

- Game generation should store rating-derived expected score share and
  expected raw scores for both teams before applying score noise.

- Win-by-two extensions should be controlled by
  `win_by_two_extension_rate` when `win_by_two_rule_enabled` is true.

## 14. Noise Injection Framework

- Noise must be intentionally injected throughout the simulation
  pipeline.

- Noise should affect player availability, team formation, scheduling,
  and outcomes.

- Noise levels should be configurable globally and regionally.

- Competitive tournaments should use lower noise levels than
  recreational play.

- Simulation reruns should produce statistically similar but
  non-identical ecosystems.

## 15. Recommended Noise Categories

- Availability noise.

- Social randomness noise.

- Travel variability noise.

- Skill-performance variance.

- Momentum and fatigue variance.

- Environmental randomness.

- Partner chemistry fluctuation.

## 16. Statistical Anti-Determinism Controls

- The same players should not repeatedly face identical opponents.

- Scheduling algorithms should intentionally vary opponent selection.

- Long-term ecosystem drift should naturally emerge.

- Player performance variance should fluctuate over time.

- Probability distributions should prevent repetitive exact outcomes.

## 17. Monthly Historical Persistence

- All generated matches and games must remain historically queryable.

- Historical records should support time-series analytics.

- Monthly snapshots should preserve evolving player trajectories.

- Ratings and confidence should update incrementally after each monthly
  batch.

- Historical chemistry and team persistence should influence future
  scheduling.

## 18. Suggested Configuration Parameters

- Monthly matches per player distribution.

- Games-per-match by event type.

- Tournament frequency by region.

- Noise intensity settings.

- Team persistence probabilities.

- Upset probability modifiers.

- Seasonality modifiers.

- Weekend participation multipliers.

- Travel radius limits.

## 19. Data Model Status and Future Enhancements

- Implemented: `matches`, `match_teams`, `match_team_players`, and
  `match_games`.

- Implemented: predicted match winner fields on `matches`.

- Implemented: expected score share, actual score share, expected raw
  scores, and score noise fields on `match_games`.

- Future enhancement: Session table.

- Future enhancement: Match type dimension table.

- Implemented: Monthly batch tracking table.

- Future enhancement: Scheduling conflict audit table.

- Implemented: Historical rating snapshot table via
  `player_rating_history`.

- Implemented as JSONB configuration profile payloads; a normalized noise
  configuration table remains optional.

## 20. Recommended Processing Sequence

- Load prior month state.

- Introduce new player registrations.

- Update active player pools.

- Update team persistence.

- Generate player availability.

- Generate sessions. This is a future enhancement; the current generator
  schedules matches directly to dates.

- Generate match schedules.

- Generate games.

- Generate scores.

- Apply noise adjustments.

- Update ratings and confidence.

- Persist monthly snapshots.

## 21. Scalability Considerations

- Generation pipelines should support hundreds of millions of games.

- Monthly processing should be partitionable by region.

- Parquet outputs should support downstream analytics.

- Distributed generation should permit horizontal scaling.

- Deterministic seed overrides should support reproducible testing.

## 22. Analytics and Data Science Support

- Historical match data should support player trajectory analysis.

- Game-level records should support advanced statistical modeling.

- Confidence scores should evolve using historical participation.

- Monthly persistence enables realistic forecasting exercises.

- Noise injection improves machine-learning realism.

**This architecture intentionally balances realism, scalability,
configurability, historical persistence, and controlled stochastic
behavior. The result is a synthetic ecosystem capable of supporting
graduate-level analytics workloads, simulation experimentation,
tournament forecasting, longitudinal player analysis, and
machine-learning training scenarios.**

## 23. Day-of-Month Match Distribution with Weekend Concentration Bias

Monthly match generation should assign matches to specific calendar
dates after the monthly match volume has been determined but before
sessions, courts, and individual start times are finalized. This
preserves the monthly batch model while producing realistic
calendar-level behavior. The allocation should be probability weighted
rather than evenly distributed, with higher concentration on Saturdays
and Sundays and secondary concentration on weekday evenings.

### 23.1 Design Intent

- Avoid unrealistic uniform distribution of matches across all days of
  the month.

- Create a natural concentration of recreational and tournament play on
  weekends.

- Permit weekday league and ladder play, especially during evening time
  windows.

- Allow regional, seasonal, club, and match-type configuration to
  influence date selection.

- Inject controlled random noise so the same month does not produce a
  mechanically identical date pattern.

- Support calendar-level analytics such as participation trends,
  day-of-week demand, and weekend tournament forecasting.

### 23.2 Recommended Calendar Allocation Sequence

- 1\. Create the month calendar for the target batch, including day
  number, day-of-week, holiday flag, school/workday flag if available,
  and seasonality attributes.

- 2\. Assign each day a base date weight using day-of-week rules.

- 3\. Apply match-type modifiers, such as stronger weekend weighting for
  tournaments and more weekday evening weighting for leagues.

- 4\. Apply regional and seasonal modifiers, such as outdoor-climate
  penalties during winter months or heat penalties during extreme summer
  periods.

- 5\. Apply club capacity constraints, court availability assumptions,
  and session density limits.

- 6\. Apply noise to each day weight to reduce deterministic
  concentration.

- 7\. Normalize all adjusted daily weights so they sum to 1.0 within the
  month.

- 8\. Sample match dates from the normalized distribution until the
  monthly match volume has been assigned.

- 9\. Create sessions within each selected date and then assign matches
  to sessions and start-time windows.

- 10\. Run validation checks to ensure no player, team, court, or
  location conflicts exist.

### 23.3 Baseline Day-of-Week Weighting

The following default weights are recommended as a starting point. These
should be configurable by region, club type, and match type.

  --------------------------------------------------------------------------
  **Day Type**      **Example Days**  **Default         **Interpretation**
                                      Weight**          
  ----------------- ----------------- ----------------- --------------------
  Low-volume        Monday, Tuesday   0.70              Reduced
  weekday                                               participation due to
                                                        work, school, and
                                                        lower club
                                                        programming.

  League weekday    Wednesday,        1.00              Normal weekday
                    Thursday                            participation with
                                                        evening league and
                                                        ladder play.

  Pre-weekend day   Friday            1.20              Higher activity from
                                                        evening play and
                                                        travel to weekend
                                                        tournaments.

  Primary weekend   Saturday          2.25              Highest
  day                                                   participation day
                                                        for tournaments,
                                                        open play, and
                                                        recreational
                                                        sessions.

  Secondary weekend Sunday            1.85              Strong
  day                                                   participation,
                                                        slightly lower than
                                                        Saturday due to
                                                        travel and work-week
                                                        preparation.
  --------------------------------------------------------------------------

### 23.4 Match-Type Day Bias Configuration

Different match types should use different day concentration behavior.
The monthly generator should select a match type first, then apply the
relevant day-of-month distribution for that type.

  ----------------------------------------------------------------------------------
  **Match Type**      **Weekend      **Weekday      **Typical         **Notes**
                      Bias**         Bias**         Pattern**         
  ------------------- -------------- -------------- ----------------- --------------
  Recreational/Open   Medium         Medium         Broad             Best for clubs
  Play                                              distribution with with casual
                                                    higher            drop-in play.
                                                    Saturday/Sunday   
                                                    density.          

  League              Low to Medium  High           Clustered on      Useful for
                                                    weekday evenings, predictable
                                                    often Tuesday     recurring
                                                    through Thursday. play.

  Ladder              Medium         Medium         Weekday evening   Often
                                                    and weekend       recurring but
                                                    morning           less rigid
                                                    concentration.    than formal
                                                                      league.

  Tournament          Very High      Low            Strong Saturday   Use multi-day
                                                    concentration     event windows
                                                    with some Sunday  for larger
                                                    finals and Friday tournaments.
                                                    warmups.          

  Challenge Match     Low            Medium         Flexible dates    Should use
                                                    based on player   more
                                                    availability.     randomness
                                                                      than
                                                                      structured
                                                                      events.

  Clinic/Event        Medium         Medium         Weekend mornings  May generate
                                                    and select        related
                                                    weekday evenings. informal games
                                                                      afterward.
  ----------------------------------------------------------------------------------

### 23.5 Daily Weight Formula

A practical date allocation weight can be calculated for each day in the
month using the following conceptual formula:

**daily_weight = base_day_weight x match_type_modifier x
regional_modifier x seasonality_modifier x holiday_modifier x
capacity_modifier x noise_factor**

- base_day_weight captures the normal day-of-week pattern.

- match_type_modifier adjusts the weight based on whether the match is
  recreational, league, ladder, or tournament play.

- regional_modifier captures local participation culture, travel
  patterns, and urban/suburban density.

- seasonality_modifier accounts for weather, daylight, and
  indoor/outdoor court availability.

- holiday_modifier can increase or decrease play depending on the
  specific holiday and region.

- capacity_modifier limits unrealistic concentration on a single day
  when court or club capacity would be exceeded.

- noise_factor introduces random variation so calendar allocation is not
  deterministic.

### 23.6 Noise Injection for Date Allocation

Noise should be applied after deterministic modifiers but before
normalization. This ensures that expected calendar patterns remain
visible while exact day selection varies between simulation runs.

- Low noise: multiply each daily weight by a random factor between 0.90
  and 1.10.

- Medium noise: multiply each daily weight by a random factor between
  0.80 and 1.25.

- High noise: multiply each daily weight by a random factor between 0.65
  and 1.50.

- Tournament schedules should usually use low-to-medium noise because
  real tournaments are intentionally scheduled.

- Open-play and challenge matches can use medium-to-high noise because
  participation is less structured.

- Noise should be seedable for reproducible test runs, but not
  hard-coded into production generation.

### 23.7 Weekend Concentration Guardrails

- Weekend concentration should be strong but not absolute; weekdays must
  still receive match volume.

- For recreational/open play, target approximately 40% to 55% of monthly
  matches on Saturdays and Sundays combined.

- For league-heavy configurations, target approximately 25% to 40% of
  matches on weekends because weekday evenings dominate.

- For tournament-heavy configurations, target approximately 60% to 80%
  of tournament matches on weekends, with Friday used for early rounds
  or travel warmups.

- Guardrails should be configurable so regions with stronger weekday
  club culture can reduce weekend concentration.

- The generator should flag unrealistic output when one or two days
  absorb too much monthly volume.

### 23.8 Capacity and Conflict Validation

- After assigning dates, validate that each club has enough court
  capacity to support scheduled sessions.

- Ensure players are not scheduled for impossible same-day match density
  unless the session format supports it.

- Prevent a player from participating in overlapping sessions at
  different clubs.

- Limit travel-heavy same-day movement across distant regions.

- Allow multiple matches per player on the same date when they occur
  within the same session or tournament event.

- If capacity is exceeded, either shift excess matches to the nearest
  weighted date or create additional sessions within the same date.

### 23.9 Example Monthly Distribution Workflow

- Assume a region requires a configured number of generated matches for
  May.

- Split those matches by configured match type distribution before date
  assignment.

- For each match type, calculate a daily probability distribution across
  all May dates.

- Apply weekend bias so Saturdays and Sundays receive higher probability
  mass.

- Apply league modifiers so Wednesday and Thursday evenings receive
  additional probability for league matches.

- Apply random noise to each day weight and normalize weights back to
  1.0.

- Sample dates for each match using the normalized distribution.

- Group sampled matches into realistic sessions and then assign teams,
  courts, and times.

- Run post-generation validation to confirm weekend bias is visible but
  not overly concentrated.

### 23.10 Recommended Configuration Fields

  -------------------------------------------------------------------------------
  **Configuration Field**         **Purpose**             **Example Value**
  ------------------------------- ----------------------- -----------------------
  weekend_concentration_bias      Increases Saturday and  1.75
                                  Sunday allocation       
                                  probability.            

  saturday_weight                 Controls                2.25
                                  Saturday-specific       
                                  concentration.          

  sunday_weight                   Controls                1.85
                                  Sunday-specific         
                                  concentration.          

  weekday_evening_multiplier      Raises weekday evening  1.20
                                  match probability.      

  league_weekday_multiplier       Creates stronger        1.40
                                  Tuesday-Thursday league 
                                  concentration.          

  tournament_weekend_multiplier   Creates strong weekend  2.50
                                  tournament clustering.  

  date_allocation_noise_level     Controls stochastic     medium
                                  variation in daily      
                                  assignment.             

  max_daily_match_share           Prevents excessive      0.08
                                  concentration on one    
                                  date.                   

  holiday_modifier_enabled        Allows holiday-specific true
                                  increases or decreases. 

  capacity_rebalance_enabled      Moves excess matches    true
                                  when daily capacity is  
                                  exceeded.               
  -------------------------------------------------------------------------------

### 23.11 Integration with the Monthly Batch Pipeline

- Date distribution should occur after monthly match volume and
  match-type mix are calculated.

- Date distribution should occur before session creation and exact time
  assignment.

- The selected date should be stored on the match record and inherited
  by associated game records unless games span multiple days in a
  tournament.

- The batch audit table should store distribution summary metrics,
  including weekend share, weekday share, maximum daily share, and noise
  configuration used.

- Monthly validation should compare actual generated distribution
  against configured target ranges.
