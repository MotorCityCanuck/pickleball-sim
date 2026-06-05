# NAPA Olympic Team Selection & Monte Carlo Tournament Simulation

# Overview

The NAPA Olympic Team Selection Project is designed to challenge student consulting teams to develop a more sophisticated team recommendation methodology than NAPA's existing rating system.

Students will receive historical match data, player information, team information, and NAPA ratings. Their objective is to recommend one Men's Doubles team, one Women's Doubles team, and one Mixed Doubles team for Olympic competition.

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
- Incomplete

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

## Simulation Levels

### Game Level

- Simulate individual games
- Best-of-three format
- First to 11 points, win by 2

### Match Level

- Simulate best-of-three games
- Determine match winner

### Tournament Level

- Round-robin and/or bracket play
- Determine champions
- Track standings and statistics

### Monte Carlo Level

Run tournament repeatedly:

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

Each student group submits:

- One Men's Doubles Team ID
- One Women's Doubles Team ID
- One Mixed Doubles Team ID

Only existing NAPA teams may be submitted.

No ad hoc team formation is permitted.

---

# Portfolio Construction

Student teams are responsible for selecting a balanced portfolio consisting of one men's doubles team, one women's doubles team, and one mixed doubles team.

Success is measured across the entire portfolio rather than any individual category.

This encourages strategic portfolio optimization rather than isolated team selection.

---

# Duplicate Team Selections

Duplicate submissions are allowed.

If multiple student groups select the same team:

- The team appears only once in the tournament.
- All selecting groups receive credit for that team's performance.

This avoids duplicate entries while preserving fairness.

---

# Determining the Winning Student Group

Categories:

- Men's Doubles
- Women's Doubles
- Mixed Doubles

Example scoring:

| Result | Points |
|----------|----------|
| Champion | 10 |
| Runner-up | 7 |
| Semifinalist | 4 |
| Match Win | 1 |

Total Group Score =
    Men's Points
  + Women's Points
  + Mixed Points

---

# Tournament Format

To Be Finalized

Future specification items:

- Number of participating teams
- Seeding methodology
- Round-robin format
- Elimination format
- Tie-break procedures
- Medal determination rules

Tournament format decisions may materially influence team-selection strategy.

---

# Live Classroom Event

## Submission Panel

Collect:

- Group Name
- Men's Team ID
- Women's Team ID
- Mixed Team ID

## Tournament Control Panel

Features:

- Run Tournament
- Select Iteration Count
- View Results
- View Portfolio Summary

## Live Results

Display:

- Category Winners
- Overall Student Leaderboard
- Championship Probabilities
- Medal Probabilities
- Final Tournament Results

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

simulation/
    config.py
    factors.py
    probability.py
    game_simulator.py
    match_simulator.py
    tournament_simulator.py
    student_scoring.py
    results_summary.py

---

# Configurable Parameters

Examples:

- use_partnership_quality
- use_fatigue
- use_age_effects
- use_travel
- use_recent_form

Weights should be configurable without code changes.

---

# Performance Targets

Target workload:

- 16 teams per category
- 3 tournament categories
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
