# agents.md

## Project Purpose

This project generates a large-scale synthetic North American pickleball ecosystem for graduate-level data science education and analytics experimentation.

The platform simulates:
- players
- clubs
- teams
- matches
- tournaments
- rankings
- player progression
- regional competitiveness
- monthly batch evolution
- realistic stochastic behavior

The generated data supports:
- analytics engineering
- data science
- machine learning
- Monte Carlo simulation
- medallion architecture exercises
- forecasting
- ranking analysis
- BI/dashboarding
- AI-assisted engineering workflows

Primary goals:
1. Realism
2. Configurability
3. Reproducibility
4. Statistical plausibility
5. Educational value
6. Long-term maintainability

---

# Core Architectural Principles

## ORM-First Architecture

SQLAlchemy ORM models are the authoritative system of record.

All:
- DDL
- migrations
- repositories
- services
- ETL logic

must remain synchronized with ORM definitions.

Never introduce schema drift.  Always validate consistency with ORM models after every change.

---

## Monthly Batch Processing

All simulation activity occurs through monthly batch data generation and processing.

This includes:
- initial historical generation
- future simulation months
- player additions
- player status changes
- match generation
- rankings progression
- tournament generation

Historical months and future months must use the same core logic.  Match data and simulated results will be generated in monthly increments.

---

## Deterministic Randomness

All randomness must support deterministic seeded execution.

Requirements:
- seeded RNG support
- reproducible runs
- configurable noise injection
- replay capability

Never use uncontrolled randomness.

---

## Simulation Realism

The system must avoid excessive determinism.

The simulation should introduce:
- regional variation
- imperfect matchmaking
- performance volatility
- probabilistic outcomes
- noise in rankings
- inconsistent player growth
- scheduling irregularities

Synthetic data should appear operationally believable.

---

## Player Availability Modeling

Player participation must be probabilistic and configurable.

Availability factors may include:
- work schedules
- age
- competitiveness level
- recreational vs tournament orientation
- injury/recovery state
- seasonal participation
- travel constraints
- club activity level

Players should not participate uniformly across all weeks or months.

---

## Injury and Recovery Modeling

The platform should support realistic, configurable injury and recovery simulation to improve longitudinal player realism and participation patterns.

Injury modeling should not attempt clinical precision. Its purpose is to simulate plausible sports participation disruption, temporary performance degradation, and recovery behavior.

Injury and recovery logic must support deterministic seeded execution.

---

### Injury Modeling Principles

Injuries should be:
- probabilistic
- configurable
- bounded
- realistic for recreational and competitive pickleball
- influenced by player and scheduling factors
- capable of affecting both availability and performance

The system should avoid excessive injury rates that make the simulation chaotic or unrealistic.

---

### Injury Risk Factors

Injury probability may be influenced by:
- player age
- recent match volume
- same-day game volume
- tournament density
- inadequate recovery time
- fatigue accumulation
- competitiveness level
- prior injury history
- travel load
- seasonal activity spikes

Older players, highly active players, and players with compressed match schedules may have modestly higher injury risk.

---

### Injury Types and Severity

The simulation may support broad injury categories such as:
- minor soreness or strain
- moderate overuse injury
- acute short-term injury
- recurring/chronic limitation

Severity should influence:
- duration of reduced availability
- likelihood of missed matches
- temporary performance impact
- recovery timeline
- reinjury probability

The model should use generalized categories, not detailed medical diagnosis.

---

### Availability Impact

Injuries may affect whether a player is available for:
- recreational matches
- league play
- tournaments
- same-day multi-game events
- future monthly batches

Possible availability states:
- fully available
- limited availability
- tournament unavailable
- temporarily inactive
- returning from injury

Availability effects should be probabilistic rather than absolute where appropriate.

---

### Performance Impact

Injured or recovering players may experience temporary reductions in:
- consistency
- stamina
- late-game performance
- upset resistance
- partnership effectiveness
- rating progression

Performance penalties should:
- scale with injury severity
- decay during recovery
- remain bounded
- avoid unrealistic permanent collapse unless explicitly configured

---

### Recovery Behavior

Recovery should occur over time and may be influenced by:
- injury severity
- player age
- rest period
- match load during recovery
- prior injury history

Players may return gradually rather than immediately resuming full performance.

The simulation should support recovery states such as:
- active injury
- limited return
- recovering
- fully recovered

---

### Reinjury and Recurrence

The model may include a modest probability of reinjury or recurring limitations, especially when:
- players return too quickly
- match volume remains high
- fatigue remains elevated
- prior injury history exists

Recurring injuries should remain uncommon and bounded.

---

### Configuration Requirements

Injury simulation must be configurable.

Example configuration:

```yaml
injury_model:
  enabled: true
  base_monthly_injury_rate: 0.015
  fatigue_multiplier: 1.25
  age_multiplier_enabled: true
  recovery_variance: medium
  reinjury_enabled: true
  ```

---

## Data Quality Injection

The platform intentionally supports configurable injection of realistic data quality issues for educational and analytics validation purposes. These data quality issues will be introduced following simulation data generation and prior to final validation and publication workflows.

Injected issues must:
- remain statistically plausible
- mimic real operational environments
- support configurable severity levels
- preserve overall simulation integrity
- support deterministic seeded execution

The system should support configurable injection of issues such as:
- missing data
- duplicate entities
- referential integrity problems
- delayed updates
- inconsistent formatting
- temporal inconsistencies
- statistical outliers
- partial monthly loads

Injected issues should:
- remain bounded
- avoid catastrophic corruption
- preserve educational usefulness
- support reproducible replay through seeded execution

Data quality injection should conceptually align with Bronze-layer operational realism within the medallion architecture model.

---

## Monthly Batch Execution Sequence

The simulation pipeline should execute using a deterministic and reproducible orchestration sequence.

The following represents the preferred high-level execution order for monthly batch generation:

1. New player generation
2. Player lifecycle and attrition updates
3. Injury and recovery updates
4. Player availability determination
5. Club assignment updates
6. Team formation
7. Match assignment and scheduling
8. Match result simulation
9. Rankings progression and recalculation
10. Tournament generation and simulation
11. Data quality issue injection
12. Validation and metrics generation
13. Final publication/export generation

Execution ordering should remain:
- deterministic
- reproducible
- observable
- auditable

Subsystem execution dependencies should be explicitly documented and validated.

Agents should avoid introducing execution-order drift or hidden side effects between orchestration stages.

Monthly batch execution should support:
- deterministic replay
- partial rerun capability
- subsystem isolation
- failure recovery
- incremental regeneration where appropriate

The orchestration framework should preserve statistical consistency and longitudinal realism across all monthly simulation batches.

---

## Medallion Architecture Alignment

Pipelines should conceptually align with:
- Bronze
- Silver
- Gold

data architecture principles.

Transformations should support:
- lineage
- auditability
- observability
- reproducibility
- quality validation

---

# Repository Structure

## /docs

Contains authoritative specifications.

Examples:
- architecture.md
- agents.md
- database_design.md
- generation_sequence.md
- module_interfaces.md
- coding_standards.md

Agents must review relevant documentation before implementation.

---

## /backend/models

Contains SQLAlchemy ORM definitions only.

Avoid placing business logic inside ORM models.

---

## /backend/repositories

Contains data access abstractions.

Direct SQL outside repositories is discouraged.

---

## /backend/services

Contains business and simulation logic.

Examples:
- player generation
- club assignment
- team formation
- match simulation
- tournament simulation
- rankings determination and progression

---

## /backend/etl

Contains ingestion and transformation logic.

---

## /backend/simulation

Contains stochastic simulation engines and orchestration workflows.

---

## /tests

Contains:
- unit tests
- integration tests
- deterministic simulation tests
- distribution validation tests

---

# Coding Standards

## Python Standards

Requirements:
- Python type hints required
- Use dataclasses where appropriate
- Prefer explicit typing
- Prefer composition over inheritance
- Avoid hidden side effects
- Avoid global mutable state

---

## Naming Standards

Use:
- snake_case for variables/functions
- PascalCase for classes
- plural snake_case for tables
- singular nouns for ORM entities where appropriate

Examples:
- players
- player_match_results
- club_assignments

---

## SQLAlchemy Standards

Requirements:
- explicit foreign keys
- indexed lookup columns
- consistent relationship naming
- avoid circular imports
- maintain migration compatibility

---

# Simulation Rules

## Player Generation

Player generation must support:
- regional distributions
- census-driven naming
- age distributions
- skill distributions
- DUPR-like ratings
- realistic variance based on configurable noise injection

Player populations should not be uniformly distributed.

---

## Team Formation

Team generation must:
- preserve cross-month consistency
- support partner continuity
- include probabilistic partner rotation
- consider geographic proximity
- consider club affiliation
- include realistic noise

Avoid purely random pairings.

---

## Match Generation

Match generation must support:
- configurable match frequency
- configurable games per match
- matches occur across days of the month with configurable maximum games per day and month ranges
- weekend scheduling bias
- tournament vs recreational play
- skill-based but imperfect matchmaking

---

# Match Result Determination

## Overview

Following match assignment and scheduling, the platform determines match outcomes using a probabilistic simulation model designed to balance:
- realism
- statistical plausibility
- competitive variability
- regional differences
- player volatility
- reproducibility

Match results must never be purely deterministic.

Even highly favored teams must retain a non-zero probability of underperformance or upset.

The simulation engine should produce outcomes that appear operationally believable over both:
- individual matches
- long-term population-level distributions

All match result generation must support deterministic seeded execution.

---

# Core Match Outcome Principles

Match outcomes are determined using a weighted probabilistic model incorporating:
- individual player skill
- team chemistry
- fatigue
- geographic factors
- regional competitiveness adjustments
- momentum/volatility
- configurable stochastic noise

The objective is to simulate realistic competitive behavior rather than mathematically perfect outcomes.

---

# Primary Match Outcome Variables

## Team Skill Rating

Each team receives a calculated baseline team strength score derived from:
- individual player ratings
- player consistency metrics
- historical volatility
- recent performance trends

Suggested approaches may include:
- weighted average rating
- Bayesian adjustment
- ELO/DUPR-style calculations
- recency weighting

The simulation should avoid relying solely on raw average ratings.

---

## Partnership Affinity

Teams with repeated historical partnerships may receive chemistry modifiers.

Affinity factors may include:
- historical win percentage together
- number of prior matches together
- communication/consistency simulation factors
- playstyle compatibility

Partnership affinity should:
- improve consistency
- slightly reduce unforced volatility
- improve close-game performance

Newly formed teams may experience higher variability.

---

## Fatigue Factors

Fatigue modifiers should simulate realistic physical and mental degradation.

Potential fatigue drivers:
- number of matches played recently
- tournament density
- travel load
- age-related recovery differences
- back-to-back scheduling
- same-day match volume

Fatigue may influence:
- consistency
- upset probability
- late-game performance
- error likelihood

Fatigue effects should remain probabilistic rather than absolute.

---

## Home Geography Advantage

Teams competing within their home region or club geography may receive minor environmental advantages.

Possible factors:
- familiarity with venue
- reduced travel fatigue
- local climate familiarity
- regional comfort

Home advantage should remain relatively small and configurable.

The model should avoid unrealistic home dominance effects.

---

## Regional Rating Inequality

Equivalent ratings across regions should not necessarily imply identical competitive strength.

The simulation should support regional competitiveness modifiers to reflect:
- regions will have a defined comparative strength factor
- stronger competitive ecosystems
- deeper talent pools
- higher tournament density
- stronger average opponents

Example:
- a 4.5 player in a highly competitive metro region may outperform a 4.5 player from a weaker regional pool

Regional modifiers should:
- remain subtle
- avoid excessive distortion
- preserve overall rating system stability

---

## Momentum and Volatility

Players and teams may experience temporary:
- hot streaks
- slumps
- confidence shifts
- inconsistent form

Momentum factors should:
- decay over time
- remain probabilistic
- avoid deterministic streak behavior

The system should avoid unrealistic sustained dominance.

---

## Match Type Influence

Different match types may alter competitive behavior.

Examples:
- recreational play
- ladder matches
- league play
- regional tournaments
- national tournaments

Tournament matches may:
- reduce volatility
- increase skill weighting
- increase fatigue accumulation
- increase upset pressure

Recreational matches may exhibit:
- greater inconsistency
- reduced intensity
- more skill variance

---

# Randomness and Noise Injection

## Configurable Stochastic Noise

The simulation engine must support configurable randomness injection.

Randomness should:
- create realistic upset behavior
- prevent deterministic outcomes
- introduce operational unpredictability
- preserve long-term statistical plausibility

Noise injection should be:
- configurable
- bounded
- reproducible through seeded RNG

Example configuration:

```yaml
match_randomness:
  enabled: true
  upset_factor: medium
  volatility_level: 0.12
```

---

## Upset Probability

Lower-rated teams must retain a realistic probability of victory.

Upset probability should vary based on:
- rating differential
- fatigue
- volatility
- partnership familiarity
- regional adjustments
- match importance

The system should avoid:
- excessive predictability
- unrealistic Cinderella outcomes
- purely rating-driven results

---

## Seeded RNG Support

All randomness must support deterministic replay through seeded pseudo-random number generation.

Requirements:
- reproducible simulation runs
- configurable subsystem seeds
- replay capability
- stable testing behavior

Suggested RNG isolation:
- match assignment RNG
- match outcome RNG
- tournament RNG
- fatigue RNG

Subsystem RNG separation is preferred to reduce execution-order sensitivity.

---

# Match Score Determination

Following winner determination, the engine should generate realistic game-level scores.

Score generation should consider:
- matches will consist of a configurable but variable number of games
- relative team strength
- consistency
- volatility
- fatigue
- momentum

Examples:
- close matches between evenly rated teams
- dominant victories by heavily favored teams
- occasional upset blowouts
- realistic point distributions

The engine should avoid repetitive or mechanically identical scores.

---

# Longitudinal Statistical Expectations

Over large populations and long time horizons, the simulation should approximately preserve:
- realistic win distributions
- stable rating ecosystems
- plausible upset frequencies
- reasonable progression curves
- competitive regional differentiation

The system should avoid:
- runaway rating inflation
- permanent dominance lock-in
- excessive random chaos
- deterministic ranking stability

---

# Validation Expectations

Match outcome systems must support:
- deterministic seeded validation
- upset frequency analysis
- regional competitiveness validation
- fatigue impact analysis
- score distribution analysis
- long-term rating stability testing

Major simulation changes should be statistically validated before release.

## Rankings Progression

Rankings progression must:
- evolve incrementally
- support volatility
- avoid unrealistic jumps
- include regression behavior
- support skill plateaus

---

## Tournament Simulation

Tournament simulation should support:
- bracket generation
- seeded and unseeded events
- regional tournaments
- cross-region events
- Monte Carlo simulation capability

---

# Testing Expectations

All major simulation features require:
- deterministic seed validation
- edge-case handling
- distribution sanity checks
- statistical plausibility checks
- continuity validation across months

Do not implement untested simulation logic.

---

# Agent Workflow Expectations

Before implementation:
1. Review relevant documentation
2. Inspect existing ORM models
3. Review related services
4. Avoid duplicate logic
5. Confirm consistency with architecture

When modifying existing systems:
- preserve backward compatibility where possible
- avoid unnecessary abstraction
- prefer incremental enhancement
- document assumptions

---

# Forbidden Patterns

The following are prohibited unless explicitly approved:

- direct SQL outside repository layer
- non-seeded randomness
- duplicate simulation logic
- hardcoded regional assumptions
- schema drift between ORM and DDL
- business logic inside ORM models
- hidden side effects
- bypassing service layers
- introducing circular dependencies
- monolithic multi-purpose service classes

---

# Definition of Done

A task is not complete until:
- code compiles
- tests pass
- deterministic execution validated
- documentation updated if necessary
- architecture consistency maintained
- no duplicate logic introduced

---

# Priority Order for Decision Making

When tradeoffs occur, prioritize:

1. Data realism
2. Architectural consistency
3. Reproducibility
4. Maintainability
5. Performance optimization
6. Development speed

---

# Long-Term Vision

This project is intended to evolve into a realistic enterprise-scale educational analytics platform demonstrating:

- modern data engineering
- AI-assisted software development
- simulation systems
- medallion architecture
- analytics engineering
- machine learning workflows
- statistical modeling
- Monte Carlo techniques
- production-style governance patterns

Agents should favor long-term maintainability and extensibility over short-term implementation shortcuts.
