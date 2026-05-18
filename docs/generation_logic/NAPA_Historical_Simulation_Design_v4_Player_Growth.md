**NAPA Pickleball Analytics Platform**

**Historical Simulation and Rating System Design**

**Technical Design for Historical Data Generation, Match Simulation,
Player Assessment History, and Rating Evaluation**

Version 2 update: player rating, confidence, volatility, rank, and other
assessment measures are modeled as dated historical records rather than
static attributes on the player table. Player age is replaced with
birthdate so age can be derived at any historical point in time.

# Overview

This document describes the recommended technical and analytical
approach for constructing the North American Pickleball Association
(NAPA) historical data environment, player rating system, doubles
partnership evaluation framework, and longitudinal sports analytics
platform.

The goal of the platform is to simulate and operationalize one year of
realistic doubles pickleball competition data for use in a
graduate-level data science and application development course. The
platform is intended to support:

- Large-scale sports analytics

- Historical match generation

- Longitudinal player tracking

- Doubles partnership evaluation

- Monthly batch processing

- Predictive analytics

- Ranking system experimentation

- Data engineering workflows

- Validation pipelines

- Simulation-based analytics

- AI-assisted application development

- Point-in-time player assessment history

• Monthly new-player registration and onboarding simulation

The environment should resemble a realistic enterprise sports analytics
platform rather than a simplified academic exercise.

# Core Architectural Philosophy

The recommended architecture separates three critical concepts:

1.  True Player Skill

2.  Match Performance

3.  Observed Organizational Ratings and Assessments

This distinction is essential because real-world sports organizations
never observe true player ability directly. Instead, organizations
attempt to estimate underlying player skill from noisy historical
outcomes.

The architecture therefore introduces:

- Hidden true-skill ratings used by the simulation engine

- Match-level performance variability

- Calculated organizational ratings derived from match outcomes

- Dated player assessment snapshots that preserve historical state

The most important structural change in this version is that rating and
assessment features are no longer stored directly on the players table.
A player can have many assessment records over time, each keyed by
player_id and assessment_date. This allows the platform to answer
point-in-time questions such as what a player was rated on March 31, how
confidence changed after a tournament, or which players were rising
fastest entering a future monthly batch.

# Core Rating and Assessment Concepts

The simulation framework should maintain multiple rating concepts for
each player, but those concepts should be stored in appropriate
historical tables rather than as fixed player attributes.

## True Skill Rating

- Hidden internal simulation value

- Represents underlying player ability

- Used when generating realistic match outcomes

- Never directly visible to analytics teams unless an instructor-only
  table or simulation audit view is exposed

- May be stored in a protected simulation-only table or in a
  player_truth_state table keyed by player_id and date if true skill is
  allowed to drift over time

## Observed Rating

- Public organizational rating

- Calculated from historical match outcomes

- Updated one match at a time or rolled into monthly assessment
  snapshots

- Represents what the organization believes about the player at a
  specific point in time

- Stored in player_assessments using player_id and assessment_date

## Effective Match Rating

- Temporary match-specific performance level

- Derived from true skill plus randomized performance noise

- Represents day-to-day variability in performance

- Stored only if needed for auditability, preferably at match-player or
  match-team level rather than the player table

## Assessment Snapshot

A player assessment snapshot is the historical record of the
organization's view of a player as of a specific date. It should include
ratings, confidence, volatility, ranking, activity, recent form, and
derived performance indicators. This table becomes the primary source
for longitudinal player analytics.

# Initial Player Population Generation

The simulation should begin by generating a realistic player population.
The players table should contain stable identity, demographic, and
classification attributes only. It should not contain current rating,
confidence, volatility, ranking, or other time-varying assessment
fields.

## Recommended player attributes

- player_id

- first_name

- last_name

- gender

- birthdate

- region_id or region

- home_city

- home_state_or_province

- country

- handedness

- dominant_play_style

- activity_level

- years_experience

- created_at

- updated_at

Age should be derived from birthdate using the relevant date context.
This is important because the generated dataset covers historical and
future periods. A static age field would become inconsistent as monthly
batches advance.

## Rating and assessment attributes moved out of players

The following fields should not be stored on the players table because
they change over time and require historical tracking:

- true_skill_rating

- observed_rating

- current_rating

- confidence_score

- volatility_score

- regional_rank

- national_rank

- rating_change

- rolling_3_month_change

- matches_played

- win_percentage

- pressure_performance_score

- consistency_score

- partnership_synergy indicators

These values should be stored in a dedicated player_assessments table,
with one record per player per assessment date or monthly assessment
period.

# Player Assessment History Design

The player_assessments table is the central longitudinal table for
player ratings and derived player-level evaluation features. It should
support both monthly snapshots and optional intra-month updates after
tournaments or important match events.

## Primary design

  -------------------------------------------------------------
  **Column**                     **Recommended meaning**
  ------------------------------ ------------------------------
  player_assessment_id           Surrogate primary key for the
                                 assessment record

  player_id                      Foreign key to
                                 players.player_id

  assessment_date                Date the assessment is
                                 effective; commonly month-end
                                 for monthly snapshots

  assessment_period              Optional YYYY-MM period label
                                 for reporting and partitions

  observed_rating                Organization-visible player
                                 rating as of assessment_date

  rating_change                  Change since prior assessment
                                 snapshot

  rolling_3_month_change         Three-month rating trend

  matches_played_lifetime        Total matches played through
                                 assessment_date

  matches_played_period          Matches played during the
                                 assessment period

  win_percentage_lifetime        Cumulative win percentage
                                 through assessment_date

  win_percentage_period          Period-specific win percentage

  confidence_score               Confidence in the observed
                                 rating estimate

  volatility_score               Rating instability or expected
                                 movement risk

  regional_rank                  Rank within region as of
                                 assessment_date

  national_rank                  Rank across the full NAPA
                                 population as of
                                 assessment_date

  pressure_performance_score     Performance estimate in close,
                                 high-value, or tournament
                                 situations

  consistency_score              Stability of match-to-match
                                 performance

  partnership_synergy_score      Player-level summary of
                                 partnership effectiveness

  assessment_source              Monthly batch, tournament
                                 batch, manual recalculation,
                                 or simulation audit

  generation_run_id              Foreign key to generation_runs
                                 when generated by a batch

  created_at                     Timestamp when the assessment
                                 row was written
  -------------------------------------------------------------

## Recommended key strategy

- Use player_assessment_id as the physical primary key for simplicity.

- Enforce a unique constraint on (player_id, assessment_date,
  assessment_source) or, if only one official record is allowed per day,
  on (player_id, assessment_date).

- Index (player_id, assessment_date) for point-in-time player history
  queries.

- Index (assessment_date, observed_rating) and (assessment_date,
  national_rank) for leaderboard and monthly ranking queries.

- Treat player_assessments as append-friendly historical data.
  Corrections should generally write a new version or be tracked through
  a recalculation_run_id rather than silently overwriting history.

## Point-in-time query behavior

Analytical queries should retrieve the latest assessment row with
assessment_date less than or equal to the date of interest. This
supports historically accurate views, such as building features using
only information available before a tournament or future prediction
month.

# Initial Rating Structure

Initial observed ratings should be represented by the first
player_assessments record for each player rather than by columns on the
players table.

- All players initially begin near 1500 observed rating, with controlled
  initialization noise if desired.

- Initial confidence should generally be low for new players and
  increase as match volume accumulates.

- Initial volatility should generally be high for new or infrequently
  active players and decrease as ratings stabilize.

- Initial true skill should be kept separate from organizational
  assessments and should remain hidden from student-facing analytical
  tables.

Recommended true-skill tiers:

- Recreational: 1000-1300

- Club Competitive: 1300-1600

- Regional Competitive: 1600-1900

- National Elite: 1900-2300

The population should not be generated from a perfectly uniform
distribution. Realistic clustering should be introduced so that elite
players remain relatively rare.

# Monthly Historical Data Simulation

The platform should generate historical data month-by-month over a
one-year period.

For each month:

1\. Load monthly new-player registration file

4.  Select active players

5.  Assign tournaments and events

6.  Generate doubles partnerships

7.  Match teams against similar competition levels

8.  Simulate match outcomes

9.  Store match results

10. Update observed player ratings after each match or tournament

11. Generate month-end player assessment snapshots

12. Store monthly assessment and ranking records

13. Process validation checks

14. Generate operational metrics

The simulation should generate:

- Match-level records

- Tournament results

- Doubles partnership histories

- Player rating history records and optional assessment history records

- Monthly rating histories

- Regional participation statistics

- Validation anomalies

- Longitudinal progression data

The resulting dataset should resemble a realistic operational sports
analytics environment where player identity is stable but rating and
assessment values evolve over time.

# Doubles Team Construction

Monthly Batch File Processing and Player Growth\
\
The simulation platform should model realistic organizational growth by
introducing new players during each monthly batch cycle. Rather than
assuming a static player population, the system should simulate ongoing
player registration activity similar to a real sports organization.\
\
Each monthly batch should therefore include two primary operational
input files:\
\
• Monthly new-player registration file\
• Monthly match results file\
\
Recommended monthly registration process:\
\
1. Load newly registered players\
2. Validate demographic and regional information\
3. Assign initial hidden true-skill values\
4. Generate initial player_assessments records\
5. Insert players into the active player population\
6. Make newly registered players eligible for future tournaments and
match generation\
\
Default player growth assumption:\
\
• 2% net player growth per month\
• Growth rate should later become configurable at generation-run level\
• Growth may vary by region, age group, competitive tier, or seasonal
participation patterns\
\
Example:\
\
If the active population begins at 250,000 players, a 2% monthly growth
rate would introduce approximately 5,000 newly registered players during
the next monthly batch.\
\
New-player onboarding behavior\
\
Newly registered players should behave differently from long-established
players.\
\
Recommended characteristics for newly registered players:\
\
• Lower confidence scores\
• Higher volatility scores\
• Fewer historical matches\
• Greater rating instability\
• Wider distribution of actual underlying skill\
• Higher probability of rapid rating movement during early matches\
\
The simulation should also support realistic registration patterns such
as:\
\
• Seasonal participation spikes\
• Regional growth differences\
• Beginner-heavy registration waves\
• Tournament-driven player acquisition\
• Demographic-specific growth patterns\
\
New-player records should first appear in the `players` table and
receive their initial observed rating through a
`player_rating_history` record tied to the registration batch date.
`player_assessment_history` is reserved for broader assessment metrics,
not for the canonical player rating.

Doubles partnerships are a critical component of the simulation.

Recommended team generation rules:

- Teams consist of two players

- Teams may be men's doubles, women's doubles, or mixed doubles

- Some partnerships should recur frequently

- Some pairings should be temporary

- Certain players should demonstrate strong partnership chemistry

- Some elite players should elevate weaker partners

- Some strong individuals should perform poorly together

Recommended partnership attributes:

- partnership_id

- player_1_id

- player_2_id

- matches_together

- wins

- losses

- synergy_score

- chemistry_modifier

- communication_modifier

- first_match_date

- last_match_date

Partnership-specific measures may be stored in partnership_stats or
partnership_assessments. Player-level summaries of partnership
performance should be written into player_assessments only when they
represent an assessment of the individual player as of a specific date.

# Match Outcome Simulation

Match outcomes should be generated using underlying player skill while
incorporating realistic performance variability.

Recommended team rating calculation:

team_true_rating = average(player_1_true_skill, player_2_true_skill) +
partnership_chemistry_bonus + regional_adjustment

The simulation should then introduce randomized match noise.

Recommended effective match rating:

team_effective_rating = team_true_rating + random_match_noise

Where random_match_noise \~ Normal(0, noise_std_dev).

Recommended default noise settings:

- Low noise: 25

- Moderate noise: 75

- High noise: 125

- Chaos mode: 200

Recommended default: noise_std_dev = 75

This prevents the simulation from becoming unrealistically deterministic
while still allowing stronger teams to win consistently over time.

# Score Generation Logic

The platform should generate realistic pickleball scores rather than
simple binary wins and losses.

Recommended game structure:

- Games played to 11

- Teams must win by at least 2

- Typical score ranges: 11-0 dominant win, 11-3 strong win, 11-7
  competitive win, and 12-10 extended close game

The probability model should generate expected score share, match
winner, and final game score. This allows the rating system to
incorporate score margin information rather than relying solely on
binary outcomes.

# Score-Adjusted Rating System

The recommended rating system is a modified score-adjusted doubles ELO
model. Rating updates should use the most recent player_assessments
record available before the match date, not a static rating stored on
the players table.

## Step 1: Calculate team ratings

team_rating = average(player_1_observed_rating_as_of_match_date,
player_2_observed_rating_as_of_match_date)

## Step 2: Calculate expected score share

expected_score = 1 / (1 + 10\^((opponent_team_rating -
team_rating)/400))

## Step 3: Calculate actual score share

actual_score_share = team_points / total_points_scored

Example: For an 11-7 result, the winning team score share is 11 / (11 +
7) = 0.611. The losing team score share is 7 / (11 + 7) = 0.389.

## Step 4: Calculate rating change

rating_delta = K \* match_weight \* (actual_score_share -
expected_score)

Recommended K values:

- New player: 48

- Established player: 24

- Elite stable player: 16

This approach allows close matches, dominant wins, and upsets to affect
ratings differently. Match-by-match rating movement may be retained in
rating_history, while official point-in-time player status should be
written to player_assessments.

# Monthly Rating Re-Evaluation

At the end of each month, the system should calculate updated player
metrics and write them to player_assessments as month-end snapshots.

Recommended monthly metrics:

- observed_rating

- rating_change

- rolling_3_month_change

- matches_played_period

- matches_played_lifetime

- win_percentage_period

- win_percentage_lifetime

- regional_rank

- national_rank

- partnership_synergy_score

- confidence_score

- volatility_score

- pressure_performance_score

- consistency_score

Monthly snapshots should be stored historically for longitudinal
analytics and trend analysis. These snapshots should be treated as the
official historical view of player assessments.

# Recommended Database Tables

Core operational tables should include the following structures.

## players

- player_id

- first_name

- last_name

- gender

- birthdate

- region_id or region

- home_city

- home_state_or_province

- country

- handedness

- dominant_play_style

- activity_level

- years_experience

- created_at

- updated_at

The players table should not include age, true_skill_rating,
observed_rating, current_rating, confidence_score, volatility_score, or
ranking fields.

## player_assessments

- player_assessment_id

- player_id

- assessment_date

- assessment_period

- observed_rating

- rating_change

- rolling_3_month_change

- matches_played_period

- matches_played_lifetime

- win_percentage_period

- win_percentage_lifetime

- confidence_score

- volatility_score

- regional_rank

- national_rank

- pressure_performance_score

- consistency_score

- partnership_synergy_score

- assessment_source

- generation_run_id

- created_at

## player_truth_state

- player_id

- effective_date

- true_skill_rating

- skill_drift_component

- injury_or_fatigue_modifier

- generation_run_id

This table is optional and should generally remain instructor-only or
simulation-engine-only. It preserves hidden truth when true skill
changes over time.

## matches

- match_id

- tournament_id

- team assignments

- score

- winner

- match_date

- timestamps

## rating_history

- rating_history_id

- player_id

- match_id

- rating_before

- rating_after

- rating_delta

- k_factor

- expected_score_share

- actual_score_share

- created_at

rating_history stores event-level rating movement. player_assessments
stores official dated snapshots used for longitudinal analytics.

## partnership_stats

- player_1_id

- player_2_id

- synergy_score

- wins

- losses

- matches_together

- first_match_date

- last_match_date

## generation_runs

- generation metadata

- parameters

- timestamps

## batch_runs

- monthly processing tracking

- input data periods

- status

- timestamps

## validation_results

- validation status

- anomalies

- severity

- affected_table

- affected_record_id

## export_runs

- parquet export tracking

- export path

- row counts

- timestamps

## job_status

- long-running job monitoring

- progress percentage

- current phase

- error details

# Recommended Technical Stack

Recommended technologies:

- Python

- FastAPI

- PostgreSQL

- SQLAlchemy

- ORM schema recreation utilities

- Pandas

- PyArrow

- HTMX

- Jinja2

- Vanilla JavaScript

- Docker Desktop

- Dev Containers

- GitHub

- Pytest

- DBeaver

The platform should emphasize local-first execution, zero cloud costs,
reproducibility, modular architecture, AI-assisted development, and
maintainable engineering practices.

# Recommended Student Learning Outcomes

This case study exposes students to:

## Data Science

- probabilistic modeling

- rating systems

- longitudinal analytics

- predictive modeling

- feature engineering

- point-in-time feature construction

## Data Engineering

- ingestion pipelines

- monthly batch processing

- historical snapshot design

- parquet exports

- validation frameworks

## Software Engineering

- modular architecture

- SQLAlchemy

- migrations

- testing

- Docker reproducibility

## Sports Analytics

- doubles evaluation

- player ranking systems

- partnership chemistry

- performance forecasting

## AI-Assisted Development

- architecture planning

- code generation

- context engineering

- AI-supported implementation workflows

# Recommended Future Enhancements

Advanced future enhancements may include:

- Monte Carlo tournament simulation

- Injury simulation

- Fatigue modeling

- Travel effects

- Bayesian ranking systems

- Glicko or TrueSkill variants

- Explainable AI models

- Visualization dashboards

- Real-time tournament ingestion

- Partnership optimization algorithms

- International competition simulation

- Olympic roster recommendation engines

The architecture should remain modular so that future enhancements can
be added incrementally.
