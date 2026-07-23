-- ============================================
-- Pickleball Simulation Platform - Database Schema
-- Generated from SQLAlchemy ORM metadata
-- Do not edit by hand; run backend/scripts/export_schema_from_orm.py
-- Total Tables: 54
-- Explicit Indexes: 148
-- PostgreSQL 16+
-- ============================================

-- ============================================
-- TABLES
-- ============================================

CREATE TABLE configuration_profiles (
	id BIGSERIAL NOT NULL, 
	profile_name VARCHAR(255) NOT NULL, 
	description TEXT, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_configuration_profile_name UNIQUE (profile_name)
);

CREATE TABLE first_names (
	id BIGSERIAL NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(2) NOT NULL, 
	birth_year INTEGER NOT NULL, 
	gender VARCHAR(1) NOT NULL, 
	first_name VARCHAR(100) NOT NULL, 
	frequency_count INTEGER NOT NULL, 
	normalized_probability NUMERIC(12, 8), 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_first_names_gender CHECK (gender IN ('M', 'F')), 
	CONSTRAINT chk_first_names_freq CHECK (frequency_count > 0), 
	CONSTRAINT chk_first_names_country CHECK (country_code IN ('US', 'CA'))
);

CREATE TABLE generation_runs (
	id BIGSERIAL NOT NULL, 
	generation_name VARCHAR(255) NOT NULL, 
	seed_value BIGINT NOT NULL, 
	simulation_version VARCHAR(100), 
	parameter_snapshot JSONB, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR(30) DEFAULT 'not_started' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_generation_status CHECK (status IN ('not_started', 'running', 'succeeded', 'failed'))
);

CREATE TABLE job_status (
	id BIGSERIAL NOT NULL, 
	job_type VARCHAR(50) NOT NULL, 
	job_id VARCHAR(100) NOT NULL, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	current_phase VARCHAR(100), 
	percent_complete NUMERIC(5, 2), 
	current_message TEXT, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_job_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed')), 
	CONSTRAINT chk_percent_complete CHECK (percent_complete >= 0 AND percent_complete <= 100), 
	UNIQUE (job_id)
);

CREATE TABLE last_names (
	id BIGSERIAL NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(2) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	frequency_count INTEGER NOT NULL, 
	bias_multiplier NUMERIC(10, 4), 
	adjusted_frequency_count NUMERIC(18, 4), 
	normalized_probability NUMERIC(12, 8), 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_last_names_freq CHECK (frequency_count > 0), 
	CONSTRAINT chk_last_names_country CHECK (country_code IN ('US', 'CA'))
);

CREATE TABLE ops.background_workers (
	worker_id VARCHAR(64) NOT NULL, 
	worker_type VARCHAR(50) NOT NULL, 
	host_name VARCHAR(255), 
	process_id INTEGER, 
	started_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	last_heartbeat_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	status VARCHAR(30) DEFAULT 'running' NOT NULL, 
	metadata_json JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (worker_id), 
	CONSTRAINT chk_background_workers_status CHECK (status IN ('running', 'stopped', 'failed'))
);

CREATE TABLE regions (
	id BIGSERIAL NOT NULL, 
	country_code VARCHAR(10) NOT NULL, 
	region_type VARCHAR(20), 
	region_name VARCHAR(255) NOT NULL, 
	state_province_code VARCHAR(10), 
	population BIGINT, 
	selection_probability NUMERIC(12, 8), 
	competitiveness_multiplier NUMERIC(8, 4) DEFAULT 1.0, 
	latitude NUMERIC(10, 6), 
	longitude NUMERIC(10, 6), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_region_country_state_name UNIQUE (country_code, state_province_code, region_name)
);

CREATE TABLE uploaded_files (
	id BIGSERIAL NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	stored_filename VARCHAR(255) NOT NULL, 
	file_type VARCHAR(50), 
	file_size_bytes BIGINT, 
	upload_timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	validation_status VARCHAR(30), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_file_size CHECK (file_size_bytes >= 0)
);

CREATE TABLE clubs (
	id BIGSERIAL NOT NULL, 
	club_name VARCHAR(255) NOT NULL, 
	region_id BIGINT NOT NULL, 
	club_type VARCHAR(50), 
	competitiveness_level VARCHAR(50), 
	member_capacity INTEGER, 
	founding_date DATE, 
	indoor_court_count INTEGER, 
	outdoor_court_count INTEGER, 
	generation_run_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_club_region_name UNIQUE (region_id, club_name), 
	CONSTRAINT chk_club_type CHECK (club_type IN ('public_park', 'private_club', 'community_center', 'resort', 'university', 'municipal_recreation', 'dedicated_facility')), 
	CONSTRAINT chk_court_counts CHECK (indoor_court_count >= 0 AND outdoor_court_count >= 0), 
	FOREIGN KEY(region_id) REFERENCES regions (id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE configuration_profile_versions (
	id BIGSERIAL NOT NULL, 
	profile_id BIGINT NOT NULL, 
	version_number INTEGER NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	notes TEXT, 
	config_schema_version VARCHAR(50) NOT NULL, 
	config_hash VARCHAR(128), 
	config_payload JSONB NOT NULL, 
	created_by VARCHAR(255), 
	lifecycle_status VARCHAR(30) DEFAULT 'valid' NOT NULL, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	deprecated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_configuration_profile_version UNIQUE (profile_id, version_number), 
	CONSTRAINT chk_configuration_version_number CHECK (version_number > 0), 
	CONSTRAINT chk_configuration_lifecycle_status CHECK (lifecycle_status IN ('valid', 'deprecated')), 
	FOREIGN KEY(profile_id) REFERENCES configuration_profiles (id)
);

CREATE TABLE monthly_batches (
	id BIGSERIAL NOT NULL, 
	generation_run_id BIGINT NOT NULL, 
	batch_month DATE NOT NULL, 
	batch_sequence INTEGER NOT NULL, 
	batch_type VARCHAR(30) DEFAULT 'future_increment' NOT NULL, 
	active_player_count_start INTEGER, 
	new_player_count INTEGER, 
	active_player_count_end INTEGER, 
	match_count_generated INTEGER, 
	rating_update_count INTEGER, 
	assessment_update_count INTEGER, 
	processing_status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_batch_generation_month UNIQUE (generation_run_id, batch_month), 
	CONSTRAINT chk_batch_type CHECK (batch_type IN ('historical_initial', 'future_increment')), 
	CONSTRAINT chk_processing_status CHECK (processing_status IN ('pending', 'running', 'succeeded', 'failed')), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE ops.background_job_events (
	id BIGSERIAL NOT NULL, 
	job_status_id BIGINT NOT NULL, 
	worker_id VARCHAR(64), 
	event_type VARCHAR(50) NOT NULL, 
	event_message TEXT, 
	event_metadata_json JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id) ON DELETE CASCADE
);

CREATE TABLE ops.background_job_leases (
	job_status_id BIGINT NOT NULL, 
	worker_id VARCHAR(64) NOT NULL, 
	lease_token VARCHAR(64) NOT NULL, 
	claimed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	lease_expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_heartbeat_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	attempt_count INTEGER DEFAULT 1 NOT NULL, 
	metadata_json JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (job_status_id), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id) ON DELETE CASCADE, 
	FOREIGN KEY(worker_id) REFERENCES ops.background_workers (worker_id)
);

CREATE TABLE players (
	id BIGSERIAL NOT NULL, 
	external_player_key UUID DEFAULT gen_random_uuid() NOT NULL, 
	first_name VARCHAR(100) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	gender VARCHAR(20), 
	birth_date DATE NOT NULL, 
	dominant_hand VARCHAR(10), 
	home_region_id BIGINT, 
	registration_date DATE NOT NULL, 
	initial_skill_seed NUMERIC(8, 4), 
	player_status VARCHAR(30) DEFAULT 'ACTIVE' NOT NULL, 
	generation_run_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_player_birth_date CHECK (birth_date < CURRENT_DATE), 
	CONSTRAINT chk_player_status CHECK (player_status IN ('ACTIVE', 'INJURED', 'INACTIVE', 'RETIRED')), 
	UNIQUE (external_player_key), 
	FOREIGN KEY(home_region_id) REFERENCES regions (id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE raw_seed_load_runs (
	id BIGSERIAL NOT NULL, 
	job_status_id BIGINT,
	dataset_type VARCHAR(80) NOT NULL, 
	source_path VARCHAR(1000) NOT NULL, 
	source_file_count INTEGER NOT NULL, 
	source_checksum VARCHAR(128), 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	rows_read INTEGER NOT NULL, 
	rows_loaded INTEGER NOT NULL, 
	rows_rejected INTEGER NOT NULL, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_raw_seed_load_status CHECK (status IN ('pending', 'running', 'completed', 'failed')), 
	CONSTRAINT chk_raw_seed_load_counts CHECK (source_file_count >= 0 AND rows_read >= 0 AND rows_loaded >= 0 AND rows_rejected >= 0), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id)
);

CREATE TABLE student_dataset_comparisons (
	id BIGSERIAL NOT NULL, 
	clean_export_path TEXT NOT NULL, 
	tainted_export_path TEXT NOT NULL, 
	clean_generation_run_id BIGINT, 
	tainted_generation_run_id BIGINT, 
	compared_release_count BIGINT DEFAULT 0 NOT NULL, 
	total_issue_count BIGINT DEFAULT 0 NOT NULL, 
	missing_clean_release_count BIGINT DEFAULT 0 NOT NULL, 
	missing_tainted_release_count BIGINT DEFAULT 0 NOT NULL, 
	status VARCHAR(30) DEFAULT 'succeeded' NOT NULL, 
	summary_payload TEXT NOT NULL, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_student_dataset_comparison_counts CHECK (compared_release_count >= 0 AND total_issue_count >= 0 AND missing_clean_release_count >= 0 AND missing_tainted_release_count >= 0), 
	CONSTRAINT chk_student_dataset_comparison_status CHECK (status IN ('succeeded', 'failed')), 
	FOREIGN KEY(clean_generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(tainted_generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE student_dataset_releases (
	id BIGSERIAL NOT NULL, 
	release_name VARCHAR(255) NOT NULL, 
	release_type VARCHAR(50) NOT NULL, 
	release_month DATE, 
	generation_run_id BIGINT NOT NULL, 
	data_quality_level VARCHAR(50), 
	output_path TEXT NOT NULL, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_student_release_type CHECK (release_type IN ('initial_snapshot', 'monthly_incremental')), 
	CONSTRAINT chk_student_release_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed')), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE teams (
	id BIGSERIAL NOT NULL, 
	team_type VARCHAR(50) NOT NULL, 
	team_identity_type VARCHAR(30) DEFAULT 'competitive' NOT NULL, 
	team_status VARCHAR(30), 
	country_code VARCHAR(2), 
	formation_date DATE NOT NULL, 
	dissolution_date DATE, 
	chemistry_score NUMERIC(8, 4), 
	persistence_probability NUMERIC(5, 4), 
	generation_run_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_team_country CHECK (country_code IS NULL OR country_code IN ('US', 'CA')), 
	CONSTRAINT chk_team_type CHECK (team_type IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles')), 
	CONSTRAINT chk_team_identity_type CHECK (team_identity_type IN ('competitive', 'ad_hoc')), 
	CONSTRAINT chk_team_status CHECK (team_status IN ('active', 'dormant', 'retired')), 
	CONSTRAINT chk_team_dates CHECK (dissolution_date IS NULL OR dissolution_date >= formation_date), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE tournaments (
	id BIGSERIAL NOT NULL, 
	tournament_name VARCHAR(255) NOT NULL, 
	region_id BIGINT, 
	tournament_start_date DATE NOT NULL, 
	tournament_end_date DATE NOT NULL, 
	tournament_type VARCHAR(50), 
	skill_division VARCHAR(50), 
	participant_count INTEGER, 
	generation_run_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_tournament_dates CHECK (tournament_end_date >= tournament_start_date), 
	FOREIGN KEY(region_id) REFERENCES regions (id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE audit_batch_team_rosters (
	generation_run_id BIGINT NOT NULL, 
	batch_id BIGINT NOT NULL, 
	batch_month DATE NOT NULL, 
	team_id BIGINT NOT NULL, 
	player_one_id BIGINT NOT NULL, 
	player_two_id BIGINT NOT NULL, 
	roster_key VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (batch_id, team_id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id), 
	FOREIGN KEY(player_one_id) REFERENCES players (id), 
	FOREIGN KEY(player_two_id) REFERENCES players (id)
);

CREATE TABLE batch_runs (
	id BIGSERIAL NOT NULL, 
	batch_id BIGINT NOT NULL, 
	run_status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_run_status CHECK (run_status IN ('pending', 'running', 'succeeded', 'failed')), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE club_memberships (
	id BIGSERIAL NOT NULL, 
	player_id BIGINT NOT NULL, 
	club_id BIGINT NOT NULL, 
	membership_type VARCHAR(50), 
	start_date DATE NOT NULL, 
	end_date DATE, 
	is_primary BOOLEAN, 
	generation_run_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_membership_dates CHECK (end_date IS NULL OR end_date >= start_date), 
	FOREIGN KEY(player_id) REFERENCES players (id), 
	FOREIGN KEY(club_id) REFERENCES clubs (id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
);

CREATE TABLE export_runs (
	id BIGSERIAL NOT NULL, 
	batch_id BIGINT, 
	export_type VARCHAR(50) NOT NULL, 
	export_format VARCHAR(50) NOT NULL, 
	export_path TEXT NOT NULL, 
	partition_strategy VARCHAR(100), 
	row_count BIGINT, 
	schema_hash VARCHAR(64), 
	checksum VARCHAR(64), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_export_format CHECK (export_format IN ('parquet', 'csv', 'json', 'sql')), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE generation_runtime_metrics (
	id BIGSERIAL NOT NULL, 
	generation_run_id BIGINT NOT NULL, 
	job_status_id BIGINT,
	batch_id BIGINT, 
	stage_name VARCHAR(100) NOT NULL, 
	subphase_name VARCHAR(100) NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	elapsed_ms BIGINT NOT NULL, 
	input_count BIGINT, 
	output_count BIGINT, 
	attempt_count BIGINT, 
	metadata_json JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_generation_runtime_metric_event_type CHECK (event_type IN ('completed', 'failed')), 
	CONSTRAINT chk_generation_runtime_metric_elapsed CHECK (elapsed_ms >= 0), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id),
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE job_stage_progress (
	id BIGSERIAL NOT NULL, 
	job_status_id BIGINT NOT NULL, 
	generation_run_id BIGINT, 
	batch_id BIGINT, 
	stage_name VARCHAR(100) NOT NULL, 
	stage_sequence BIGINT, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	progress_current BIGINT DEFAULT 0 NOT NULL, 
	progress_total BIGINT, 
	progress_unit VARCHAR(100), 
	progress_percent NUMERIC(5, 2), 
	last_heartbeat_at TIMESTAMP WITHOUT TIME ZONE, 
	progress_message TEXT, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	metadata_json JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_job_stage_progress_stage UNIQUE (job_status_id, batch_id, stage_name), 
	CONSTRAINT chk_job_stage_progress_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed')), 
	CONSTRAINT chk_job_stage_progress_percent CHECK (progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE matches (
	id BIGSERIAL NOT NULL, 
	tournament_id BIGINT, 
	match_date DATE NOT NULL, 
	region_id BIGINT, 
	match_type VARCHAR(50) NOT NULL, 
	court_type VARCHAR(50), 
	match_format VARCHAR(50), 
	winning_team_id BIGINT, 
	predicted_winning_team_number INTEGER, 
	predicted_win_probability NUMERIC(8, 4), 
	total_points_played INTEGER, 
	expected_competitiveness NUMERIC(8, 3), 
	simulation_noise_factor NUMERIC(8, 3), 
	batch_id BIGINT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_match_type CHECK (match_type IN ('recreational', 'league', 'ladder', 'tournament', 'challenge', 'clinic', 'open_play')), 
	CONSTRAINT chk_match_predicted_winning_team CHECK (predicted_winning_team_number IS NULL OR predicted_winning_team_number IN (1, 2)), 
	FOREIGN KEY(tournament_id) REFERENCES tournaments (id), 
	FOREIGN KEY(region_id) REFERENCES regions (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE ops.realism_audit_query_runs (
	id BIGSERIAL NOT NULL, 
	job_status_id BIGINT NOT NULL, 
	generation_run_id BIGINT, 
	batch_id BIGINT, 
	query_index INTEGER NOT NULL, 
	query_name VARCHAR(255) NOT NULL, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	elapsed_ms BIGINT, 
	row_count BIGINT, 
	result_json JSONB, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_realism_audit_query_runs_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id) ON DELETE CASCADE, 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE player_assessment_history (
	id BIGSERIAL NOT NULL, 
	player_id BIGINT NOT NULL, 
	assessment_date DATE NOT NULL, 
	assessment_type VARCHAR(100) NOT NULL, 
	assessment_value NUMERIC(8, 3), 
	confidence_score NUMERIC(8, 3), 
	derived_from_matches INTEGER, 
	batch_id BIGINT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_assessment_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1), 
	FOREIGN KEY(player_id) REFERENCES players (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE player_rating_history (
	id BIGSERIAL NOT NULL, 
	player_id BIGINT NOT NULL, 
	rating_date DATE NOT NULL, 
	rating_type VARCHAR(50) NOT NULL, 
	rating_value NUMERIC(8, 3) NOT NULL, 
	confidence_score NUMERIC(8, 3), 
	volatility_score NUMERIC(8, 3), 
	expected_performance NUMERIC(8, 3), 
	regional_adjustment_factor NUMERIC(8, 4), 
	global_percentile NUMERIC(5, 2), 
	match_count_used INTEGER, 
	calculation_version VARCHAR(50), 
	batch_id BIGINT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_rating_value CHECK (rating_value >= 0 AND rating_value <= 5000), 
	CONSTRAINT chk_confidence_score CHECK (confidence_score >= 0 AND confidence_score <= 1), 
	FOREIGN KEY(player_id) REFERENCES players (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE player_registrations (
	id BIGSERIAL NOT NULL, 
	player_id BIGINT NOT NULL, 
	batch_id BIGINT NOT NULL, 
	registration_month DATE NOT NULL, 
	registration_source VARCHAR(50) DEFAULT 'synthetic' NOT NULL, 
	assigned_region_id BIGINT, 
	initial_rating_value NUMERIC(8, 3), 
	initial_confidence_score NUMERIC(8, 3), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_player_batch UNIQUE (player_id, batch_id), 
	FOREIGN KEY(player_id) REFERENCES players (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id), 
	FOREIGN KEY(assigned_region_id) REFERENCES regions (id)
);

CREATE TABLE raw_first_names (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(10) NOT NULL, 
	gender VARCHAR(1) NOT NULL, 
	birth_year INTEGER NOT NULL, 
	first_name VARCHAR(100) NOT NULL, 
	frequency_count INTEGER NOT NULL, 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_raw_first_names_country CHECK (country_code IN ('US', 'CA')), 
	CONSTRAINT chk_raw_first_names_gender CHECK (gender IN ('M', 'F')), 
	CONSTRAINT chk_raw_first_names_freq CHECK (frequency_count > 0), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_last_names (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	frequency_count INTEGER NOT NULL, 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_raw_last_names_country CHECK (country_code IN ('US', 'CA')), 
	CONSTRAINT chk_raw_last_names_freq CHECK (frequency_count > 0), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_metro_areas (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(10) NOT NULL, 
	metro_area_name VARCHAR(255) NOT NULL, 
	population BIGINT NOT NULL, 
	selection_probability NUMERIC(12, 8) NOT NULL, 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_raw_metro_country CHECK (country_code IN ('US', 'CA')), 
	CONSTRAINT chk_raw_metro_population CHECK (population > 0), 
	CONSTRAINT chk_raw_metro_probability CHECK (selection_probability >= 0), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_pickleball_club_distributions (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(10) NOT NULL, 
	state_province_name VARCHAR(255) NOT NULL, 
	target_club_count INTEGER NOT NULL, 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_raw_club_distribution_state UNIQUE (load_run_id, country_code, state_province_code), 
	CONSTRAINT chk_raw_club_dist_country CHECK (country_code IN ('US', 'CA')), 
	CONSTRAINT chk_raw_club_dist_count CHECK (target_club_count >= 0), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_pickleball_club_names (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	club_seed BIGINT NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(10) NOT NULL, 
	club_name VARCHAR(255) NOT NULL, 
	club_type VARCHAR(80), 
	size_tier VARCHAR(30), 
	generation_method VARCHAR(100), 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_raw_club_name_seed UNIQUE (load_run_id, club_seed), 
	CONSTRAINT chk_raw_club_names_country CHECK (country_code IN ('US', 'CA')), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_seed_load_errors (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER, 
	error_code VARCHAR(80) NOT NULL, 
	error_message TEXT NOT NULL, 
	raw_payload JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE raw_state_prov_biases (
	id BIGSERIAL NOT NULL, 
	load_run_id BIGINT NOT NULL, 
	source_file VARCHAR(500) NOT NULL, 
	source_row_number INTEGER NOT NULL, 
	raw_payload JSONB NOT NULL, 
	country_code VARCHAR(2) NOT NULL, 
	state_province_code VARCHAR(10) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	bias_multiplier NUMERIC(10, 4) NOT NULL, 
	bias_reason TEXT, 
	source_dataset VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_raw_state_bias_country CHECK (country_code IN ('US', 'CA')), 
	CONSTRAINT chk_raw_state_bias_multiplier CHECK (bias_multiplier > 0), 
	FOREIGN KEY(load_run_id) REFERENCES raw_seed_load_runs (id)
);

CREATE TABLE student_dataset_release_files (
	id BIGSERIAL NOT NULL, 
	release_id BIGINT NOT NULL, 
	table_name VARCHAR(255) NOT NULL, 
	file_path TEXT NOT NULL, 
	row_count BIGINT, 
	schema_hash VARCHAR(128), 
	checksum VARCHAR(128), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(release_id) REFERENCES student_dataset_releases (id)
);

CREATE TABLE team_lifecycle_events (
	id BIGSERIAL NOT NULL, 
	generation_run_id BIGINT NOT NULL, 
	batch_id BIGINT NOT NULL, 
	team_id BIGINT NOT NULL, 
	event_date DATE NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_team_lifecycle_event_type CHECK (event_type IN ('formed', 'dormant', 'retired', 'reactivated')), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id)
);

CREATE TABLE team_memberships (
	id BIGSERIAL NOT NULL, 
	team_id BIGINT NOT NULL, 
	player_id BIGINT NOT NULL, 
	player_position INTEGER NOT NULL, 
	joined_date DATE NOT NULL, 
	left_date DATE, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_position CHECK (player_position IN (1, 2)), 
	CONSTRAINT chk_membership_dates CHECK (left_date IS NULL OR left_date >= joined_date), 
	CONSTRAINT uq_team_player_joined UNIQUE (team_id, player_id, joined_date), 
	FOREIGN KEY(team_id) REFERENCES teams (id), 
	FOREIGN KEY(player_id) REFERENCES players (id)
);

CREATE TABLE tournament_events (
	id BIGSERIAL NOT NULL, 
	event_name VARCHAR(255) NOT NULL, 
	generation_run_id BIGINT NOT NULL, 
	source_batch_id BIGINT NOT NULL, 
	tournament_date DATE NOT NULL, 
	config_snapshot JSONB NOT NULL, 
	status VARCHAR(30) DEFAULT 'draft' NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_tournament_event_status CHECK (status IN ('draft', 'ready', 'running', 'completed', 'cancelled')), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(source_batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE validation_results (
	id BIGSERIAL NOT NULL, 
	batch_id BIGINT, 
	validation_rule_id VARCHAR(100) NOT NULL, 
	validation_rule_name VARCHAR(255) NOT NULL, 
	severity VARCHAR(30) NOT NULL, 
	entity_type VARCHAR(100), 
	entity_id BIGINT, 
	field_name VARCHAR(100), 
	observed_value TEXT, 
	expected_value TEXT, 
	validation_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_severity CHECK (severity IN ('info', 'warning', 'error', 'blocker')), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id)
);

CREATE TABLE match_games (
	id BIGSERIAL NOT NULL, 
	match_id BIGINT NOT NULL, 
	game_number INTEGER NOT NULL, 
	team_one_score INTEGER NOT NULL, 
	team_two_score INTEGER NOT NULL, 
	winning_team_number INTEGER NOT NULL, 
	target_score INTEGER DEFAULT 11 NOT NULL, 
	win_by INTEGER DEFAULT 2 NOT NULL, 
	expected_team_one_score_share NUMERIC(8, 4), 
	actual_team_one_score_share NUMERIC(8, 4), 
	expected_team_one_score NUMERIC(8, 3), 
	expected_team_two_score NUMERIC(8, 3), 
	score_noise_factor NUMERIC(8, 3), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_match_game_number UNIQUE (match_id, game_number), 
	CONSTRAINT chk_game_number CHECK (game_number >= 1), 
	CONSTRAINT chk_game_scores_nonnegative CHECK (team_one_score >= 0 AND team_two_score >= 0), 
	CONSTRAINT chk_game_winning_team CHECK (winning_team_number IN (1, 2)), 
	CONSTRAINT chk_game_target_score CHECK (target_score IN (11, 15, 21)), 
	CONSTRAINT chk_game_win_by CHECK (win_by >= 1), 
	FOREIGN KEY(match_id) REFERENCES matches (id)
);

CREATE TABLE match_teams (
	id BIGSERIAL NOT NULL, 
	match_id BIGINT NOT NULL, 
	team_number INTEGER NOT NULL, 
	team_score INTEGER NOT NULL, 
	expected_win_probability NUMERIC(8, 4), 
	average_team_rating NUMERIC(8, 3), 
	pairing_source VARCHAR(30), 
	source_team_id BIGINT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_team_number CHECK (team_number IN (1, 2)), 
	CONSTRAINT chk_match_team_pairing_source CHECK (pairing_source IS NULL OR pairing_source IN ('competitive_team', 'ad_hoc')), 
	CONSTRAINT uq_match_team_number UNIQUE (match_id, team_number), 
	FOREIGN KEY(match_id) REFERENCES matches (id), 
	FOREIGN KEY(source_team_id) REFERENCES teams (id)
);

CREATE TABLE tournament_simulation_runs (
	id BIGSERIAL NOT NULL, 
	event_id BIGINT NOT NULL, 
	run_type VARCHAR(30) NOT NULL, 
	status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	seed BIGINT, 
	iteration_count INTEGER, 
	config_snapshot JSONB NOT NULL, 
	job_status_id BIGINT, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_tournament_simulation_run_type CHECK (run_type IN ('monte_carlo', 'official')), 
	CONSTRAINT chk_tournament_simulation_run_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed')), 
	CONSTRAINT chk_tournament_simulation_iterations CHECK (iteration_count IS NULL OR iteration_count >= 1), 
	FOREIGN KEY(event_id) REFERENCES tournament_events (id), 
	FOREIGN KEY(job_status_id) REFERENCES job_status (id)
);

CREATE TABLE tournament_student_groups (
	id BIGSERIAL NOT NULL, 
	event_id BIGINT NOT NULL, 
	group_name VARCHAR(255) NOT NULL, 
	external_group_key VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_group_name UNIQUE (event_id, group_name), 
	CONSTRAINT uq_tournament_group_external_key UNIQUE (event_id, external_group_key), 
	FOREIGN KEY(event_id) REFERENCES tournament_events (id)
);

CREATE TABLE match_team_players (
	id BIGSERIAL NOT NULL, 
	match_team_id BIGINT NOT NULL, 
	player_id BIGINT NOT NULL, 
	player_position INTEGER, 
	player_rating_at_match NUMERIC(8, 3), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_player_position CHECK (player_position IN (1, 2)), 
	CONSTRAINT uq_match_team_player UNIQUE (match_team_id, player_id), 
	FOREIGN KEY(match_team_id) REFERENCES match_teams (id), 
	FOREIGN KEY(player_id) REFERENCES players (id)
);

CREATE TABLE ratings_update_log (
	id BIGSERIAL NOT NULL, 
	generation_run_id BIGINT NOT NULL, 
	batch_id BIGINT NOT NULL, 
	match_id BIGINT NOT NULL, 
	match_number INTEGER NOT NULL, 
	match_date DATE NOT NULL, 
	player_id BIGINT NOT NULL, 
	match_team_id BIGINT NOT NULL, 
	team_number INTEGER NOT NULL, 
	rating_type VARCHAR(50) NOT NULL, 
	rating_before NUMERIC(8, 3) NOT NULL, 
	rating_after NUMERIC(8, 3) NOT NULL, 
	rating_delta NUMERIC(8, 3) NOT NULL, 
	expected_score_share NUMERIC(8, 4) NOT NULL, 
	actual_score_share NUMERIC(8, 4) NOT NULL, 
	expected_raw_points NUMERIC(8, 3) NOT NULL, 
	actual_raw_points NUMERIC(8, 3) NOT NULL, 
	games_played INTEGER NOT NULL, 
	games_won INTEGER NOT NULL, 
	match_won INTEGER NOT NULL, 
	k_factor NUMERIC(8, 3) NOT NULL, 
	confidence_before NUMERIC(8, 3), 
	confidence_after NUMERIC(8, 3), 
	calculation_version VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT chk_rating_log_match_number CHECK (match_number >= 1), 
	CONSTRAINT chk_rating_log_team_number CHECK (team_number IN (1, 2)), 
	CONSTRAINT chk_rating_log_games_played CHECK (games_played >= 1), 
	CONSTRAINT chk_rating_log_games_won CHECK (games_won >= 0), 
	CONSTRAINT chk_rating_log_match_won CHECK (match_won IN (0, 1)), 
	CONSTRAINT chk_rating_log_before CHECK (rating_before >= 0 AND rating_before <= 5000), 
	CONSTRAINT chk_rating_log_after CHECK (rating_after >= 0 AND rating_after <= 5000), 
	CONSTRAINT chk_rating_log_expected_share CHECK (expected_score_share >= 0 AND expected_score_share <= 1), 
	CONSTRAINT chk_rating_log_actual_share CHECK (actual_score_share >= 0 AND actual_score_share <= 1), 
	FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id), 
	FOREIGN KEY(batch_id) REFERENCES monthly_batches (id), 
	FOREIGN KEY(match_id) REFERENCES matches (id), 
	FOREIGN KEY(player_id) REFERENCES players (id), 
	FOREIGN KEY(match_team_id) REFERENCES match_teams (id)
);

CREATE TABLE tournament_division_results (
	id BIGSERIAL NOT NULL, 
	simulation_run_id BIGINT NOT NULL, 
	slot_country_code VARCHAR(2) NOT NULL, 
	slot_division VARCHAR(50) NOT NULL, 
	iteration_count INTEGER, 
	unique_team_count INTEGER NOT NULL, 
	match_count INTEGER NOT NULL, 
	champion_team_id BIGINT, 
	summary_payload JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_division_result UNIQUE (simulation_run_id, slot_country_code, slot_division), 
	CONSTRAINT chk_tournament_division_result_country CHECK (slot_country_code IN ('US', 'CA', 'ALL')), 
	CONSTRAINT chk_tournament_division_result_division CHECK (slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')), 
	CONSTRAINT chk_tournament_division_team_count CHECK (unique_team_count >= 0), 
	CONSTRAINT chk_tournament_division_match_count CHECK (match_count >= 0), 
	FOREIGN KEY(simulation_run_id) REFERENCES tournament_simulation_runs (id), 
	FOREIGN KEY(champion_team_id) REFERENCES teams (id)
);

CREATE TABLE tournament_group_results (
	id BIGSERIAL NOT NULL, 
	simulation_run_id BIGINT NOT NULL, 
	student_group_id BIGINT NOT NULL, 
	expected_score NUMERIC(10, 3), 
	official_score NUMERIC(10, 3), 
	average_rank NUMERIC(8, 3), 
	final_rank INTEGER, 
	champion_count INTEGER, 
	runner_up_count INTEGER, 
	top_four_count INTEGER, 
	match_wins INTEGER, 
	rank_distribution JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_group_result UNIQUE (simulation_run_id, student_group_id), 
	CONSTRAINT chk_tournament_group_result_rank CHECK (final_rank IS NULL OR final_rank >= 1), 
	FOREIGN KEY(simulation_run_id) REFERENCES tournament_simulation_runs (id), 
	FOREIGN KEY(student_group_id) REFERENCES tournament_student_groups (id)
);

CREATE TABLE tournament_official_matches (
	id BIGSERIAL NOT NULL, 
	simulation_run_id BIGINT NOT NULL, 
	slot_country_code VARCHAR(2) NOT NULL, 
	slot_division VARCHAR(50) NOT NULL, 
	match_number INTEGER NOT NULL, 
	team_one_id BIGINT NOT NULL, 
	team_two_id BIGINT NOT NULL, 
	winning_team_id BIGINT NOT NULL, 
	team_one_games_won INTEGER NOT NULL, 
	team_two_games_won INTEGER NOT NULL, 
	team_one_points INTEGER NOT NULL, 
	team_two_points INTEGER NOT NULL, 
	visible_team_one_win_probability NUMERIC(8, 4), 
	final_team_one_win_probability NUMERIC(8, 4), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_official_match_number UNIQUE (simulation_run_id, match_number), 
	CONSTRAINT chk_tournament_official_match_country CHECK (slot_country_code IN ('US', 'CA', 'ALL')), 
	CONSTRAINT chk_tournament_official_match_division CHECK (slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')), 
	CONSTRAINT chk_tournament_official_match_number CHECK (match_number >= 1), 
	CONSTRAINT chk_tournament_official_match_distinct_teams CHECK (team_one_id <> team_two_id), 
	FOREIGN KEY(simulation_run_id) REFERENCES tournament_simulation_runs (id), 
	FOREIGN KEY(team_one_id) REFERENCES teams (id), 
	FOREIGN KEY(team_two_id) REFERENCES teams (id), 
	FOREIGN KEY(winning_team_id) REFERENCES teams (id)
);

CREATE TABLE tournament_submissions (
	id BIGSERIAL NOT NULL, 
	event_id BIGINT NOT NULL, 
	student_group_id BIGINT NOT NULL, 
	slot_country_code VARCHAR(3) NOT NULL, 
	slot_division VARCHAR(50) NOT NULL, 
	team_id BIGINT NOT NULL, 
	validation_status VARCHAR(30) DEFAULT 'pending' NOT NULL, 
	validation_message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_submission_slot UNIQUE (event_id, student_group_id, slot_country_code, slot_division), 
	CONSTRAINT chk_tournament_submission_country CHECK (slot_country_code IN ('US', 'CA')), 
	CONSTRAINT chk_tournament_submission_division CHECK (slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')), 
	CONSTRAINT chk_tournament_submission_validation_status CHECK (validation_status IN ('pending', 'valid', 'invalid')), 
	FOREIGN KEY(event_id) REFERENCES tournament_events (id), 
	FOREIGN KEY(student_group_id) REFERENCES tournament_student_groups (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id)
);

CREATE TABLE tournament_team_results (
	id BIGSERIAL NOT NULL, 
	simulation_run_id BIGINT NOT NULL, 
	slot_country_code VARCHAR(3) NOT NULL, 
	slot_division VARCHAR(50) NOT NULL, 
	team_id BIGINT NOT NULL, 
	championship_probability NUMERIC(8, 5), 
	top_three_probability NUMERIC(8, 5), 
	average_finish NUMERIC(8, 3), 
	win_percentage NUMERIC(8, 5), 
	upset_count INTEGER, 
	final_rank INTEGER, 
	match_wins INTEGER, 
	match_losses INTEGER, 
	games_won INTEGER, 
	games_lost INTEGER, 
	point_differential INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_team_result UNIQUE (simulation_run_id, slot_country_code, slot_division, team_id), 
	CONSTRAINT chk_tournament_team_result_country CHECK (slot_country_code IN ('US', 'CA')), 
	CONSTRAINT chk_tournament_team_result_division CHECK (slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')), 
	CONSTRAINT chk_tournament_team_result_rank CHECK (final_rank IS NULL OR final_rank >= 1), 
	FOREIGN KEY(simulation_run_id) REFERENCES tournament_simulation_runs (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id)
);

CREATE TABLE tournament_official_games (
	id BIGSERIAL NOT NULL, 
	official_match_id BIGINT NOT NULL, 
	game_number INTEGER NOT NULL, 
	team_one_score INTEGER NOT NULL, 
	team_two_score INTEGER NOT NULL, 
	winning_team_number INTEGER NOT NULL, 
	target_score INTEGER DEFAULT 11 NOT NULL, 
	win_by INTEGER DEFAULT 2 NOT NULL, 
	expected_team_one_score_share NUMERIC(8, 4), 
	actual_team_one_score_share NUMERIC(8, 4), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tournament_official_game_number UNIQUE (official_match_id, game_number), 
	CONSTRAINT chk_tournament_official_game_number CHECK (game_number >= 1), 
	CONSTRAINT chk_tournament_official_game_winner CHECK (winning_team_number IN (1, 2)), 
	CONSTRAINT chk_tournament_official_game_scores CHECK (team_one_score >= 0 AND team_two_score >= 0), 
	CONSTRAINT chk_tournament_official_game_target CHECK (target_score IN (11, 15, 21)), 
	CONSTRAINT chk_tournament_official_game_win_by CHECK (win_by >= 1), 
	FOREIGN KEY(official_match_id) REFERENCES tournament_official_matches (id)
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX idx_assessment_batch ON player_assessment_history (batch_id);
CREATE INDEX idx_assessment_player_date ON player_assessment_history (player_id, assessment_date DESC);
CREATE INDEX idx_audit_batch_team_rosters_run_batch ON audit_batch_team_rosters (generation_run_id, batch_id);
CREATE INDEX idx_audit_batch_team_rosters_run_batch_month ON audit_batch_team_rosters (generation_run_id, batch_month);
CREATE INDEX idx_audit_batch_team_rosters_run_roster_batch ON audit_batch_team_rosters (generation_run_id, roster_key, batch_id);
CREATE INDEX idx_background_job_events_job ON ops.background_job_events (job_status_id, id);
CREATE INDEX idx_background_job_events_type ON ops.background_job_events (event_type);
CREATE INDEX idx_background_job_leases_expiry ON ops.background_job_leases (lease_expires_at);
CREATE UNIQUE INDEX idx_background_job_leases_token ON ops.background_job_leases (lease_token);
CREATE INDEX idx_background_job_leases_worker ON ops.background_job_leases (worker_id);
CREATE INDEX idx_background_workers_heartbeat ON ops.background_workers (last_heartbeat_at);
CREATE INDEX idx_background_workers_status ON ops.background_workers (status);
CREATE INDEX idx_batch_runs_batch ON batch_runs (batch_id);
CREATE INDEX idx_batch_runs_status ON batch_runs (run_status);
CREATE INDEX idx_club_memberships_club ON club_memberships (club_id);
CREATE INDEX idx_club_memberships_dates ON club_memberships (start_date, end_date);
CREATE INDEX idx_club_memberships_player ON club_memberships (player_id);
CREATE INDEX idx_club_memberships_primary ON club_memberships (player_id, is_primary) WHERE is_primary = true;
CREATE INDEX idx_clubs_generation_run ON clubs (generation_run_id);
CREATE INDEX idx_clubs_region ON clubs (region_id);
CREATE INDEX idx_clubs_type ON clubs (club_type);
CREATE INDEX idx_configuration_profiles_active ON configuration_profiles (is_active);
CREATE INDEX idx_configuration_versions_lifecycle ON configuration_profile_versions (lifecycle_status);
CREATE INDEX idx_configuration_versions_profile ON configuration_profile_versions (profile_id);
CREATE INDEX idx_configuration_versions_schema ON configuration_profile_versions (config_schema_version);
CREATE INDEX idx_export_runs_batch ON export_runs (batch_id);
CREATE INDEX idx_export_runs_created ON export_runs (created_at);
CREATE INDEX idx_export_runs_type ON export_runs (export_type);
CREATE INDEX idx_first_names_country ON first_names (country_code);
CREATE INDEX idx_first_names_lookup ON first_names (country_code, state_province_code, birth_year, gender);
CREATE INDEX idx_first_names_probability ON first_names (normalized_probability);
CREATE INDEX idx_generation_runs_started ON generation_runs (started_at);
CREATE INDEX idx_generation_runs_status ON generation_runs (status);
CREATE INDEX idx_generation_runtime_metrics_batch ON generation_runtime_metrics (batch_id);
CREATE INDEX idx_generation_runtime_metrics_event ON generation_runtime_metrics (event_type);
CREATE INDEX idx_generation_runtime_metrics_job ON generation_runtime_metrics (job_status_id);
CREATE INDEX idx_generation_runtime_metrics_run ON generation_runtime_metrics (generation_run_id);
CREATE INDEX idx_generation_runtime_metrics_stage ON generation_runtime_metrics (stage_name);
CREATE INDEX idx_generation_runtime_metrics_subphase ON generation_runtime_metrics (subphase_name);
CREATE INDEX idx_job_stage_progress_batch ON job_stage_progress (batch_id);
CREATE INDEX idx_job_stage_progress_generation_run ON job_stage_progress (generation_run_id);
CREATE INDEX idx_job_stage_progress_heartbeat ON job_stage_progress (last_heartbeat_at);
CREATE INDEX idx_job_stage_progress_job ON job_stage_progress (job_status_id);
CREATE INDEX idx_job_stage_progress_status ON job_stage_progress (status);
CREATE INDEX idx_job_status_started ON job_status (started_at);
CREATE INDEX idx_job_status_status ON job_status (status);
CREATE INDEX idx_job_status_type ON job_status (job_type);
CREATE INDEX idx_last_names_country ON last_names (country_code);
CREATE INDEX idx_last_names_country_name_lookup ON last_names (country_code, last_name);
CREATE INDEX idx_last_names_lookup ON last_names (country_code, state_province_code);
CREATE INDEX idx_last_names_state_name_lookup ON last_names (country_code, state_province_code, last_name);
CREATE INDEX idx_match_games_match ON match_games (match_id);
CREATE INDEX idx_match_games_winner ON match_games (winning_team_number);
CREATE INDEX idx_match_team_players_player ON match_team_players (player_id);
CREATE INDEX idx_match_team_players_team ON match_team_players (match_team_id);
CREATE INDEX idx_match_teams_match ON match_teams (match_id);
CREATE INDEX idx_matches_batch ON matches (batch_id);
CREATE INDEX idx_matches_date ON matches (match_date);
CREATE INDEX idx_matches_region ON matches (region_id);
CREATE INDEX idx_matches_tournament ON matches (tournament_id);
CREATE INDEX idx_matches_type ON matches (match_type);
CREATE INDEX idx_monthly_batches_generation_run ON monthly_batches (generation_run_id);
CREATE INDEX idx_monthly_batches_month ON monthly_batches (batch_month);
CREATE INDEX idx_monthly_batches_status ON monthly_batches (processing_status);
CREATE INDEX idx_player_registrations_batch ON player_registrations (batch_id);
CREATE INDEX idx_player_registrations_month ON player_registrations (registration_month);
CREATE INDEX idx_player_registrations_player ON player_registrations (player_id);
CREATE INDEX idx_players_generation_run ON players (generation_run_id);
CREATE INDEX idx_players_region ON players (home_region_id);
CREATE INDEX idx_players_registration_date ON players (registration_date);
CREATE INDEX idx_players_status ON players (player_status);
CREATE INDEX idx_rating_batch ON player_rating_history (batch_id);
CREATE INDEX idx_rating_player_date ON player_rating_history (player_id, rating_date DESC);
CREATE INDEX idx_ratings_update_log_batch ON ratings_update_log (batch_id);
CREATE INDEX idx_raw_club_distributions_country_state ON raw_pickleball_club_distributions (country_code, state_province_code);
CREATE INDEX idx_raw_club_distributions_load_run ON raw_pickleball_club_distributions (load_run_id);
CREATE INDEX idx_raw_club_names_country_state ON raw_pickleball_club_names (country_code, state_province_code);
CREATE INDEX idx_raw_club_names_load_run ON raw_pickleball_club_names (load_run_id);
CREATE INDEX idx_raw_club_names_seed ON raw_pickleball_club_names (club_seed);
CREATE INDEX idx_raw_first_names_load_run ON raw_first_names (load_run_id);
CREATE INDEX idx_raw_first_names_lookup ON raw_first_names (country_code, state_province_code, birth_year, gender);
CREATE INDEX idx_raw_last_names_country ON raw_last_names (country_code);
CREATE INDEX idx_raw_last_names_load_run ON raw_last_names (load_run_id);
CREATE INDEX idx_raw_last_names_name ON raw_last_names (last_name);
CREATE INDEX idx_raw_metro_areas_country_state ON raw_metro_areas (country_code, state_province_code);
CREATE INDEX idx_raw_metro_areas_load_run ON raw_metro_areas (load_run_id);
CREATE INDEX idx_raw_metro_areas_probability ON raw_metro_areas (selection_probability);
CREATE INDEX idx_raw_seed_load_errors_code ON raw_seed_load_errors (error_code);
CREATE INDEX idx_raw_seed_load_errors_load_run ON raw_seed_load_errors (load_run_id);
CREATE INDEX idx_raw_seed_load_runs_dataset ON raw_seed_load_runs (dataset_type);
CREATE INDEX idx_raw_seed_load_runs_job ON raw_seed_load_runs (job_status_id);
CREATE INDEX idx_raw_seed_load_runs_started ON raw_seed_load_runs (started_at);
CREATE INDEX idx_raw_seed_load_runs_status ON raw_seed_load_runs (status);
CREATE INDEX idx_raw_state_prov_biases_country_state ON raw_state_prov_biases (country_code, state_province_code);
CREATE INDEX idx_raw_state_prov_biases_load_run ON raw_state_prov_biases (load_run_id);
CREATE INDEX idx_raw_state_prov_biases_lookup ON raw_state_prov_biases (country_code, state_province_code, last_name);
CREATE INDEX idx_realism_audit_query_runs_generation_run ON ops.realism_audit_query_runs (generation_run_id);
CREATE INDEX idx_realism_audit_query_runs_job_index ON ops.realism_audit_query_runs (job_status_id, query_index);
CREATE INDEX idx_realism_audit_query_runs_status ON ops.realism_audit_query_runs (status);
CREATE INDEX idx_student_dataset_comparisons_clean_run ON student_dataset_comparisons (clean_generation_run_id);
CREATE INDEX idx_student_dataset_comparisons_created ON student_dataset_comparisons (created_at);
CREATE INDEX idx_student_dataset_comparisons_status ON student_dataset_comparisons (status);
CREATE INDEX idx_student_dataset_comparisons_tainted_run ON student_dataset_comparisons (tainted_generation_run_id);
CREATE INDEX idx_student_dataset_release_files_release ON student_dataset_release_files (release_id);
CREATE INDEX idx_student_dataset_release_files_table ON student_dataset_release_files (table_name);
CREATE INDEX idx_student_dataset_releases_generation_run ON student_dataset_releases (generation_run_id);
CREATE INDEX idx_student_dataset_releases_status ON student_dataset_releases (status);
CREATE INDEX idx_team_lifecycle_events_batch ON team_lifecycle_events (batch_id);
CREATE INDEX idx_team_lifecycle_events_date ON team_lifecycle_events (event_date);
CREATE INDEX idx_team_lifecycle_events_run ON team_lifecycle_events (generation_run_id);
CREATE INDEX idx_team_lifecycle_events_team ON team_lifecycle_events (team_id);
CREATE INDEX idx_team_memberships_dates ON team_memberships (joined_date, left_date);
CREATE INDEX idx_team_memberships_player ON team_memberships (player_id);
CREATE INDEX idx_team_memberships_team ON team_memberships (team_id);
CREATE INDEX idx_teams_country ON teams (country_code);
CREATE INDEX idx_teams_formation_date ON teams (formation_date);
CREATE INDEX idx_teams_identity_type ON teams (team_identity_type);
CREATE INDEX idx_teams_status ON teams (team_status);
CREATE INDEX idx_teams_type ON teams (team_type);
CREATE INDEX idx_tournament_division_results_division ON tournament_division_results (slot_country_code, slot_division);
CREATE INDEX idx_tournament_division_results_run ON tournament_division_results (simulation_run_id);
CREATE INDEX idx_tournament_events_date ON tournament_events (tournament_date);
CREATE INDEX idx_tournament_events_generation_run ON tournament_events (generation_run_id);
CREATE INDEX idx_tournament_events_source_batch ON tournament_events (source_batch_id);
CREATE INDEX idx_tournament_events_status ON tournament_events (status);
CREATE INDEX idx_tournament_group_results_group ON tournament_group_results (student_group_id);
CREATE INDEX idx_tournament_group_results_run ON tournament_group_results (simulation_run_id);
CREATE INDEX idx_tournament_official_games_match ON tournament_official_games (official_match_id);
CREATE INDEX idx_tournament_official_matches_division ON tournament_official_matches (slot_country_code, slot_division);
CREATE INDEX idx_tournament_official_matches_run ON tournament_official_matches (simulation_run_id);
CREATE INDEX idx_tournament_simulation_runs_event ON tournament_simulation_runs (event_id);
CREATE INDEX idx_tournament_simulation_runs_job ON tournament_simulation_runs (job_status_id);
CREATE INDEX idx_tournament_simulation_runs_status ON tournament_simulation_runs (status);
CREATE INDEX idx_tournament_simulation_runs_type ON tournament_simulation_runs (run_type);
CREATE INDEX idx_tournament_student_groups_event ON tournament_student_groups (event_id);
CREATE INDEX idx_tournament_submissions_event ON tournament_submissions (event_id);
CREATE INDEX idx_tournament_submissions_group ON tournament_submissions (student_group_id);
CREATE INDEX idx_tournament_submissions_team ON tournament_submissions (team_id);
CREATE INDEX idx_tournament_team_results_division ON tournament_team_results (slot_country_code, slot_division);
CREATE INDEX idx_tournament_team_results_run ON tournament_team_results (simulation_run_id);
CREATE INDEX idx_tournament_team_results_team ON tournament_team_results (team_id);
CREATE INDEX idx_tournaments_region ON tournaments (region_id);
CREATE INDEX idx_tournaments_start_date ON tournaments (tournament_start_date);
CREATE INDEX idx_uploaded_files_status ON uploaded_files (validation_status);
CREATE INDEX idx_uploaded_files_timestamp ON uploaded_files (upload_timestamp);
CREATE INDEX idx_validation_results_batch ON validation_results (batch_id);
CREATE INDEX idx_validation_results_rule ON validation_results (validation_rule_id);
CREATE INDEX idx_validation_results_severity ON validation_results (severity);
CREATE UNIQUE INDEX uq_configuration_versions_single_valid ON configuration_profile_versions (lifecycle_status) WHERE lifecycle_status = 'valid';
CREATE UNIQUE INDEX uq_realism_audit_query_runs_job_query ON ops.realism_audit_query_runs (job_status_id, query_name);
