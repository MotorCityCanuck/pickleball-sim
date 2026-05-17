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

-- 2. regions
CREATE TABLE regions (
    id BIGSERIAL PRIMARY KEY,
    country_code VARCHAR(10) NOT NULL,
    region_type VARCHAR(20),
    region_name VARCHAR(255) NOT NULL,
    state_province_code VARCHAR(10),
    population BIGINT,
    selection_probability NUMERIC(12,8),
    competitiveness_multiplier NUMERIC(8,4) DEFAULT 1.0,
    latitude NUMERIC(10,6),
    longitude NUMERIC(10,6),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (country_code, state_province_code, region_name)
);

-- 3. monthly_batches
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

-- 4. players
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

-- 5. player_rating_history
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

-- 6. player_assessment_history
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

-- 7. player_registrations
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

-- 8. clubs
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

-- 9. club_memberships
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

-- 10. teams
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

-- 11. team_memberships
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

-- 12. tournaments
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

-- 13. matches
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

-- 14. match_teams
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

-- 15. match_team_players
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

-- 16. first_names (consolidated USA and Canada)
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

-- 17. last_names (consolidated USA and Canada)
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

-- 18. batch_runs
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

-- 19. uploaded_files
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

-- 20. export_runs
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

-- 21. validation_results
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

-- 22. job_status
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

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_players_region ON players(home_region_id);
CREATE INDEX idx_players_status ON players(player_status);
CREATE INDEX idx_players_registration_date ON players(registration_date);
CREATE INDEX idx_players_generation_run ON players(generation_run_id);

CREATE INDEX idx_rating_player_date ON player_rating_history(player_id, rating_date DESC);
CREATE INDEX idx_rating_batch ON player_rating_history(batch_id);
CREATE INDEX idx_rating_date_type ON player_rating_history(rating_date, rating_type);
CREATE INDEX idx_rating_value ON player_rating_history(rating_value);

CREATE INDEX idx_assessment_player_date ON player_assessment_history(player_id, assessment_date DESC);
CREATE INDEX idx_assessment_batch ON player_assessment_history(batch_id);

CREATE INDEX idx_player_registrations_batch ON player_registrations(batch_id);
CREATE INDEX idx_player_registrations_player ON player_registrations(player_id);
CREATE INDEX idx_player_registrations_month ON player_registrations(registration_month);

CREATE INDEX idx_matches_date ON matches(match_date);
CREATE INDEX idx_matches_batch ON matches(batch_id);
CREATE INDEX idx_matches_region ON matches(region_id);
CREATE INDEX idx_matches_tournament ON matches(tournament_id);
CREATE INDEX idx_matches_type ON matches(match_type);

CREATE INDEX idx_match_teams_match ON match_teams(match_id);

CREATE INDEX idx_match_team_players_team ON match_team_players(match_team_id);
CREATE INDEX idx_match_team_players_player ON match_team_players(player_id);

CREATE INDEX idx_tournaments_region ON tournaments(region_id);
CREATE INDEX idx_tournaments_start_date ON tournaments(tournament_start_date);

CREATE INDEX idx_monthly_batches_generation_run ON monthly_batches(generation_run_id);
CREATE INDEX idx_monthly_batches_month ON monthly_batches(batch_month);
CREATE INDEX idx_monthly_batches_status ON monthly_batches(processing_status);

CREATE INDEX idx_batch_runs_batch ON batch_runs(batch_id);
CREATE INDEX idx_batch_runs_status ON batch_runs(run_status);

CREATE INDEX idx_first_names_lookup ON first_names(country_code, state_province_code, birth_year, gender);
CREATE INDEX idx_first_names_probability ON first_names(normalized_probability);
CREATE INDEX idx_first_names_country ON first_names(country_code);

CREATE INDEX idx_last_names_lookup ON last_names(country_code, state_province_code);
CREATE INDEX idx_last_names_country ON last_names(country_code);

CREATE INDEX idx_clubs_region ON clubs(region_id);
CREATE INDEX idx_clubs_type ON clubs(club_type);
CREATE INDEX idx_clubs_generation_run ON clubs(generation_run_id);

CREATE INDEX idx_club_memberships_player ON club_memberships(player_id);
CREATE INDEX idx_club_memberships_club ON club_memberships(club_id);
CREATE INDEX idx_club_memberships_dates ON club_memberships(start_date, end_date);
CREATE INDEX idx_club_memberships_primary ON club_memberships(player_id, is_primary) WHERE is_primary = true;

CREATE INDEX idx_teams_type ON teams(team_type);
CREATE INDEX idx_teams_status ON teams(team_status);
CREATE INDEX idx_teams_formation_date ON teams(formation_date);

CREATE INDEX idx_team_memberships_team ON team_memberships(team_id);
CREATE INDEX idx_team_memberships_player ON team_memberships(player_id);
CREATE INDEX idx_team_memberships_dates ON team_memberships(joined_date, left_date);

CREATE INDEX idx_generation_runs_status ON generation_runs(status);
CREATE INDEX idx_generation_runs_started ON generation_runs(started_at);

CREATE INDEX idx_uploaded_files_timestamp ON uploaded_files(upload_timestamp);
CREATE INDEX idx_uploaded_files_status ON uploaded_files(validation_status);

CREATE INDEX idx_export_runs_batch ON export_runs(batch_id);
CREATE INDEX idx_export_runs_type ON export_runs(export_type);
CREATE INDEX idx_export_runs_created ON export_runs(created_at);

CREATE INDEX idx_validation_results_batch ON validation_results(batch_id);
CREATE INDEX idx_validation_results_severity ON validation_results(severity);
CREATE INDEX idx_validation_results_rule ON validation_results(validation_rule_id);

CREATE INDEX idx_job_status_type ON job_status(job_type);
CREATE INDEX idx_job_status_status ON job_status(status);
CREATE INDEX idx_job_status_started ON job_status(started_at);
