# NAPA Olympic Team Selection & Monte Carlo Tournament Simulation

# Overview

The NAPA Olympic Team Selection Project is designed to challenge student consulting teams to develop a more sophisticated team recommendation methodology than NAPA's existing rating system.

Students will receive historical match data, player information, team information, and NAPA ratings. Their objective is to recommend one Men's Doubles team, one Women's Doubles team, and one Mixed Doubles team for each Olympic country delegation included in the exercise.

The final class will feature a live tournament simulation and student competition.

## Educational Objective

The purpose of this exercise is not to identify the "correct" Olympic teams. The purpose is to develop and defend a repeatable analytical methodology that can be used to identify high-performing teams under conditions of uncertainty.

Students will be evaluated primarily on the quality of their analytical methodology, business justification, presentation quality, and ability to defend recommendations rather than on the outcome of any single tournament simulation.

---

# Core Educational Philosophy

NAPA's published ratings are intentionally positioned as:

- Useful
- Credible
- Data-driven
- Basic

The ratings primarily reflect score-based historical match outcomes and serve as a baseline indicator of team strength.

Students are expected to explore additional factors that may influence success, including:

- Partnership chemistry
- Partnership stability
- Age and age differential
- Fatigue and workload
- Geographic and travel factors
- Recent form and trends
- Confidence and uncertainty
- Other engineered features

The objective is to move beyond simple rating-based ranking approaches.

---

# NAPA Rating System Philosophy

NAPA ratings are generated using a relatively simple score-based methodology derived from historical match outcomes.

Ratings are intended to provide a useful estimate of team strength but are not intended to capture all factors that influence future tournament performance.

Consulting organizations are encouraged to evaluate whether additional analytical approaches may improve predictive accuracy.

---

# Team Selection Objective

The objective is not necessarily to identify the highest-rated teams.

The objective is to identify the teams most likely to succeed in an Olympic-style tournament environment.

Consulting teams should consider both current strength and tournament-specific factors that may influence performance.

---

# Hidden Factor Design

## Student Visibility

Students will NOT be provided:

- Hidden factors
- Hidden factor values
- Hidden factor weights
- Tournament simulation formulas

Students must infer useful predictors through data analysis.

## Hidden Factor Design Principles

1. Hidden factors must be grounded in realistic pickleball concepts.
2. Hidden factors must leave observable patterns within the historical data.
3. Hidden factors must not dominate the published ratings.

## Tournament Engine

The tournament simulation will utilize hidden factors when determining match outcomes.

The tournament engine must reuse the same `hidden_performance_bias` configuration
section and the same hidden-bias application logic used by generated match
outcomes. Tournament-specific match and game simulation may be implemented in a
separate application module, but the rating adjustment semantics should remain
consistent with the synthetic match generator.

Potential hidden factors include:

- Partnership quality
- Fatigue
- Age effects
- Age differential effects
- Travel burden
- Recent form
- Consistency / volatility
- Other contextual factors

Recommended balance:

- Ratings: 70–85%
- Contextual factors: 15–30%

---

# Match Outcome Model

## Baseline Strength

Adjusted Team Strength =
    Team Rating
  + Partnership Adjustment
  + Fatigue Adjustment
  + Age Adjustment
  + Travel Adjustment
  + Recent Form Adjustment

## Win Probability

Convert strength differences into an Elo-style probability model.

Higher adjusted strength results in a higher expected win probability.

## Randomness

Controlled randomness should be introduced to reflect real sports variability.

The objective is to create realistic upsets without making outcomes feel arbitrary.

---

# Rating Confidence

Ratings should be interpreted alongside confidence measures.

Examples:

- High rating / high confidence
- High rating / low confidence
- Moderate rating / rapidly improving
- Moderate rating / highly volatile

Students may choose to incorporate confidence measures into their analytical methodology.

---

# Consistency and Variance

Teams with identical ratings may exhibit significantly different volatility profiles.

Examples:

- Consistent teams may outperform expectations over long tournaments.
- High-variance teams may generate upset potential.

Consistency should influence tournament behavior independently from average rating.

---

# Fatigue Model

Potential fatigue inputs include:

- Matches played during the current tournament
- Games played during the current tournament
- Match duration
- Rest periods between matches
- Age-related recovery effects

Fatigue should accumulate throughout tournament play.

---

# Tournament Simulation Architecture

## System Boundary

The tournament simulation is an instructor-facing application feature, not part
of monthly synthetic data generation.

The tournament simulation must remain independent from:

- monthly batch orchestration
- generated historical `matches` and `match_games`
- rating update generation
- student dataset export workflows

Tournament simulation may read generated historical data as source context, but
it must not mutate historical matches, generated games, player ratings, monthly
batches, or student export release data.

The only intended shared behavior is match and game outcome determination:
tournament simulation should reuse the existing hidden-bias configuration and
outcome logic rather than inventing a separate probability model.

## Data Source Snapshot

Tournament team strength should be based on the latest
`player_rating_history` records as of the selected tournament source batch.

For the initial application version, the selected source batch should normally
be the latest completed batch in the selected generation run. The tournament
date will be after the final generated batch date.

Teams are eligible only if active as of the tournament date.

Eligibility should use the most accurate lifecycle source available:

- Prefer immutable team lifecycle history when available.
- Fall back to current team status and dissolution date only when lifecycle
  history is unavailable.

## Country Eligibility

The team formation model must be extended to assign and persist a country
identifier on each generated team.

Tournament submissions must use teams whose persisted country identifier matches
the requested delegation country.

Cross-country teams are prohibited.

Team formation should therefore prevent player pairings that would create a
team spanning multiple countries, or explicitly reject those pairings before
persisting teams.

The initial supported countries for the Olympic selection exercise are:

- Canada
- USA

The persisted team country identifier should use a stable machine-readable code
such as `CA` and `US`, with display labels handled separately.

## Simulation Levels

### Game Level

- Simulate individual games
- Best-of-three format
- First to 11 points, win by 2

### Match Level

- Simulate best-of-three games
- Determine match winner

### Tournament Level

- Round-robin play for the initial implementation
- Determine champions
- Track standings and statistics

### Monte Carlo Level

Provide the option to run tournament repeatedly:

- 1,000 iterations
- 5,000 iterations
- 10,000 iterations

Generate:

- Championship probability
- Medal probability
- Average finish
- Win percentage
- Upset frequency

---

# Official Tournament vs Monte Carlo Analysis

## Official Tournament

A single tournament simulation will be executed live during the final class session.

This simulation is intended to provide:

- Entertainment
- Engagement
- Friendly competition
- Trophy determination

## Monte Carlo Analysis

Thousands of tournament simulations may be executed to evaluate expected performance.

Monte Carlo analysis provides:

- Expected performance estimates
- Championship probabilities
- Portfolio strength comparisons
- Model validation insights

The official tournament outcome represents only one realization of a probabilistic process and should not be interpreted as the sole measure of recommendation quality.

---

# Student Competition Structure

There will be six student groups.

Each student group submits six existing NAPA teams:

- Canada Men's Doubles Team ID
- Canada Women's Doubles Team ID
- Canada Mixed Doubles Team ID
- USA Men's Doubles Team ID
- USA Women's Doubles Team ID
- USA Mixed Doubles Team ID

Only existing NAPA teams may be submitted.  Teams must be identified using their NAPA Team ID numbers.

No ad hoc team formation is permitted.

Submitted teams must be active as of the tournament date and must match the
required country and division.

---

# Portfolio Construction

Student teams are responsible for selecting a balanced portfolio consisting of
one team for each country/division combination.

The six portfolio slots are:

- Canada Men's Doubles
- Canada Women's Doubles
- Canada Mixed Doubles
- USA Men's Doubles
- USA Women's Doubles
- USA Mixed Doubles

Success is measured across the entire portfolio rather than any individual category.

This encourages strategic portfolio optimization rather than isolated team selection.

---

# Duplicate Team Selections

Duplicate submissions are allowed.  A team may be submitted by more than one student group.

If multiple student groups select the same team:

- The team appears only once in the tournament.
- All selecting groups receive credit for that team's performance.

This avoids duplicate entries while preserving fairness.

---

# Determining the Winning Student Group

Tournament divisions:

- Canada Men's Doubles
- Canada Women's Doubles
- Canada Mixed Doubles
- USA Men's Doubles
- USA Women's Doubles
- USA Mixed Doubles

Student scoring should be configurable without code changes.

Default scoring:

| Result | Points |
|----------|----------|
| Champion | 10 |
| Runner-up | 7 |
| Semifinalist | 4 |
| Match Win | 1 |

Total Group Score =
    Canada Men's Points
  + Canada Women's Points
  + Canada Mixed Points
  + USA Men's Points
  + USA Women's Points
  + USA Mixed Points

For the initial round-robin format, champion and runner-up points are awarded
from final standings. Match-win points are awarded directly from round-robin
match results.

The semifinalist score value is retained as a configurable result level for
future elimination or hybrid formats. If no semifinal or top-four concept is
configured for round robin, semifinalist points are not awarded.

---

# Tournament Format

Initial format:

- Six student groups submit teams.
- Each country/division combination is simulated as its own round-robin division.
- Duplicate team selections collapse to one tournament entry per division.
- All student groups selecting a duplicated team receive credit for that team's results.
- Each unique team plays every other unique team in its division once.
- Champion, runner-up, medal/top-three, win percentage, match wins, and average finish are derived from division standings.

Tie-break order:

1. Match wins
2. Head-to-head result among tied teams
3. Game differential
4. Point differential
5. Deterministic seeded tiebreak

Future format extensions:

- Larger fields, including up to 36 unique teams per country/division
- Seeding methodology
- Elimination or hybrid round-robin plus playoff format
- Semifinal and medal-match rules

Tournament format decisions may materially influence team-selection strategy.

---

# Live Classroom Event

## Submission Panel

Collect:

- Group Name
- Canada Men's Team ID
- Canada Women's Team ID
- Canada Mixed Team ID
- USA Men's Team ID
- USA Women's Team ID
- USA Mixed Team ID

## Tournament Control Panel

Features:

- Select generation run and source batch
- Select tournament date
- Run Monte Carlo prediction
- Run official live tournament
- Select Iteration Count
- View Results
- View Portfolio Summary

## Live Results

Display:

- Division Winners
- Overall Student Leaderboard
- Championship Probabilities
- Medal Probabilities
- Final Tournament Results
- Official match and game results

---

# Persistence Strategy

Tournament simulation output should use dedicated tournament simulation tables,
not monthly generation tables.

Do not write Monte Carlo trial matches to the historical `matches`,
`match_games`, `match_teams`, or `match_team_players` tables.

Do not trigger `ratings_update_log` generation from tournament simulation.

Recommended persistence split:

- Student submissions: durable rows keyed by tournament event/run and student group.
- Monte Carlo runs: durable run metadata, config snapshot, source generation run, source batch, tournament date, iteration count, seed, and aggregate results.
- Monte Carlo aggregate outputs: per-team and per-student probabilities, average finish, win percentage, medal probability, championship probability, and upset frequency.
- Official live tournament run: durable match-level and game-level result rows for replay and display.

Official live tournament results should persist complete round-robin match and
game results for every division.

Monte Carlo simulation should persist aggregate outputs by default. Persisting
every simulated trial match is not recommended because it would create high
storage volume without improving the classroom workflow.

Tournament simulation tables should be excluded from student dataset export
unless a future instructor-facing results package is intentionally added.

---

# Student Dataset Visibility

Student-facing exports should not expose hidden simulation formulas, factor
weights, hidden factor values, or tournament internals.

The existing team fields `chemistry_score` and `persistence_probability` should
be omitted from student-exposed data. These values are too close to hidden
partnership and persistence signals and may weaken the intended analytical
challenge.

Students should receive enough visible data to construct defensible analytical
features, including team membership, historical results, visible ratings,
rating confidence, geography, age, and match history.

---

# Simulation Insights

Following tournament completion, the platform may reveal high-level observations regarding performance drivers without exposing proprietary formulas.

Examples:

- Partnership stability was predictive.
- Fatigue effects influenced later rounds.
- Rating alone was insufficient.
- Consistency affected upset rates.

---

# Suggested Software Architecture

tournament_simulation/
    config.py
    eligibility.py
    factors.py
    probability.py
    game_simulator.py
    match_simulator.py
    round_robin.py
    tournament_simulator.py
    student_scoring.py
    results_summary.py
    persistence.py
    service.py

The implementation should extract or wrap reusable match outcome behavior from
the existing match generator so tournament simulation and monthly match
generation share the same hidden-bias semantics.

The tournament simulation package should not depend on monthly pipeline
orchestration.

---

# Configurable Parameters

The tournament configuration should be added as another configuration tab in the control panel.

Examples:

- tournament date
- source generation run
- source batch
- iteration count
- random seed
- use hidden performance bias
- champion points
- runner-up points
- semifinalist/top-four points
- match-win points
- medal cutoff
- tie-break configuration

The tournament should use the existing `hidden_performance_bias` configuration
for factor weights and enablement. Tournament-specific scoring and execution
settings should be configurable without code changes.

---

# Performance Targets

Initial classroom workload:

- 6 student groups
- 6 submitted teams per student group
- 36 submitted team slots
- 6 country/division round-robin tournaments
- Up to 6 unique teams per country/division after duplicate selections collapse
- 10,000 Monte Carlo iterations
- One live tournament execution

Future stress target:

- Up to 36 unique teams per country/division
- 6 country/division tournaments
- 10,000 Monte Carlo iterations

Target execution:

- Results generated in under 10 seconds on instructor workstation hardware

---

# Key Design Goal

Students should be able to achieve reasonable results using ratings alone, but superior analytical approaches should consistently outperform simple rating-based selection.

The project should reward:

- Feature engineering
- Predictive analytics
- Strategic thinking
- Uncertainty modeling
- Executive-level decision making

rather than rewarding simple sorting by rating.
