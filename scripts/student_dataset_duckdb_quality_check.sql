-- Student dataset release quality checks using DuckDB only.
--
-- Usage:
--   SET VARIABLE release_dir = '/abs/path/to/release_folder';
--   .read scripts/student_dataset_duckdb_quality_check.sql
--
-- Example:
--   duckdb
--   D SET VARIABLE release_dir = '/home/brett/projects/pickleball-sim/data/student_dataset_exports/run_32_student_dataset_publish_smoke/run_32_student_dataset_publish_smoke_initial_history';
--   D .read scripts/student_dataset_duckdb_quality_check.sql

SET VARIABLE manifest_path = getvariable('release_dir') || '/manifest.json';

CREATE OR REPLACE TEMP TABLE qc_results (
    category VARCHAR,
    check_name VARCHAR,
    status VARCHAR,
    failure_count BIGINT,
    details VARCHAR
);

CREATE OR REPLACE TEMP VIEW manifest AS
SELECT *
FROM read_json_auto(getvariable('manifest_path'));

CREATE OR REPLACE TEMP TABLE expected_tables (
    table_name VARCHAR,
    output_file VARCHAR,
    required_non_empty BOOLEAN
);

INSERT INTO expected_tables VALUES
    ('clubs', 'clubs.parquet', TRUE),
    ('club_memberships', 'club_memberships.parquet', TRUE),
    ('match_games', 'match_games.parquet', TRUE),
    ('match_team_players', 'match_team_players.parquet', TRUE),
    ('match_teams', 'match_teams.parquet', TRUE),
    ('matches', 'matches.parquet', TRUE),
    ('monthly_batches', 'monthly_batches.parquet', TRUE),
    ('player_assessment_history', 'player_assessment_history.parquet', FALSE),
    ('player_rating_history', 'player_rating_history.parquet', TRUE),
    ('player_registrations', 'player_registrations.parquet', TRUE),
    ('players', 'players.parquet', TRUE),
    ('regions', 'regions.parquet', TRUE),
    ('team_memberships', 'team_memberships.parquet', TRUE),
    ('teams', 'teams.parquet', TRUE);

CREATE OR REPLACE TEMP TABLE expected_columns (
    table_name VARCHAR,
    ordinal INTEGER,
    column_name VARCHAR
);

INSERT INTO expected_columns VALUES
    ('clubs', 1, 'id'),
    ('clubs', 2, 'club_name'),
    ('clubs', 3, 'region_id'),
    ('clubs', 4, 'club_type'),
    ('clubs', 5, 'competitiveness_level'),
    ('clubs', 6, 'member_capacity'),
    ('clubs', 7, 'founding_date'),
    ('clubs', 8, 'indoor_court_count'),
    ('clubs', 9, 'outdoor_court_count'),
    ('club_memberships', 1, 'id'),
    ('club_memberships', 2, 'player_id'),
    ('club_memberships', 3, 'club_id'),
    ('club_memberships', 4, 'membership_type'),
    ('club_memberships', 5, 'start_date'),
    ('club_memberships', 6, 'end_date'),
    ('club_memberships', 7, 'is_primary'),
    ('match_games', 1, 'id'),
    ('match_games', 2, 'match_id'),
    ('match_games', 3, 'game_number'),
    ('match_games', 4, 'team_one_score'),
    ('match_games', 5, 'team_two_score'),
    ('match_games', 6, 'winning_team_number'),
    ('match_games', 7, 'target_score'),
    ('match_games', 8, 'win_by'),
    ('match_games', 9, 'actual_team_one_score_share'),
    ('match_team_players', 1, 'id'),
    ('match_team_players', 2, 'match_team_id'),
    ('match_team_players', 3, 'player_id'),
    ('match_team_players', 4, 'player_position'),
    ('match_team_players', 5, 'player_rating_at_match'),
    ('match_teams', 1, 'id'),
    ('match_teams', 2, 'match_id'),
    ('match_teams', 3, 'team_number'),
    ('match_teams', 4, 'team_score'),
    ('match_teams', 5, 'average_team_rating'),
    ('matches', 1, 'id'),
    ('matches', 2, 'match_date'),
    ('matches', 3, 'region_id'),
    ('matches', 4, 'match_type'),
    ('matches', 5, 'court_type'),
    ('matches', 6, 'match_format'),
    ('matches', 7, 'winning_team_id'),
    ('matches', 8, 'total_points_played'),
    ('matches', 9, 'batch_id'),
    ('monthly_batches', 1, 'id'),
    ('monthly_batches', 2, 'batch_month'),
    ('monthly_batches', 3, 'batch_sequence'),
    ('monthly_batches', 4, 'batch_type'),
    ('monthly_batches', 5, 'active_player_count_start'),
    ('monthly_batches', 6, 'new_player_count'),
    ('monthly_batches', 7, 'active_player_count_end'),
    ('monthly_batches', 8, 'match_count_generated'),
    ('monthly_batches', 9, 'rating_update_count'),
    ('monthly_batches', 10, 'assessment_update_count'),
    ('player_assessment_history', 1, 'id'),
    ('player_assessment_history', 2, 'player_id'),
    ('player_assessment_history', 3, 'assessment_date'),
    ('player_assessment_history', 4, 'assessment_type'),
    ('player_assessment_history', 5, 'assessment_value'),
    ('player_assessment_history', 6, 'confidence_score'),
    ('player_assessment_history', 7, 'derived_from_matches'),
    ('player_assessment_history', 8, 'batch_id'),
    ('player_rating_history', 1, 'id'),
    ('player_rating_history', 2, 'player_id'),
    ('player_rating_history', 3, 'rating_date'),
    ('player_rating_history', 4, 'rating_type'),
    ('player_rating_history', 5, 'rating_value'),
    ('player_rating_history', 6, 'confidence_score'),
    ('player_rating_history', 7, 'volatility_score'),
    ('player_rating_history', 8, 'regional_adjustment_factor'),
    ('player_rating_history', 9, 'global_percentile'),
    ('player_rating_history', 10, 'match_count_used'),
    ('player_rating_history', 11, 'batch_id'),
    ('player_registrations', 1, 'id'),
    ('player_registrations', 2, 'player_id'),
    ('player_registrations', 3, 'batch_id'),
    ('player_registrations', 4, 'registration_month'),
    ('player_registrations', 5, 'registration_source'),
    ('player_registrations', 6, 'assigned_region_id'),
    ('player_registrations', 7, 'initial_rating_value'),
    ('player_registrations', 8, 'initial_confidence_score'),
    ('players', 1, 'id'),
    ('players', 2, 'external_player_key'),
    ('players', 3, 'first_name'),
    ('players', 4, 'last_name'),
    ('players', 5, 'gender'),
    ('players', 6, 'birth_date'),
    ('players', 7, 'dominant_hand'),
    ('players', 8, 'home_region_id'),
    ('players', 9, 'registration_date'),
    ('players', 10, 'player_status'),
    ('regions', 1, 'id'),
    ('regions', 2, 'country_code'),
    ('regions', 3, 'region_type'),
    ('regions', 4, 'region_name'),
    ('regions', 5, 'state_province_code'),
    ('regions', 6, 'population'),
    ('regions', 7, 'latitude'),
    ('regions', 8, 'longitude'),
    ('team_memberships', 1, 'id'),
    ('team_memberships', 2, 'team_id'),
    ('team_memberships', 3, 'player_id'),
    ('team_memberships', 4, 'player_position'),
    ('team_memberships', 5, 'joined_date'),
    ('team_memberships', 6, 'left_date'),
    ('teams', 1, 'id'),
    ('teams', 2, 'team_type'),
    ('teams', 3, 'team_status'),
    ('teams', 4, 'formation_date'),
    ('teams', 5, 'dissolution_date'),
    ('teams', 6, 'chemistry_score'),
    ('teams', 7, 'persistence_probability');

CREATE OR REPLACE TEMP TABLE excluded_parquet_files (file_name VARCHAR);

INSERT INTO excluded_parquet_files VALUES
    ('batch_runs.parquet'),
    ('configuration_profile_versions.parquet'),
    ('configuration_profiles.parquet'),
    ('export_runs.parquet'),
    ('first_names.parquet'),
    ('generation_runtime_metrics.parquet'),
    ('generation_runs.parquet'),
    ('job_stage_progress.parquet'),
    ('job_status.parquet'),
    ('last_names.parquet'),
    ('ratings_update_log.parquet'),
    ('raw_first_names.parquet'),
    ('raw_last_names.parquet'),
    ('raw_metro_areas.parquet'),
    ('raw_pickleball_club_distributions.parquet'),
    ('raw_pickleball_club_names.parquet'),
    ('raw_seed_load_errors.parquet'),
    ('raw_seed_load_runs.parquet'),
    ('raw_state_prov_biases.parquet'),
    ('student_dataset_release_files.parquet'),
    ('student_dataset_releases.parquet'),
    ('tournaments.parquet'),
    ('uploaded_files.parquet'),
    ('validation_results.parquet');

CREATE OR REPLACE TEMP VIEW actual_files AS
SELECT regexp_extract(file, '[^/]+$', 0) AS file_name
FROM glob(getvariable('release_dir') || '/*.parquet');

CREATE OR REPLACE TEMP VIEW manifest_row_counts AS
SELECT * FROM (
    SELECT 'clubs' AS table_name, manifest.row_counts.clubs AS row_count FROM manifest
    UNION ALL SELECT 'club_memberships', manifest.row_counts.club_memberships FROM manifest
    UNION ALL SELECT 'match_games', manifest.row_counts.match_games FROM manifest
    UNION ALL SELECT 'match_team_players', manifest.row_counts.match_team_players FROM manifest
    UNION ALL SELECT 'match_teams', manifest.row_counts.match_teams FROM manifest
    UNION ALL SELECT 'matches', manifest.row_counts.matches FROM manifest
    UNION ALL SELECT 'monthly_batches', manifest.row_counts.monthly_batches FROM manifest
    UNION ALL SELECT 'player_assessment_history', manifest.row_counts.player_assessment_history FROM manifest
    UNION ALL SELECT 'player_rating_history', manifest.row_counts.player_rating_history FROM manifest
    UNION ALL SELECT 'player_registrations', manifest.row_counts.player_registrations FROM manifest
    UNION ALL SELECT 'players', manifest.row_counts.players FROM manifest
    UNION ALL SELECT 'regions', manifest.row_counts.regions FROM manifest
    UNION ALL SELECT 'team_memberships', manifest.row_counts.team_memberships FROM manifest
    UNION ALL SELECT 'teams', manifest.row_counts.teams FROM manifest
);

CREATE OR REPLACE TEMP VIEW manifest_ordered_columns AS
SELECT * FROM (
    SELECT 'clubs' AS table_name, c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.clubs) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'club_memberships', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.club_memberships) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'match_games', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.match_games) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'match_team_players', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.match_team_players) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'match_teams', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.match_teams) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'matches', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.matches) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'monthly_batches', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.monthly_batches) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'player_assessment_history', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.player_assessment_history) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'player_rating_history', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.player_rating_history) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'player_registrations', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.player_registrations) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'players', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.players) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'regions', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.regions) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'team_memberships', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.team_memberships) WITH ORDINALITY AS c(column_name, ordinal)
    UNION ALL SELECT 'teams', c.column_name, c.ordinal FROM manifest, unnest(manifest.ordered_columns.teams) WITH ORDINALITY AS c(column_name, ordinal)
);

CREATE OR REPLACE VIEW clubs AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/clubs.parquet');

CREATE OR REPLACE VIEW club_memberships AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/club_memberships.parquet');

CREATE OR REPLACE VIEW match_games AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/match_games.parquet');

CREATE OR REPLACE VIEW match_team_players AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/match_team_players.parquet');

CREATE OR REPLACE VIEW match_teams AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/match_teams.parquet');

CREATE OR REPLACE VIEW matches AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/matches.parquet');

CREATE OR REPLACE VIEW monthly_batches AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/monthly_batches.parquet');

CREATE OR REPLACE VIEW player_assessment_history AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/player_assessment_history.parquet');

CREATE OR REPLACE VIEW player_rating_history AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/player_rating_history.parquet');

CREATE OR REPLACE VIEW player_registrations AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/player_registrations.parquet');

CREATE OR REPLACE VIEW players AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/players.parquet');

CREATE OR REPLACE VIEW regions AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/regions.parquet');

CREATE OR REPLACE VIEW team_memberships AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/team_memberships.parquet');

CREATE OR REPLACE VIEW teams AS
SELECT *
FROM read_parquet(getvariable('release_dir') || '/teams.parquet');

CREATE OR REPLACE TEMP VIEW actual_table_columns AS
SELECT 'clubs' AS table_name, cid + 1 AS ordinal, name AS column_name FROM pragma_table_info('clubs')
UNION ALL SELECT 'club_memberships', cid + 1, name FROM pragma_table_info('club_memberships')
UNION ALL SELECT 'match_games', cid + 1, name FROM pragma_table_info('match_games')
UNION ALL SELECT 'match_team_players', cid + 1, name FROM pragma_table_info('match_team_players')
UNION ALL SELECT 'match_teams', cid + 1, name FROM pragma_table_info('match_teams')
UNION ALL SELECT 'matches', cid + 1, name FROM pragma_table_info('matches')
UNION ALL SELECT 'monthly_batches', cid + 1, name FROM pragma_table_info('monthly_batches')
UNION ALL SELECT 'player_assessment_history', cid + 1, name FROM pragma_table_info('player_assessment_history')
UNION ALL SELECT 'player_rating_history', cid + 1, name FROM pragma_table_info('player_rating_history')
UNION ALL SELECT 'player_registrations', cid + 1, name FROM pragma_table_info('player_registrations')
UNION ALL SELECT 'players', cid + 1, name FROM pragma_table_info('players')
UNION ALL SELECT 'regions', cid + 1, name FROM pragma_table_info('regions')
UNION ALL SELECT 'team_memberships', cid + 1, name FROM pragma_table_info('team_memberships')
UNION ALL SELECT 'teams', cid + 1, name FROM pragma_table_info('teams');

CREATE OR REPLACE TEMP VIEW actual_table_row_counts AS
SELECT 'clubs' AS table_name, COUNT(*) AS row_count FROM clubs
UNION ALL SELECT 'club_memberships', COUNT(*) FROM club_memberships
UNION ALL SELECT 'match_games', COUNT(*) FROM match_games
UNION ALL SELECT 'match_team_players', COUNT(*) FROM match_team_players
UNION ALL SELECT 'match_teams', COUNT(*) FROM match_teams
UNION ALL SELECT 'matches', COUNT(*) FROM matches
UNION ALL SELECT 'monthly_batches', COUNT(*) FROM monthly_batches
UNION ALL SELECT 'player_assessment_history', COUNT(*) FROM player_assessment_history
UNION ALL SELECT 'player_rating_history', COUNT(*) FROM player_rating_history
UNION ALL SELECT 'player_registrations', COUNT(*) FROM player_registrations
UNION ALL SELECT 'players', COUNT(*) FROM players
UNION ALL SELECT 'regions', COUNT(*) FROM regions
UNION ALL SELECT 'team_memberships', COUNT(*) FROM team_memberships
UNION ALL SELECT 'teams', COUNT(*) FROM teams;

INSERT INTO qc_results
SELECT
    'manifest' AS category,
    'manifest.validation_status' AS check_name,
    CASE WHEN validation_status = 'passed' THEN 'passed' ELSE 'failed' END AS status,
    CASE WHEN validation_status = 'passed' THEN 0 ELSE 1 END AS failure_count,
    'validation_status=' || validation_status AS details
FROM manifest;

INSERT INTO qc_results
SELECT
    'files',
    'expected_parquet_file_count',
    CASE WHEN COUNT(*) = 14 THEN 'passed' ELSE 'failed' END,
    ABS(COUNT(*) - 14),
    'actual_file_count=' || COUNT(*)::VARCHAR
FROM actual_files;

INSERT INTO qc_results
SELECT
    'files',
    'unexpected_parquet_files',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    COALESCE(string_agg(actual.file_name, ', ' ORDER BY actual.file_name), '')
FROM actual_files actual
LEFT JOIN expected_tables expected
  ON expected.output_file = actual.file_name
WHERE expected.output_file IS NULL;

INSERT INTO qc_results
SELECT
    'files',
    'excluded_source_parquet_files',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    COALESCE(string_agg(actual.file_name, ', ' ORDER BY actual.file_name), '')
FROM actual_files actual
INNER JOIN excluded_parquet_files excluded
  ON excluded.file_name = actual.file_name;

INSERT INTO qc_results
SELECT
    'manifest',
    'manifest_row_counts_cover_expected_tables',
    CASE WHEN COUNT(*) = 14 THEN 'passed' ELSE 'failed' END,
    ABS(COUNT(*) - 14),
    'manifest_row_count_entries=' || COUNT(*)::VARCHAR
FROM manifest_row_counts;

INSERT INTO qc_results
SELECT
    'manifest',
    'manifest_ordered_columns_cover_expected_tables',
    CASE WHEN COUNT(DISTINCT table_name) = 14 THEN 'passed' ELSE 'failed' END,
    ABS(COUNT(DISTINCT table_name) - 14),
    'manifest_tables=' || COUNT(DISTINCT table_name)::VARCHAR
FROM manifest_ordered_columns;

INSERT INTO qc_results
SELECT
    'schema',
    'column_order:' || table_name,
    CASE WHEN actual_columns = expected_columns THEN 'passed' ELSE 'failed' END,
    CASE WHEN actual_columns = expected_columns THEN 0 ELSE 1 END,
    'expected=' || to_json(expected_columns) || ' actual=' || to_json(actual_columns)
FROM (
    SELECT
        expected.table_name,
        list(expected.column_name ORDER BY expected.ordinal) AS expected_columns,
        list(actual.column_name ORDER BY actual.ordinal) AS actual_columns
    FROM expected_columns expected
    LEFT JOIN actual_table_columns actual
      ON actual.table_name = expected.table_name
     AND actual.ordinal = expected.ordinal
    GROUP BY expected.table_name
) comparison;

INSERT INTO qc_results
SELECT
    'schema',
    'manifest_column_order:' || expected.table_name,
    CASE WHEN actual.actual_columns = manifest_columns.manifest_columns THEN 'passed' ELSE 'failed' END,
    CASE WHEN actual.actual_columns = manifest_columns.manifest_columns THEN 0 ELSE 1 END,
    'manifest=' || to_json(manifest_columns.manifest_columns) || ' actual=' || to_json(actual.actual_columns)
FROM (
    SELECT table_name, list(column_name ORDER BY ordinal) AS actual_columns
    FROM actual_table_columns
    GROUP BY table_name
) actual
JOIN (
    SELECT table_name, list(column_name ORDER BY ordinal) AS manifest_columns
    FROM manifest_ordered_columns
    GROUP BY table_name
) manifest_columns
  ON manifest_columns.table_name = actual.table_name
JOIN expected_tables expected
  ON expected.table_name = actual.table_name;

INSERT INTO qc_results
SELECT
    'counts',
    'row_count:' || actual.table_name,
    CASE WHEN actual.row_count = manifest_rows.row_count THEN 'passed' ELSE 'failed' END,
    ABS(actual.row_count - manifest_rows.row_count),
    'manifest=' || manifest_rows.row_count::VARCHAR || ' actual=' || actual.row_count::VARCHAR
FROM actual_table_row_counts actual
JOIN manifest_row_counts manifest_rows
  ON manifest_rows.table_name = actual.table_name;

INSERT INTO qc_results
SELECT
    'counts',
    'required_non_empty:' || actual.table_name,
    CASE WHEN actual.row_count > 0 THEN 'passed' ELSE 'failed' END,
    CASE WHEN actual.row_count > 0 THEN 0 ELSE 1 END,
    'row_count=' || actual.row_count::VARCHAR
FROM actual_table_row_counts actual
JOIN expected_tables expected
  ON expected.table_name = actual.table_name
WHERE expected.required_non_empty;

INSERT INTO qc_results
SELECT
    'relationships',
    'clubs.region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM clubs child
LEFT JOIN regions parent
  ON parent.id = child.region_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'club_memberships.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM club_memberships child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'club_memberships.club_id->clubs.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM club_memberships child
LEFT JOIN clubs parent
  ON parent.id = child.club_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_games.match_id->matches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM match_games child
LEFT JOIN matches parent
  ON parent.id = child.match_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_team_players.match_team_id->match_teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM match_team_players child
LEFT JOIN match_teams parent
  ON parent.id = child.match_team_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_team_players.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM match_team_players child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_teams.match_id->matches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM match_teams child
LEFT JOIN matches parent
  ON parent.id = child.match_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM matches child
LEFT JOIN regions parent
  ON parent.id = child.region_id
WHERE child.region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM matches child
LEFT JOIN monthly_batches parent
  ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.winning_team_id->match_teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM matches child
LEFT JOIN match_teams parent
  ON parent.id = child.winning_team_id
WHERE child.winning_team_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_assessment_history.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_assessment_history child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_assessment_history.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_assessment_history child
LEFT JOIN monthly_batches parent
  ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_rating_history.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_rating_history child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_rating_history.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_rating_history child
LEFT JOIN monthly_batches parent
  ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_registrations child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_registrations child
LEFT JOIN monthly_batches parent
  ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.assigned_region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM player_registrations child
LEFT JOIN regions parent
  ON parent.id = child.assigned_region_id
WHERE child.assigned_region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'players.home_region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM players child
LEFT JOIN regions parent
  ON parent.id = child.home_region_id
WHERE child.home_region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'team_memberships.team_id->teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM team_memberships child
LEFT JOIN teams parent
  ON parent.id = child.team_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'team_memberships.player_id->players.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_parent_rows=' || COUNT(*)::VARCHAR
FROM team_memberships child
LEFT JOIN players parent
  ON parent.id = child.player_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'match_shape',
    'matches.winning_team_id_same_match',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'mismatch_count=' || COUNT(*)::VARCHAR
FROM matches m
LEFT JOIN match_teams mt
  ON mt.id = m.winning_team_id
 AND mt.match_id = m.id
WHERE m.winning_team_id IS NOT NULL
  AND mt.id IS NULL;

INSERT INTO qc_results
SELECT
    'match_shape',
    'exactly_two_match_teams_per_match',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM (
    SELECT m.id
    FROM matches m
    LEFT JOIN match_teams mt
      ON mt.match_id = m.id
    GROUP BY m.id
    HAVING COUNT(mt.id) <> 2
) failures;

INSERT INTO qc_results
SELECT
    'match_shape',
    'match_teams_have_players',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM (
    SELECT mt.id
    FROM match_teams mt
    LEFT JOIN match_team_players mtp
      ON mtp.match_team_id = mt.id
    GROUP BY mt.id
    HAVING COUNT(mtp.id) = 0
) failures;

INSERT INTO qc_results
SELECT
    'temporal',
    'monthly_batches_match_manifest_sequences',
    CASE WHEN COALESCE(to_json(list(batch_sequence ORDER BY batch_sequence)), '[]') = COALESCE(to_json(included_batch_sequences), '[]')
         THEN 'passed' ELSE 'failed' END,
    CASE WHEN COALESCE(to_json(list(batch_sequence ORDER BY batch_sequence)), '[]') = COALESCE(to_json(included_batch_sequences), '[]')
         THEN 0 ELSE 1 END,
    'manifest=' || COALESCE(to_json(included_batch_sequences), '[]')
    || ' actual=' || COALESCE(to_json(list(batch_sequence ORDER BY batch_sequence)), '[]')
FROM monthly_batches
CROSS JOIN manifest
GROUP BY included_batch_sequences;

INSERT INTO qc_results
SELECT
    'temporal',
    'monthly_batch_months_unique',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'duplicate_month_count=' || COUNT(*)::VARCHAR
FROM (
    SELECT batch_month
    FROM monthly_batches
    GROUP BY batch_month
    HAVING COUNT(*) > 1
) duplicates;

INSERT INTO qc_results
SELECT
    'temporal',
    'clubs_founding_date_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM clubs
CROSS JOIN manifest
WHERE founding_date IS NOT NULL
  AND CAST(founding_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'club_memberships_start_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM club_memberships
CROSS JOIN manifest
WHERE CAST(start_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'club_memberships_end_not_in_future',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM club_memberships
CROSS JOIN manifest
WHERE end_date IS NOT NULL
  AND CAST(end_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'players_registration_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM players
CROSS JOIN manifest
WHERE CAST(registration_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'team_memberships_joined_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM team_memberships
CROSS JOIN manifest
WHERE CAST(joined_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'team_memberships_left_not_in_future',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM team_memberships
CROSS JOIN manifest
WHERE left_date IS NOT NULL
  AND CAST(left_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'teams_formed_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM teams
CROSS JOIN manifest
WHERE CAST(formation_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'temporal',
    'teams_dissolution_not_in_future',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'failure_count=' || COUNT(*)::VARCHAR
FROM teams
CROSS JOIN manifest
WHERE dissolution_date IS NOT NULL
  AND CAST(dissolution_date AS DATE) >= CAST(snapshot_end_exclusive AS DATE);

INSERT INTO qc_results
SELECT
    'batch_window',
    'matches.batch_id_in_release_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_batch_count=' || COUNT(*)::VARCHAR
FROM matches fact
LEFT JOIN monthly_batches batch
  ON batch.id = fact.batch_id
WHERE batch.id IS NULL;

INSERT INTO qc_results
SELECT
    'batch_window',
    'player_assessment_history.batch_id_in_release_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_batch_count=' || COUNT(*)::VARCHAR
FROM player_assessment_history fact
LEFT JOIN monthly_batches batch
  ON batch.id = fact.batch_id
WHERE batch.id IS NULL;

INSERT INTO qc_results
SELECT
    'batch_window',
    'player_rating_history.batch_id_in_release_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_batch_count=' || COUNT(*)::VARCHAR
FROM player_rating_history fact
LEFT JOIN monthly_batches batch
  ON batch.id = fact.batch_id
WHERE batch.id IS NULL;

INSERT INTO qc_results
SELECT
    'batch_window',
    'player_registrations.batch_id_in_release_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing_batch_count=' || COUNT(*)::VARCHAR
FROM player_registrations fact
LEFT JOIN monthly_batches batch
  ON batch.id = fact.batch_id
WHERE batch.id IS NULL;

SELECT
    category,
    check_name,
    status,
    failure_count,
    details
FROM qc_results
ORDER BY
    CASE status WHEN 'failed' THEN 0 ELSE 1 END,
    category,
    check_name;

SELECT
    status,
    COUNT(*) AS check_count
FROM qc_results
GROUP BY status
ORDER BY status;

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM qc_results WHERE status = 'failed')
            THEN error(
                'Student dataset QC failed. Inspect failed rows in qc_results output.'
            )
        ELSE 'Student dataset QC passed.'
    END AS qc_outcome;
