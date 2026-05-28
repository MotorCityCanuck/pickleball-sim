# Quick Start Guide for Developers

**Pickleball Simulation Platform**

**Last Updated**: 2024-05-10  
**Estimated Reading Time**: 15 minutes  
**Target Audience**: New developers joining the project

---

## Welcome!

You're about to work on a large-scale synthetic pickleball analytics simulation platform designed for graduate-level data science education. This platform generates realistic historical data spanning 50,000 default players, configurable monthly match volume, and includes rating systems, team dynamics, expected scoring, and monthly batch processing.

**This guide will get you oriented in 15 minutes.**

---

## Step 1: Understand What You're Building (3 minutes)

### The Big Picture

This platform:
- Generates **synthetic pickleball data** for analytics education
- Creates **50,000 default players** across North America, with smaller
  5,000-player runs used for efficient local testing
- Simulates **12 months of historical match data**
- Processes **monthly batch increments** for future data releases
- Exports **Parquet datasets** for student analytics projects

### Not a Game Simulator

This is **NOT**:
- ❌ A pickleball video game
- ❌ A real-time match simulator
- ❌ A public API service
- ❌ A mobile app

This **IS**:
- ✅ A data generation engine
- ✅ A monthly batch processor
- ✅ A local control panel with web UI
- ✅ An analytics data publisher

### Key Use Case

Graduate students will:
1. Receive historical baseline Parquet files
2. Build analytics pipelines (Bronze/Silver/Gold)
3. Train predictive models
4. Receive monthly "future" batches to validate forecasts
5. Recommend Olympic team selections

---

## Step 2: Core Architecture (3 minutes)

### Technology Stack

```
┌─────────────────────────────────────┐
│   Local Web Control Panel          │
│   (FastAPI + HTMX + Jinja2)        │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   Generation Engine (Python)        │
│   - Monthly Batch Processor         │
│   - Player Generator                │
│   - Match Generator                 │
│   - Rating Calculator               │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   PostgreSQL Database               │
│   - 37 ORM-backed tables            │
│   - Historical rating tracking      │
│   - Monthly batch metadata          │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│   Parquet Exports                   │
│   - Historical baseline             │
│   - Monthly batches                 │
│   - Student analytics datasets      │
└─────────────────────────────────────┘
```

### Monthly Batch Workflow

```
1. Load Configuration
      ↓
2. Create Monthly Batch Record
      ↓
3. Register New Players (2% growth)
      ↓
4. Form/Update Teams
      ↓
5. Schedule Matches (weekend-weighted, capped by team/day limits)
      ↓
6. Pair Opponents (rating-based)
      ↓
7. Generate Games, Expected Scores & Actual Scores
      ↓
8. Update Player Ratings
      ↓
9. Recalculate Confidence
      ↓
10. Run Validation Rules
      ↓
11. Export to Parquet
      ↓
12. Mark Batch Complete
```

---

## Step 3: Critical Design Rules (3 minutes)

### Rule #1: Batch Association

**Every generated record must include `batch_id`**

```sql
-- ✅ CORRECT
INSERT INTO matches (match_date, batch_id, ...)
VALUES ('2024-01-15', 42, ...);

-- ❌ WRONG - Missing batch_id
INSERT INTO matches (match_date, ...)
VALUES ('2024-01-15', ...);
```

**Rationale**: Traceability and reproducibility

---

### Rule #2: Historical Integrity

**Ratings are stored in history tables, not on players**

```sql
-- ❌ PROHIBITED
ALTER TABLE players ADD COLUMN current_rating DECIMAL;

-- ✅ CORRECT
INSERT INTO player_rating_history (player_id, rating_date, rating_value, batch_id)
VALUES (12345, '2024-01-31', 1625.5, 42);
```

**Rationale**: Point-in-time analytics require dated snapshots

---

### Rule #3: Age vs Birthdate

**Store birthdate, calculate age at query time**

```sql
-- ❌ PROHIBITED
ALTER TABLE players ADD COLUMN age INTEGER;

-- ✅ CORRECT
SELECT 
  player_id,
  first_name,
  last_name,
  birth_date,
  EXTRACT(YEAR FROM AGE(CURRENT_DATE, birth_date)) AS current_age,
  EXTRACT(YEAR FROM AGE('2024-01-15'::date, birth_date)) AS age_at_analysis_date
FROM players;
```

**Rationale**: Age changes over time; birthdate is immutable

---

### Rule #4: Append-Only History

**Never update historical records in place**

```sql
-- ❌ WRONG
UPDATE player_rating_history 
SET rating_value = 1650.0
WHERE player_id = 12345 AND rating_date = '2024-01-15';

-- ✅ CORRECT
INSERT INTO player_rating_history (player_id, rating_date, rating_value, batch_id)
VALUES (12345, '2024-02-15', 1650.0, 43);  -- New record
```

**Rationale**: Historical integrity and audit trails

---

### Rule #5: Snake Case Everywhere

**All identifiers use snake_case**

```python
# ✅ CORRECT
monthly_player_growth_rate = 0.02
weekend_concentration_bias = 1.75

# ❌ WRONG
monthlyPlayerGrowthRate = 0.02
WeekendConcentrationBias = 1.75
```

---

## Step 4: Key Tables (2 minutes)

### Must-Know Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `players` | Player identity | `id`, `birth_date`, `home_region_id` |
| `player_rating_history` | Time-series ratings | `player_id`, `rating_date`, `rating_value`, **`batch_id`** |
| `player_registrations` | New player intake | `player_id`, **`batch_id`**, `registration_month` |
| `matches` | Match metadata | `id`, `match_date`, `match_type`, **`batch_id`** |
| `match_teams` | Team in a match | `match_id`, `team_number`, `team_score` |
| `match_team_players` | Player in a team | `match_team_id`, `player_id` |
| `monthly_batches` | Batch control | `id`, `batch_month`, `processing_status` |
| `clubs` | Facilities | `id`, `club_name`, `region_id` |
| `teams` | Persistent partnerships | `id`, `team_type`, `chemistry_score` |

### Relationships

```
generation_runs (1) ──┬──> monthly_batches (12+)
                      │
monthly_batches ──────┼──> player_registrations (many)
                      │
                      ├──> matches (many)
                      │        ├──> match_teams (2 per match)
                      │        │        └──> match_team_players (2 per team)
                      │        └──> (references players)
                      │
                      ├──> player_rating_history (many)
                      │
                      └──> player_assessment_history (many)

players (many) ──> club_memberships (many) ──> clubs (many)
players (many) ──> team_memberships (many) ──> teams (many)
```

---

## Step 5: Essential Documents (4 minutes)

### Read These First (Critical)

1. **`docs_MASTER_DOCUMENT_INDEX.md`** ← Start here for navigation
2. **`database/Pickleball_Simulation_Database_Design_v3.md`** ← Schema authority
3. **`generation_logic/configuration_parameters_specification.md`** ← All parameters
4. **`docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md`** ← What changed

### Read These Second (High Priority)

5. **`architecture/architecture.md`** ← Big picture
6. **`generation_logic/Pickleball_Simulation_Generation_Sequence_Specification.md`** ← Step-by-step workflow
7. **`generation_logic/pickleball_match_game_monthly_batch_logic_v2_weekend_weighted.md`** ← Monthly processing

### Read These Third (Implementation)

8. **`architecture/Pickleball_Simulation_Detailed_Module_Interface_Specifications.md`** ← Module contracts
9. **Other generation_logic/*.md files** ← Specific algorithms

---

## Step 6: Configuration Quick Reference

### Most Important Parameters

```yaml
# Global
master_seed: 42                          # Reproducibility
first_batch_month: "2024-01-01"         # Current simulation start month
historical_batch_count: 12               # Initial history

# Player Growth
player_count: 50000                      # Initial population size
monthly_player_growth_rate: 0.02         # 2% monthly growth

# Ratings
initial_rating_mean: 1500.0              # Starting rating
initial_rating_elite_tail_rate: 0.003    # Small high-rating tail
rating_noise_std_dev: 75.0               # Match performance variance
k_factor_new_player: 48.0                # Rating volatility

# Match/Game Generation
matches_per_team_per_month: 4.0          # Approx. weekly team play
max_daily_matches_per_team: 2            # Daily scheduling cap
win_by_two_extension_rate: 0.10          # Chance of extended games

# Scheduling
monthly_matches_per_active_player_mean: 8.0   # Match frequency
monthly_matches_per_active_player_std_dev: 4.0
match_volume_noise_factor: 0.15
weekend_concentration_bias: 1.75              # Weekend multiplier
saturday_weight: 2.25                         # Saturday concentration

# Teams
team_persistence_probability_recreational: 0.72   # 72% team retention
team_persistence_probability_competitive: 0.88    # 88% team retention

# Matchmaking
rating_band_width_recreational: 400.0    # ±400 rating points tolerance
rating_band_width_tournament: 100.0      # ±100 rating points for tournaments
```

---

## Step 7: Common Queries You'll Need

### Get Current Player Rating

```sql
SELECT 
  p.id,
  p.first_name,
  p.last_name,
  prh.rating_value AS current_rating,
  prh.confidence_score,
  prh.rating_date
FROM players p
JOIN LATERAL (
  SELECT rating_value, confidence_score, rating_date
  FROM player_rating_history
  WHERE player_id = p.id
    AND rating_date <= CURRENT_DATE  -- Or specific analysis date
  ORDER BY rating_date DESC
  LIMIT 1
) prh ON true;
```

### Get Player Age at Specific Date

```sql
SELECT 
  id,
  first_name,
  last_name,
  birth_date,
  EXTRACT(YEAR FROM AGE('2024-01-15'::date, birth_date)) AS age_on_2024_01_15
FROM players;
```

### Get Matches for a Batch

```sql
SELECT 
  m.id AS match_id,
  m.match_date,
  m.match_type,
  mt1.team_score AS team_1_score,
  mt2.team_score AS team_2_score,
  p1a.first_name || ' ' || p1a.last_name AS team_1_player_1,
  p1b.first_name || ' ' || p1b.last_name AS team_1_player_2,
  p2a.first_name || ' ' || p2a.last_name AS team_2_player_1,
  p2b.first_name || ' ' || p2b.last_name AS team_2_player_2
FROM matches m
JOIN match_teams mt1 ON m.id = mt1.match_id AND mt1.team_number = 1
JOIN match_teams mt2 ON m.id = mt2.match_id AND mt2.team_number = 2
JOIN match_team_players mtp1a ON mt1.id = mtp1a.match_team_id AND mtp1a.player_position = 1
JOIN match_team_players mtp1b ON mt1.id = mtp1b.match_team_id AND mtp1b.player_position = 2
JOIN match_team_players mtp2a ON mt2.id = mtp2a.match_team_id AND mtp2a.player_position = 1
JOIN match_team_players mtp2b ON mt2.id = mtp2b.match_team_id AND mtp2b.player_position = 2
JOIN players p1a ON mtp1a.player_id = p1a.id
JOIN players p1b ON mtp1b.player_id = p1b.id
JOIN players p2a ON mtp2a.player_id = p2a.id
JOIN players p2b ON mtp2b.player_id = p2b.id
WHERE m.batch_id = 5  -- Specific batch
ORDER BY m.match_date, m.id;
```

### Get New Players for a Batch

```sql
SELECT 
  p.id,
  p.first_name,
  p.last_name,
  p.birth_date,
  pr.registration_month,
  pr.initial_rating_value,
  r.region_name
FROM player_registrations pr
JOIN players p ON pr.player_id = p.id
JOIN regions r ON pr.assigned_region_id = r.id
WHERE pr.batch_id = 5
ORDER BY pr.registration_month, p.last_name, p.first_name;
```

---

## Step 8: Validation Rules Quick Reference

### Critical Blockers (Must Pass)

| Rule | Check | Example |
|------|-------|---------|
| **REF-002** | All `matches.batch_id` exist | Foreign key validation |
| **CNT-003** | Every match_team has exactly 2 players | `COUNT(*) = 2` |
| **CNT-004** | Every match has exactly 2 teams | `COUNT(*) = 2` |
| **DATE-001** | Match dates within batch month | `match_date BETWEEN batch_start AND batch_end` |
| **RATING-001** | Ratings between 0 and 5000 | `rating_value >= 0 AND rating_value <= 5000` |
| **BIZ-001** | No overlapping matches per player per date | Temporal check |
| **EXP-002** | Export row count = DB row count | Count reconciliation |

### Common Warnings (Should Pass)

| Rule | Check | Target Range |
|------|-------|--------------|
| **DIST-001** | Weekend match concentration | 40-60% for recreational |
| **RATING-004** | Initial ratings cluster near 1500 | Mean ≈ 1500, StdDev ≈ 200 |
| **BIZ-005** | New player count ≈ growth rate | Within ±10% of 2% |

---

## Step 9: Module Development Pattern

### Standard Module Structure

```python
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class ModuleResult:
    """Standard return object for all modules"""
    module_name: str
    status: str  # 'success', 'failed', 'warning'
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    warnings: List[str] = None
    errors: List[str] = None
    metrics: Dict[str, Any] = None
    started_at: datetime = None
    completed_at: datetime = None
    elapsed_seconds: float = 0.0

def run(context: BatchContext, config: SimulationConfig) -> ModuleResult:
    """
    Standard entry point for all generator modules.
    
    Args:
        context: Batch context (batch_id, month, run_id, etc.)
        config: Simulation configuration (loaded from YAML/JSON)
        
    Returns:
        ModuleResult with status, counts, and metrics
    """
    result = ModuleResult(module_name="my_module")
    result.started_at = datetime.now()
    
    try:
        # Your generation logic here
        result.inserted_count = do_generation(context, config)
        result.status = "success"
        
    except Exception as e:
        result.status = "failed"
        result.errors = [str(e)]
        
    finally:
        result.completed_at = datetime.now()
        result.elapsed_seconds = (result.completed_at - result.started_at).total_seconds()
        
    return result
```

### Noise Usage Pattern

```python
from random import Random

def generate_with_noise(context: BatchContext, config: SimulationConfig):
    """All randomness must use seeded random stream"""
    
    # Create module-specific random stream
    rng = Random()
    rng.seed(context.master_seed + hash(context.module_name))
    
    # Use rng for all random operations
    rating_noise = rng.gauss(0, config.rating_noise_std_dev)
    weekend_boost = rng.uniform(0.9, 1.1) * config.weekend_concentration_bias
    
    # NEVER use global random(), np.random without seed
```

---

## Step 10: Getting Help

### If You're Stuck

1. **Check the index**: `docs_MASTER_DOCUMENT_INDEX.md`
2. **Search for the concept**: Use your IDE's global search
3. **Check corrections**: `docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md` explains what changed
4. **Review examples**: SQL queries and Python patterns in this guide

### Common Gotchas

| Problem | Solution |
|---------|----------|
| "Where should ratings be stored?" | `player_rating_history`, NOT `players` table |
| "How do I get a player's age?" | Calculate from `birth_date` at query time |
| "Can I update an old rating?" | NO - append new record instead |
| "Do I need batch_id?" | YES - all generated data needs it (NOT NULL) |
| "What's the parameter name?" | Check `configuration_parameters_specification.md` |
| "What's the correct match type?" | See enum: recreational, league, ladder, tournament, challenge, clinic, open_play |

---

## You're Ready!

You now know:
- ✅ What you're building (data generation platform)
- ✅ The core architecture (monthly batches → database → Parquet)
- ✅ The 5 critical design rules
- ✅ The key tables and relationships
- ✅ Where to find detailed specs
- ✅ Essential configuration parameters
- ✅ Common SQL queries
- ✅ Module development pattern
- ✅ How to get help

---

## Next Steps

1. **Clone the repo** (if not done already)
2. **Read** `docs_MASTER_DOCUMENT_INDEX.md` (complete navigation)
3. **Review** `database/Pickleball_Simulation_Database_Design_v3.md` (schema)
4. **Explore** `generation_logic/` documents (algorithms)
5. **Start coding** using module patterns from specifications

---

## Quick Command Reference

```bash
# Docker environment
docker compose up -d

# Database connection
psql -h localhost -U postgres -d pickleball

# Recreate development database from ORM metadata
python backend/scripts/recreate_db_from_orm.py

# Run generation
python -m app.batch_processing.monthly_batch_processor --batch-month 2024-01

# Export Parquet
python -m app.exports.parquet_exporter --batch-id 5

# Validate batch
python -m app.validation.validation_engine --batch-id 5
```

---

**Welcome to the team! Let's build something great.**

---

**END OF QUICK START GUIDE**
