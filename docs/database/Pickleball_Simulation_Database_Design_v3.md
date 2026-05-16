# database_design.md

# Pickleball Simulation Platform --- Database Design

Prepared: 2026-05-10

\-\--

# 1. Overview

This document defines the logical and physical database design for the
Pickleball Simulation Platform.

The schema supports:

- Large-scale synthetic pickleball player generation

- Historical rating evolution

- Monthly batch simulation processing

- Match and tournament simulation

- Player assessments and confidence tracking

- Regional population modeling

- Census-driven name generation

- Analytics-ready exports

- Operational job tracking

- Parquet export metadata

- Validation and reproducibility workflows

Primary database platform:

- PostgreSQL 16+

ORM:

- SQLAlchemy (for queries and data access only)

Schema Management:

- Direct DDL execution (schema defined in Section 11)

\-\--

# 2. Core Design Principles

## 2.1 Historical Integrity

All ratings, assessments, confidence scores, and derived metrics are
stored historically using effective dates.

The design avoids storing mutable ratings directly on the player table.

## 2.2 Incremental Batch Processing

Monthly batches introduce:

- New player registrations

- New match results

- Updated ratings

- Updated assessments

- New derived analytics

All batches are reproducible.

## 2.3 Analytics-Optimized Design

The schema supports:

- Relational workloads

- Time-series analysis

- ML feature generation

- Parquet export partitioning

- Snapshot analytics

- Confidence trending

\-\--

# 3. Core Entity Relationship Summary

Primary entities:

- players

- player_rating_history

- player_assessment_history

- player_registrations

- matches

- match_teams

- match_team_players

- tournaments

- regions

- clubs

- club_memberships

- teams

- team_memberships

- monthly_batches

- generation_runs

Operational entities:

- batch_runs

- export_runs

- uploaded_files

- validation_results

- job_status

Reference entities:

- first_names

- last_names

\-\--

# 4. Core Domain Tables

## 4.1 players

Stores the master player record.

### Key Concepts

- Birthdate instead of age

- Static player attributes only

- Ratings stored historically elsewhere

### Proposed Columns

\| Column \| Type \| Description \|

\|\-\--\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \| Internal player identifier \|

\| external_player_key \| UUID \| Public stable identifier \|

\| first_name \| VARCHAR(100) \| Generated first name \|

\| last_name \| VARCHAR(100) \| Generated last name \|

\| gender \| VARCHAR(20) \| Gender \|

\| birth_date \| DATE \| Date of birth \|

\| dominant_hand \| VARCHAR(10) \| Left/Right \|

\| home_region_id \| BIGINT FK \| Home region \|

\| registration_date \| DATE \| Initial registration \|

\| initial_skill_seed \| NUMERIC(8,4) \| Initial hidden skill value \|

\| player_status \| VARCHAR(30) \| Active/Inactive/Retired \|

\| created_at \| TIMESTAMP \| Insert timestamp \|

\| updated_at \| TIMESTAMP \| Update timestamp \|

\| generation_run_id \| BIGINT FK \| Generation run \|

\-\--

## 4.2 player_rating_history

Stores historical ratings by effective date.

### Purpose

Supports:

- Historical analytics

- Trend analysis

- Confidence modeling

- Monthly snapshots

- Time-travel analytics

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| player_id \| BIGINT FK \|

\| rating_date \| DATE \|

\| rating_type \| VARCHAR(50) \|

\| rating_value \| NUMERIC(8,3) \|

\| confidence_score \| NUMERIC(8,3) \|

\| volatility_score \| NUMERIC(8,3) \|

\| expected_performance \| NUMERIC(8,3) \|

\| regional_adjustment_factor \| NUMERIC(8,4) \|

\| global_percentile \| NUMERIC(5,2) \|

\| match_count_used \| INTEGER \|

\| calculation_version \| VARCHAR(50) \|

\| batch_id \| BIGINT FK \|

\| created_at \| TIMESTAMP \|

\-\--

## 4.3 player_assessment_history

Stores historical player assessment metrics.

### Examples

- Mental resilience

- Fatigue

- Momentum

- Consistency

- Aggression

- Tournament pressure

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| player_id \| BIGINT FK \|

\| assessment_date \| DATE \|

\| assessment_type \| VARCHAR(100) \|

\| assessment_value \| NUMERIC(8,3) \|

\| confidence_score \| NUMERIC(8,3) \|

\| derived_from_matches \| INTEGER \|

\| created_at \| TIMESTAMP \|

\-\--

# 5. Match and Competition Tables

## 5.1 matches

Stores match-level metadata.

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| tournament_id \| BIGINT FK \|

\| match_date \| DATE \|

\| region_id \| BIGINT FK \|

\| court_type \| VARCHAR(50) \|

\| match_format \| VARCHAR(50) \|

\| winning_team_id \| BIGINT \|

\| total_points_played \| INTEGER \|

\| expected_competitiveness \| NUMERIC(8,3) \|

\| simulation_noise_factor \| NUMERIC(8,3) \|

\| created_at \| TIMESTAMP \|

\-\--

## 5.2 match_teams

Represents a doubles team instance inside a match.

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| match_id \| BIGINT FK \|

\| team_number \| INTEGER \|

\| team_score \| INTEGER \|

\| expected_win_probability \| NUMERIC(8,4) \|

\| average_team_rating \| NUMERIC(8,3) \|

\| created_at \| TIMESTAMP \|

\-\--

## 5.3 match_team_players

Associates players to teams.

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| match_team_id \| BIGINT FK \|

\| player_id \| BIGINT FK \|

\| player_position \| INTEGER \|

\| player_rating_at_match \| NUMERIC(8,3) \|

\| created_at \| TIMESTAMP \|

\-\--

# 6. Tournament Tables

## 6.1 tournaments

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| tournament_name \| VARCHAR(255) \|

\| region_id \| BIGINT FK \|

\| tournament_start_date \| DATE \|

\| tournament_end_date \| DATE \|

\| tournament_type \| VARCHAR(50) \|

\| skill_division \| VARCHAR(50) \|

\| participant_count \| INTEGER \|

\| created_at \| TIMESTAMP \|

\-\--

# 7. Regional Modeling Tables

## 7.1 regions

Stores MSA/CMA/CA regional definitions.

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| country_code \| VARCHAR(10) \|

\| region_type \| VARCHAR(20) \|

\| region_name \| VARCHAR(255) \|

\| state_province_code \| VARCHAR(10) \|

\| population \| BIGINT \|

\| competitiveness_multiplier \| NUMERIC(8,4) \|

\| latitude \| NUMERIC(10,6) \|

\| longitude \| NUMERIC(10,6) \|

\| created_at \| TIMESTAMP \|

\-\--

# 8. Name Generation Tables

## 8.1 first_names

Stores consolidated USA and Canada first-name frequency data.

### Purpose

Supports:

- Birth-year aligned naming

- Gender-aligned generation

- State/province-aware distributions

- Frequency-weighted generation

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| country_code \| VARCHAR(2) \|

\| state_province_code \| VARCHAR(2) \|

\| birth_year \| INTEGER \|

\| gender \| VARCHAR(1) \|

\| first_name \| VARCHAR(100) \|

\| frequency_count \| INTEGER \|

\| normalized_probability \| NUMERIC(12,8) \|

\| source_dataset \| VARCHAR(255) \|

\| created_at \| TIMESTAMP \|

## 8.2 last_names

Stores consolidated USA and Canada last-name frequency data.

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| country_code \| VARCHAR(2) \|

\| state_province_code \| VARCHAR(2) \|

\| last_name \| VARCHAR(100) \|

\| frequency_count \| INTEGER \|

\| normalized_probability \| NUMERIC(12,8) \|

\| source_dataset \| VARCHAR(255) \|

\| created_at \| TIMESTAMP \|

\-\--

# 9. Monthly Batch Processing Tables

## 9.1 monthly_batches

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| batch_month \| DATE \|

\| batch_sequence \| INTEGER \|

\| new_player_count \| INTEGER \|

\| new_match_count \| INTEGER \|

\| processing_status \| VARCHAR(30) \|

\| created_at \| TIMESTAMP \|

\| completed_at \| TIMESTAMP \|

\-\--

## 9.2 batch_runs

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| batch_id \| BIGINT FK \|

\| run_status \| VARCHAR(30) \|

\| started_at \| TIMESTAMP \|

\| completed_at \| TIMESTAMP \|

\| error_message \| TEXT \|

\| created_at \| TIMESTAMP \|

\-\--

# 10. Operational Metadata Tables

## 10.1 generation_runs

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| generation_name \| VARCHAR(255) \|

\| seed_value \| BIGINT \|

\| simulation_version \| VARCHAR(100) \|

\| parameter_snapshot \| JSONB \|

\| started_at \| TIMESTAMP \|

\| completed_at \| TIMESTAMP \|

\| status \| VARCHAR(30) \|

\-\--

## 10.2 uploaded_files

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| original_filename \| VARCHAR(255) \|

\| stored_filename \| VARCHAR(255) \|

\| file_type \| VARCHAR(50) \|

\| file_size_bytes \| BIGINT \|

\| upload_timestamp \| TIMESTAMP \|

\| validation_status \| VARCHAR(30) \|

\| created_at \| TIMESTAMP \|

\-\--

## 10.3 export_runs

### Proposed Columns

\| Column \| Type \|

\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \|

\| export_type \| VARCHAR(50) \|

\| export_format \| VARCHAR(50) \|

\| export_path \| TEXT \|

\| partition_strategy \| VARCHAR(100) \|

\| row_count \| BIGINT \|

\| created_at \| TIMESTAMP \|

\-\--

# 11. Proposed PostgreSQL DDL

## 11.1 players

CREATE TABLE players (

id BIGSERIAL PRIMARY KEY,

external_player_key UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,

first_name VARCHAR(100) NOT NULL,

last_name VARCHAR(100) NOT NULL,

gender VARCHAR(20),

birth_date DATE NOT NULL,

dominant_hand VARCHAR(10),

home_region_id BIGINT REFERENCES regions(id),

registration_date DATE NOT NULL,

initial_skill_seed NUMERIC(8,4),

player_status VARCHAR(30) DEFAULT 'ACTIVE',

generation_run_id BIGINT REFERENCES generation_runs(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_player_birth_date CHECK (birth_date < CURRENT_DATE),

CONSTRAINT chk_player_status CHECK (player_status IN ('ACTIVE', 'INACTIVE', 'RETIRED'))

);

\-\--

## 11.2 player_rating_history

CREATE TABLE player_rating_history (

id BIGSERIAL PRIMARY KEY,

player_id BIGINT NOT NULL REFERENCES players(id),

rating_date DATE NOT NULL,

rating_type VARCHAR(50) NOT NULL,

rating_value NUMERIC(8,3) NOT NULL,

confidence_score NUMERIC(8,3),

volatility_score NUMERIC(8,3),

expected_performance NUMERIC(8,3),

regional_adjustment_factor NUMERIC(8,4),

global_percentile NUMERIC(5,2),

match_count_used INTEGER,

calculation_version VARCHAR(50),

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_rating_value CHECK (rating_value >= 0 AND rating_value <= 5000),

CONSTRAINT chk_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 1)

);

\-\--

## 11.3 matches

CREATE TABLE matches (

id BIGSERIAL PRIMARY KEY,

tournament_id BIGINT REFERENCES tournaments(id),

match_date DATE NOT NULL,

region_id BIGINT REFERENCES regions(id),

match_type VARCHAR(50) NOT NULL,

court_type VARCHAR(50),

match_format VARCHAR(50),

winning_team_id BIGINT,

total_points_played INTEGER,

expected_competitiveness NUMERIC(8,3),

simulation_noise_factor NUMERIC(8,3),

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_match_type CHECK (match_type IN ('recreational', 'league', 'ladder', 'tournament', 'challenge', 'clinic', 'open_play'))

);

\-\--

## 11.4 match_teams

CREATE TABLE match_teams (

id BIGSERIAL PRIMARY KEY,

match_id BIGINT NOT NULL REFERENCES matches(id),

team_number INTEGER NOT NULL,

team_score INTEGER NOT NULL,

expected_win_probability NUMERIC(8,4),

average_team_rating NUMERIC(8,3),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_team_number CHECK (team_number IN (1, 2)),

UNIQUE (match_id, team_number)

);

\-\--

## 11.5 match_team_players

CREATE TABLE match_team_players (

id BIGSERIAL PRIMARY KEY,

match_team_id BIGINT NOT NULL REFERENCES match_teams(id),

player_id BIGINT NOT NULL REFERENCES players(id),

player_position INTEGER,

player_rating_at_match NUMERIC(8,3),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_player_position CHECK (player_position IN (1, 2)),

UNIQUE (match_team_id, player_id)

);

\-\--

## 11.6 regions

CREATE TABLE regions (

id BIGSERIAL PRIMARY KEY,

country_code VARCHAR(10) NOT NULL,

region_type VARCHAR(20),

region_name VARCHAR(255) NOT NULL,

state_province_code VARCHAR(10),

population BIGINT,

competitiveness_multiplier NUMERIC(8,4) DEFAULT 1.0,

latitude NUMERIC(10,6),

longitude NUMERIC(10,6),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

UNIQUE (country_code, region_name)

);

\-\--

## 11.7 first_names

CREATE TABLE first_names (

id BIGSERIAL PRIMARY KEY,

country_code VARCHAR(2) NOT NULL,

state_province_code VARCHAR(2) NOT NULL,

birth_year INTEGER NOT NULL,

gender VARCHAR(1) NOT NULL,

first_name VARCHAR(100) NOT NULL,

frequency_count INTEGER NOT NULL,

normalized_probability NUMERIC(12,8),

source_dataset VARCHAR(255),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_first_names_gender CHECK (gender IN ('M', 'F')),

CONSTRAINT chk_first_names_freq CHECK (frequency_count > 0),

CONSTRAINT chk_first_names_country CHECK (country_code IN ('US', 'CA'))

);

\-\--

## 11.8 last_names

CREATE TABLE last_names (

id BIGSERIAL PRIMARY KEY,

country_code VARCHAR(2) NOT NULL,

state_province_code VARCHAR(2) NOT NULL,

last_name VARCHAR(100) NOT NULL,

frequency_count INTEGER NOT NULL,

normalized_probability NUMERIC(12,8),

source_dataset VARCHAR(255),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_last_names_freq CHECK (frequency_count > 0),

CONSTRAINT chk_last_names_country CHECK (country_code IN ('US', 'CA'))

);

\-\--

## 11.9 clubs

CREATE TABLE clubs (

id BIGSERIAL PRIMARY KEY,

club_name VARCHAR(255) NOT NULL,

region_id BIGINT NOT NULL REFERENCES regions(id),

club_type VARCHAR(50),

competitiveness_level VARCHAR(50),

member_capacity INTEGER,

founding_date DATE,

indoor_court_count INTEGER DEFAULT 0,

outdoor_court_count INTEGER DEFAULT 0,

generation_run_id BIGINT REFERENCES generation_runs(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

UNIQUE (region_id, club_name),

CONSTRAINT chk_club_type CHECK (club_type IN ('public_park', 'private_club', 'community_center', 'resort', 'university', 'municipal_recreation', 'dedicated_facility')),

CONSTRAINT chk_court_counts CHECK (indoor_court_count >= 0 AND outdoor_court_count >= 0)

);

\-\--

## 11.10 club_memberships

CREATE TABLE club_memberships (

id BIGSERIAL PRIMARY KEY,

player_id BIGINT NOT NULL REFERENCES players(id),

club_id BIGINT NOT NULL REFERENCES clubs(id),

membership_type VARCHAR(50) DEFAULT 'member',

start_date DATE NOT NULL,

end_date DATE,

is_primary BOOLEAN DEFAULT true,

generation_run_id BIGINT REFERENCES generation_runs(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_membership_dates CHECK (end_date IS NULL OR end_date >= start_date)

);

\-\--

## 11.11 teams

CREATE TABLE teams (

id BIGSERIAL PRIMARY KEY,

team_type VARCHAR(50) NOT NULL,

team_status VARCHAR(30) DEFAULT 'active',

formation_date DATE NOT NULL,

dissolution_date DATE,

chemistry_score NUMERIC(8,4),

persistence_probability NUMERIC(5,4),

generation_run_id BIGINT REFERENCES generation_runs(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_team_type CHECK (team_type IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles')),

CONSTRAINT chk_team_status CHECK (team_status IN ('active', 'dormant', 'retired')),

CONSTRAINT chk_team_dates CHECK (dissolution_date IS NULL OR dissolution_date >= formation_date)

);

\-\--

## 11.12 team_memberships

CREATE TABLE team_memberships (

id BIGSERIAL PRIMARY KEY,

team_id BIGINT NOT NULL REFERENCES teams(id),

player_id BIGINT NOT NULL REFERENCES players(id),

player_position INTEGER NOT NULL,

joined_date DATE NOT NULL,

left_date DATE,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_position CHECK (player_position IN (1, 2)),

CONSTRAINT chk_membership_dates CHECK (left_date IS NULL OR left_date >= joined_date),

UNIQUE (team_id, player_id, joined_date)

);

\-\--

## 11.13 monthly_batches

CREATE TABLE monthly_batches (

id BIGSERIAL PRIMARY KEY,

generation_run_id BIGINT NOT NULL REFERENCES generation_runs(id),

batch_month DATE NOT NULL,

batch_sequence INTEGER NOT NULL,

batch_type VARCHAR(30) NOT NULL DEFAULT 'future_increment',

active_player_count_start INTEGER,

new_player_count INTEGER,

active_player_count_end INTEGER,

match_count_generated INTEGER,

rating_update_count INTEGER,

assessment_update_count INTEGER,

processing_status VARCHAR(30) NOT NULL DEFAULT 'pending',

started_at TIMESTAMP,

completed_at TIMESTAMP,

error_message TEXT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

UNIQUE (generation_run_id, batch_month),

CONSTRAINT chk_batch_type CHECK (batch_type IN ('historical_initial', 'future_increment')),

CONSTRAINT chk_processing_status CHECK (processing_status IN ('pending', 'running', 'validating', 'exporting', 'completed', 'failed', 'superseded'))

);

\-\--

## 11.14 generation_runs

CREATE TABLE generation_runs (

id BIGSERIAL PRIMARY KEY,

generation_name VARCHAR(255) NOT NULL,

seed_value BIGINT NOT NULL,

simulation_version VARCHAR(100),

parameter_snapshot JSONB,

started_at TIMESTAMP,

completed_at TIMESTAMP,

status VARCHAR(30) NOT NULL DEFAULT 'pending',

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_generation_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled'))

);

\-\--

## 11.15 tournaments

CREATE TABLE tournaments (

id BIGSERIAL PRIMARY KEY,

tournament_name VARCHAR(255) NOT NULL,

region_id BIGINT REFERENCES regions(id),

tournament_start_date DATE NOT NULL,

tournament_end_date DATE NOT NULL,

tournament_type VARCHAR(50),

skill_division VARCHAR(50),

participant_count INTEGER,

generation_run_id BIGINT REFERENCES generation_runs(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_tournament_dates CHECK (tournament_end_date >= tournament_start_date)

);

\-\--

## 11.16 player_assessment_history

CREATE TABLE player_assessment_history (

id BIGSERIAL PRIMARY KEY,

player_id BIGINT NOT NULL REFERENCES players(id),

assessment_date DATE NOT NULL,

assessment_type VARCHAR(100) NOT NULL,

assessment_value NUMERIC(8,3),

confidence_score NUMERIC(8,3),

derived_from_matches INTEGER,

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_assessment_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1)

);

\-\--

## 11.17 player_registrations

CREATE TABLE player_registrations (

id BIGSERIAL PRIMARY KEY,

player_id BIGINT NOT NULL REFERENCES players(id),

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

registration_month DATE NOT NULL,

registration_source VARCHAR(50) NOT NULL DEFAULT 'synthetic',

assigned_region_id BIGINT REFERENCES regions(id),

initial_rating_value NUMERIC(8,3),

initial_confidence_score NUMERIC(8,3),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

UNIQUE (player_id, batch_id)

);

\-\--

## 11.18 batch_runs

CREATE TABLE batch_runs (

id BIGSERIAL PRIMARY KEY,

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

run_status VARCHAR(30) NOT NULL DEFAULT 'pending',

started_at TIMESTAMP,

completed_at TIMESTAMP,

error_message TEXT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_run_status CHECK (run_status IN ('pending', 'running', 'completed', 'failed'))

);

\-\--

## 11.19 uploaded_files

CREATE TABLE uploaded_files (

id BIGSERIAL PRIMARY KEY,

original_filename VARCHAR(255) NOT NULL,

stored_filename VARCHAR(255) NOT NULL,

file_type VARCHAR(50),

file_size_bytes BIGINT,

upload_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

validation_status VARCHAR(30),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_file_size CHECK (file_size_bytes >= 0)

);

\-\--

## 11.20 export_runs

CREATE TABLE export_runs (

id BIGSERIAL PRIMARY KEY,

batch_id BIGINT REFERENCES monthly_batches(id),

export_type VARCHAR(50) NOT NULL,

export_format VARCHAR(50) NOT NULL,

export_path TEXT NOT NULL,

partition_strategy VARCHAR(100),

row_count BIGINT,

schema_hash VARCHAR(64),

checksum VARCHAR(64),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_export_format CHECK (export_format IN ('parquet', 'csv', 'json', 'sql'))

);

\-\--

## 11.21 validation_results

CREATE TABLE validation_results (

id BIGSERIAL PRIMARY KEY,

batch_id BIGINT REFERENCES monthly_batches(id),

validation_rule_id VARCHAR(100) NOT NULL,

validation_rule_name VARCHAR(255) NOT NULL,

severity VARCHAR(30) NOT NULL,

entity_type VARCHAR(100),

entity_id BIGINT,

field_name VARCHAR(100),

observed_value TEXT,

expected_value TEXT,

validation_message TEXT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_severity CHECK (severity IN ('info', 'warning', 'error', 'blocker'))

);

\-\--

## 11.22 job_status

CREATE TABLE job_status (

id BIGSERIAL PRIMARY KEY,

job_type VARCHAR(50) NOT NULL,

job_id VARCHAR(100) NOT NULL UNIQUE,

status VARCHAR(30) NOT NULL DEFAULT 'pending',

current_phase VARCHAR(100),

percent_complete NUMERIC(5,2),

current_message TEXT,

started_at TIMESTAMP,

completed_at TIMESTAMP,

error_message TEXT,

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

CONSTRAINT chk_job_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),

CONSTRAINT chk_percent_complete CHECK (percent_complete >= 0 AND percent_complete <= 100)

);

\-\--

# 12. Comprehensive Index Catalog

## Core Entity Indexes

-- players table indexes
CREATE INDEX idx_players_region ON players(home_region_id);
CREATE INDEX idx_players_status ON players(player_status);
CREATE INDEX idx_players_registration_date ON players(registration_date);
CREATE INDEX idx_players_generation_run ON players(generation_run_id);

-- player_rating_history indexes
CREATE INDEX idx_rating_player_date ON player_rating_history(player_id, rating_date DESC);
CREATE INDEX idx_rating_batch ON player_rating_history(batch_id);
CREATE INDEX idx_rating_date_type ON player_rating_history(rating_date, rating_type);
CREATE INDEX idx_rating_value ON player_rating_history(rating_value);

-- player_assessment_history indexes
CREATE INDEX idx_assessment_player_date ON player_assessment_history(player_id, assessment_date DESC);
CREATE INDEX idx_assessment_batch ON player_assessment_history(batch_id);

-- player_registrations indexes
CREATE INDEX idx_player_registrations_batch ON player_registrations(batch_id);
CREATE INDEX idx_player_registrations_player ON player_registrations(player_id);
CREATE INDEX idx_player_registrations_month ON player_registrations(registration_month);

-- matches indexes
CREATE INDEX idx_matches_date ON matches(match_date);
CREATE INDEX idx_matches_batch ON matches(batch_id);
CREATE INDEX idx_matches_region ON matches(region_id);
CREATE INDEX idx_matches_tournament ON matches(tournament_id);
CREATE INDEX idx_matches_type ON matches(match_type);

-- match_teams indexes
CREATE INDEX idx_match_teams_match ON match_teams(match_id);

-- match_team_players indexes
CREATE INDEX idx_match_team_players_team ON match_team_players(match_team_id);
CREATE INDEX idx_match_team_players_player ON match_team_players(player_id);

-- tournaments indexes
CREATE INDEX idx_tournaments_region ON tournaments(region_id);
CREATE INDEX idx_tournaments_start_date ON tournaments(tournament_start_date);

-- monthly_batches indexes
CREATE INDEX idx_monthly_batches_generation_run ON monthly_batches(generation_run_id);
CREATE INDEX idx_monthly_batches_month ON monthly_batches(batch_month);
CREATE INDEX idx_monthly_batches_status ON monthly_batches(processing_status);

-- batch_runs indexes
CREATE INDEX idx_batch_runs_batch ON batch_runs(batch_id);
CREATE INDEX idx_batch_runs_status ON batch_runs(run_status);

## Reference Data Indexes

-- first_names indexes
CREATE INDEX idx_first_names_lookup ON first_names(country_code, state_province_code, birth_year, gender);
CREATE INDEX idx_first_names_probability ON first_names(normalized_probability);
CREATE INDEX idx_first_names_country ON first_names(country_code);

-- last_names indexes
CREATE INDEX idx_last_names_lookup ON last_names(country_code, state_province_code);
CREATE INDEX idx_last_names_country ON last_names(country_code);

-- clubs indexes
CREATE INDEX idx_clubs_region ON clubs(region_id);
CREATE INDEX idx_clubs_type ON clubs(club_type);
CREATE INDEX idx_clubs_generation_run ON clubs(generation_run_id);

-- club_memberships indexes
CREATE INDEX idx_club_memberships_player ON club_memberships(player_id);
CREATE INDEX idx_club_memberships_club ON club_memberships(club_id);
CREATE INDEX idx_club_memberships_dates ON club_memberships(start_date, end_date);
CREATE INDEX idx_club_memberships_primary ON club_memberships(player_id, is_primary) WHERE is_primary = true;

-- teams indexes
CREATE INDEX idx_teams_type ON teams(team_type);
CREATE INDEX idx_teams_status ON teams(team_status);
CREATE INDEX idx_teams_formation_date ON teams(formation_date);

-- team_memberships indexes
CREATE INDEX idx_team_memberships_team ON team_memberships(team_id);
CREATE INDEX idx_team_memberships_player ON team_memberships(player_id);
CREATE INDEX idx_team_memberships_dates ON team_memberships(joined_date, left_date);

-- generation_runs indexes
CREATE INDEX idx_generation_runs_status ON generation_runs(status);
CREATE INDEX idx_generation_runs_started ON generation_runs(started_at);

-- uploaded_files indexes
CREATE INDEX idx_uploaded_files_timestamp ON uploaded_files(upload_timestamp);
CREATE INDEX idx_uploaded_files_status ON uploaded_files(validation_status);

-- export_runs indexes
CREATE INDEX idx_export_runs_batch ON export_runs(batch_id);
CREATE INDEX idx_export_runs_type ON export_runs(export_type);
CREATE INDEX idx_export_runs_created ON export_runs(created_at);

-- validation_results indexes
CREATE INDEX idx_validation_results_batch ON validation_results(batch_id);
CREATE INDEX idx_validation_results_severity ON validation_results(severity);
CREATE INDEX idx_validation_results_rule ON validation_results(validation_rule_id);

-- job_status indexes
CREATE INDEX idx_job_status_type ON job_status(job_type);
CREATE INDEX idx_job_status_status ON job_status(status);
CREATE INDEX idx_job_status_started ON job_status(started_at);

\-\--

# 13. Partitioning Recommendations

Recommended partition candidates:

- player_rating_history

- player_assessment_history

- matches

- match_team_players

Recommended partitioning strategy:

- RANGE partition by month or year

\-\--

# 14. Parquet Export Strategy

## 14.1 Partition Strategy

The platform uses a hybrid directory and column-based partitioning approach:

### Directory Structure Partitioning:

```
data/parquet/
├── historical/          # Initial 12-month baseline
│   ├── players/
│   ├── matches/
│   ├── ratings/
│   └── assessments/
├── monthly/             # Future monthly batches
│   ├── batch_month=2024-01/
│   ├── batch_month=2024-02/
│   └── ...
├── reference/           # Static reference data
│   ├── regions/
│   ├── clubs/
│   └── names/
└── metadata/            # Export manifests and schemas
```

### Column-Based Partitioning (within directories):

- `country_code` - for cross-border analysis
- `region_id` - for regional segmentation
- `batch_month` - for temporal partitioning
- `rating_type` - for rating history tables

### Export Naming Convention:

```
{table_name}_{generation_run_id}_{batch_sequence}.parquet

Examples:
players_001_initial.parquet
matches_001_batch_001.parquet
rating_history_001_batch_012.parquet
```

## 14.2 Export Manifest Requirements

Every export must generate a manifest JSON file containing:

```json
{
  "export_id": "uuid",
  "generation_run_id": 1,
  "batch_id": 12,
  "export_timestamp": "2024-05-10T14:30:00Z",
  "files": [
    {
      "table_name": "matches",
      "file_path": "monthly/batch_month=2024-01/matches_001_batch_001.parquet",
      "row_count": 125000,
      "file_size_bytes": 45678901,
      "schema_hash": "sha256:abc123...",
      "checksum": "md5:def456...",
      "partitions": {"batch_month": "2024-01"}
    }
  ]
}
```

\-\--

# 15. Future Expansion Areas

Future schema support:

- Injury simulations

- Weather effects

- Court surfaces

- Betting markets

- AI coaching analytics

- Streaming telemetry

- Wearable metrics

- ML feature stores

- Vector similarity search

\-\--

# 16. Validation Rules Catalog

## 16.1 Referential Integrity Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| REF-001 | All player_rating_history.player_id must exist in players | blocker | Foreign key validation |
| REF-002 | All matches.batch_id must exist in monthly_batches | blocker | Foreign key validation |
| REF-003 | All match_team_players.player_id must exist in players | blocker | Foreign key validation |
| REF-004 | All club_memberships.club_id must exist in clubs | blocker | Foreign key validation |
| REF-005 | All player_registrations.player_id must exist in players | blocker | Foreign key validation |

## 16.2 Count Reconciliation Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| CNT-001 | monthly_batches.new_player_count equals player_registrations count | error | Aggregate comparison |
| CNT-002 | monthly_batches.match_count_generated equals matches count for batch | error | Aggregate comparison |
| CNT-003 | Every match_team must have exactly 2 match_team_players | blocker | Group by validation |
| CNT-004 | Every match must have exactly 2 match_teams | blocker | Group by validation |
| CNT-005 | Every team must have exactly 2 team_memberships (active) | error | Group by validation |

## 16.3 Date and Temporal Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| DATE-001 | All match_date must fall within batch_month | blocker | Date range check |
| DATE-002 | player.birth_date must be before registration_date | error | Date comparison |
| DATE-003 | rating_date must not be in the future | error | Date comparison |
| DATE-004 | tournament_end_date must be >= tournament_start_date | error | Date comparison |
| DATE-005 | club_membership end_date must be >= start_date | error | Date comparison |

## 16.4 Rating and Score Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| RATING-001 | rating_value must be between 0 and 5000 | blocker | Range check |
| RATING-002 | confidence_score must be between 0 and 1 | error | Range check |
| RATING-003 | volatility_score must be non-negative | warning | Range check |
| RATING-004 | Initial player ratings should cluster near 1500 | warning | Distribution check |
| RATING-005 | Match team scores must be non-negative integers | blocker | Type and range check |

## 16.5 Distribution Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| DIST-001 | Weekend match concentration should be 40-60% for recreational | warning | Percentage calculation |
| DIST-002 | Gender distribution should be within configured tolerance | warning | Percentage calculation |
| DIST-003 | Regional player allocation should match population weights | warning | Chi-square test |
| DIST-004 | Match type distribution should match configured weights | warning | Percentage calculation |
| DIST-005 | Age distribution should follow configured profile | warning | Distribution comparison |

## 16.6 Business Logic Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| BIZ-001 | Players cannot appear in overlapping matches on same date | blocker | Temporal overlap check |
| BIZ-002 | Team chemistry score must be between 0 and 1 | warning | Range check |
| BIZ-003 | Match winning_team_id must be one of the match_teams | blocker | Join validation |
| BIZ-004 | Player cannot have multiple active primary club memberships | error | Group by validation |
| BIZ-005 | New player count should approximate configured growth rate | warning | Percentage tolerance |

## 16.7 Export Readiness Validations

| Rule ID | Description | Severity | Check |
|---------|-------------|----------|-------|
| EXP-001 | All exported tables must have created_at timestamps | blocker | Column presence check |
| EXP-002 | Parquet row count must equal database row count | blocker | Count comparison |
| EXP-003 | Export manifest checksums must be present | error | Manifest validation |
| EXP-004 | Schema hash must match expected schema version | error | Hash comparison |
| EXP-005 | No NULL values in required export columns | blocker | NULL check |

## 16.8 Validation Severity Definitions

- **blocker**: Prevents batch completion; must be fixed before proceeding
- **error**: Serious issue that should be addressed but may allow conditional completion
- **warning**: Deviation from expected patterns; logged for review
- **info**: Informational finding; does not block processing

## 16.9 Validation Execution Sequence

1. Schema validation (table existence, column types)
2. Referential integrity validation
3. Count reconciliation validation
4. Date and temporal validation
5. Rating and score validation
6. Distribution validation
7. Business logic validation
8. Export readiness validation

\-\--

# 17. Medallion Architecture and Data Lineage

## 17.1 Bronze Layer (Raw Ingestion)

- uploaded_files: Source file metadata
- Raw Parquet ingestion staging tables (future)
- Census reference data as loaded

## 17.2 Silver Layer (Cleaned and Validated)

- regions: Validated regional reference data
- clubs: Generated club inventory
- players: Core player identity
- first_names, last_names: Consolidated normalized USA and Canada name frequency data
- teams: Validated team formations
- club_memberships: Validated membership assignments

## 17.3 Gold Layer (Analytics-Ready)

- player_rating_history: Time-series rating data
- player_assessment_history: Time-series assessment data
- matches: Match-level analytical data
- match_teams: Team performance data
- match_team_players: Player participation data
- player_registrations: Player lifecycle tracking
- monthly_batches: Batch processing metadata
- validation_results: Data quality scorecards
- export_runs: Published data packages

## 17.4 Operational Layer (Platform Metadata)

- generation_runs: Simulation execution control
- batch_runs: Batch execution tracking
- job_status: Real-time job monitoring
- uploaded_files: File intake tracking

\-\--

# 18. Final Guidance

This schema is intentionally designed to support:

- Large-scale synthetic generation

- Historical replayability

- Time-series analytics

- Monthly incremental simulation

- Educational analytics workloads

- ML experimentation

- Reproducible data generation

- Longitudinal player analysis

The schema prioritizes historical integrity, modularity, analytics
readiness, and scalable synthetic simulation.

\-\--

# 20. Revised Simulation Design Assumption --- Unified Monthly Batch Processing

## 17.1 Design Change

The simulation should no longer treat the first 12 months of match
history as a separate historical generation process.

Instead, the platform should use one unified monthly batch engine for
all match generation, including:

- the initial 12-month historical period

- every future monthly increment

- new player registration files

- monthly match result files

- rating recalculation

- assessment recalculation

- confidence recalculation

- validation

- export generation

This means the system first creates the initial player foundation, then
applies monthly batches sequentially.

The initial 12 months are simply the first 12 batch periods.

## 17.2 Updated Processing Sequence

The corrected simulation lifecycle is:

1\. Create the initial generation run.

2\. Load or generate regional reference data.

3\. Load or generate name reference data.

4\. Create the initial player population.

5\. Assign players to regions.

6\. Assign static player attributes.

7\. Create the first monthly batch.

8\. Add new players for that month based on the configured growth rate.

9\. Generate match results for that month.

10\. Apply match outcomes to player ratings.

11\. Recalculate confidence and assessment metrics.

12\. Store rating history and assessment history for the month.

13\. Validate the batch.

14\. Export monthly data if configured.

15\. Repeat for each of the first 12 months.

16\. Continue the same process for future monthly increments.

## 17.3 Initial 12 Months as Standard Batches

The first 12 months should be represented in \`monthly_batches\`.

Each month should have the same lifecycle as any future month.

\| Batch Sequence \| Batch Month \| Purpose \|

\|\-\--:\|\-\--\|\-\--\|

\| 1 \| Historical Month 1 \| Initial simulated match activity \|

\| 2 \| Historical Month 2 \| Continued player development \|

\| 3 \| Historical Month 3 \| New players plus monthly matches \|

\| 4 \| Historical Month 4 \| Rating updates and confidence changes \|

\| \... \| \... \| \... \|

\| 12 \| Historical Month 12 \| Final historical baseline month \|

\| 13 \| Future Month 1 \| First staged future release \|

\| 14 \| Future Month 2 \| Second staged future release \|

## 17.4 New Player Introduction During Historical Batches

New players are introduced during the initial 12-month period using the
same logic as future monthly batches.

Default assumption:

monthly_player_growth_rate = 0.02

This means each monthly batch may add approximately 2% new players
relative to the active population, subject to later configuration.

The growth process should create:

- a new player registration batch file or table record

- new \`players\` rows

- initial rating history records

- initial assessment history records

- regional assignments

- name assignments

- generation metadata linking the new players to the batch

## 17.5 New Table: player_registrations

Tracks players introduced through each monthly batch.

\| Column \| Type \| Description \|

\|\-\--\|\-\--\|\-\--\|

\| id \| BIGSERIAL PK \| Registration record identifier \|

\| player_id \| BIGINT FK \| Registered player \|

\| batch_id \| BIGINT FK \| Monthly batch that introduced the player \|

\| registration_month \| DATE \| Month of registration \|

\| registration_source \| VARCHAR(50) \| synthetic, uploaded_file,
manual_seed \|

\| assigned_region_id \| BIGINT FK \| Region assigned at registration \|

\| initial_rating_value \| NUMERIC(8,3) \| Starting rating \|

\| initial_confidence_score \| NUMERIC(8,3) \| Starting confidence \|

\| created_at \| TIMESTAMP \| Insert timestamp \|

CREATE TABLE player_registrations (

id BIGSERIAL PRIMARY KEY,

player_id BIGINT NOT NULL REFERENCES players(id),

batch_id BIGINT NOT NULL REFERENCES monthly_batches(id),

registration_month DATE NOT NULL,

registration_source VARCHAR(50) NOT NULL DEFAULT \'synthetic\',

assigned_region_id BIGINT REFERENCES regions(id),

initial_rating_value NUMERIC(8,3),

initial_confidence_score NUMERIC(8,3),

created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

UNIQUE (player_id, batch_id)

);

CREATE INDEX idx_player_registrations_batch

ON player_registrations(batch_id);

CREATE INDEX idx_player_registrations_player

ON player_registrations(player_id);

CREATE INDEX idx_player_registrations_month

ON player_registrations(registration_month);

## 17.6 Revised Role of generation_runs

\`generation_runs\` should represent the overall simulation scenario,
not the full creation of all historical matches.

A generation run creates the initial controlled environment.

Monthly match activity belongs to \`monthly_batches\`.

generation_runs

└── monthly_batches

├── player_registrations

├── matches

├── player_rating_history

└── player_assessment_history

## 17.7 Revised Role of monthly_batches

\`monthly_batches\` becomes the central control table for simulation
progression.

Recommended additional columns:

\| Column \| Type \| Description \|

\|\-\--\|\-\--\|\-\--\|

\| generation_run_id \| BIGINT FK \| Parent simulation scenario \|

\| batch_type \| VARCHAR(30) \| historical_initial or future_increment
\|

\| active_player_count_start \| INTEGER \| Active players at start of
month \|

\| new_player_count \| INTEGER \| Players added this month \|

\| active_player_count_end \| INTEGER \| Active players after intake \|

\| match_count_generated \| INTEGER \| Matches generated this month \|

\| rating_update_count \| INTEGER \| Rating rows produced \|

\| assessment_update_count \| INTEGER \| Assessment rows produced \|

ALTER TABLE monthly_batches

ADD COLUMN generation_run_id BIGINT REFERENCES generation_runs(id),

ADD COLUMN batch_type VARCHAR(30) NOT NULL DEFAULT \'future_increment\',

ADD COLUMN active_player_count_start INTEGER,

ADD COLUMN active_player_count_end INTEGER,

ADD COLUMN match_count_generated INTEGER,

ADD COLUMN rating_update_count INTEGER,

ADD COLUMN assessment_update_count INTEGER;

## 17.8 Match Generation Rule

Every match must be associated with a monthly batch.

ALTER TABLE matches

ADD COLUMN batch_id BIGINT REFERENCES monthly_batches(id);

CREATE INDEX idx_matches_batch

ON matches(batch_id);

## 17.9 Rating and Assessment Rule

Every rating and assessment history record generated after the player
foundation is created should be associated with a monthly batch.

Note: The DDL in Section 11 now includes batch_id as NOT NULL for both
player_rating_history and player_assessment_history tables. No ALTER
statements are needed if building from the complete DDL.

## 17.10 Updated Batch Engine Responsibilities

The monthly batch processor must:

- determine the next month to process

- calculate the starting active player population

- generate new player registrations

- insert new player records

- assign names from USA/Canada frequency tables

- assign home regions

- generate monthly match schedules

- generate match outcomes with configurable noise

- calculate rating deltas

- update rating history

- update assessment history

- calculate rating confidence

- validate row counts and referential integrity

- export monthly Parquet files

- record batch completion metadata

## 17.11 Updated Design Principle

The platform should have one simulation progression engine.

Avoid separate logic for:

- initial historical match creation

- future monthly batch processing

Both historical and future activity should use the same monthly batch
workflow so that the project remains reproducible, easier to test,
easier to explain to students, and easier to extend.

\-\--

# 19. Critical Design Prohibitions

## 19.1 PROHIBITED: Age Column on players Table

**DO NOT** add an `age` column to the `players` table. Age must be derived from `birth_date` at query time using the appropriate reference date.

**Rationale**: A static age value becomes incorrect as time progresses. The simulation spans multiple years, and age must be calculated relative to the analysis date.

## 19.2 PROHIBITED: Current Rating on players Table

**DO NOT** add `current_rating`, `rating`, or any rating value directly to the `players` table. All ratings must be stored in `player_rating_history` with effective dates.

**Rationale**: Ratings change over time. Point-in-time rating queries must retrieve the most recent rating record as of the analysis date.

## 19.3 PROHIBITED: Mutable Historical Records

**DO NOT** update historical rating or assessment records in place. All corrections or recalculations must append new records with later timestamps or higher version numbers.

**Rationale**: Historical integrity is essential for reproducibility and audit trails.

## 19.4 REQUIRED: Batch Association

**REQUIRED**: All generated matches, ratings, and assessments must include a non-null `batch_id` foreign key to `monthly_batches`.

**Rationale**: Every piece of generated data must be traceable to its originating batch for reproducibility and incremental regeneration.

## 19.5 REQUIRED: Timestamp Columns

**REQUIRED**: All tables must include `created_at` and, where applicable, `updated_at` timestamp columns with `DEFAULT CURRENT_TIMESTAMP`.

**Rationale**: Operational observability and debugging require creation tracking.

## 19.6 REQUIRED: Unique Constraints

**REQUIRED**: Natural business keys must be enforced with unique constraints:

- `players.external_player_key` must be UNIQUE
- `regions(country_code, region_name)` must be UNIQUE
- `clubs(region_id, club_name)` must be UNIQUE
- `monthly_batches(generation_run_id, batch_month)` must be UNIQUE

**Rationale**: Natural key uniqueness prevents data duplication and ensures referential integrity.
