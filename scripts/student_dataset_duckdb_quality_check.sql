-- Student dataset release quality checks using DuckDB only.
--
-- Usage:
--   SET VARIABLE release_dir = '/abs/path/to/release_folder';
--   .read scripts/student_dataset_duckdb_quality_check.sql

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
    ('player_master', 'player_master.parquet', TRUE),
    ('player_registrations', 'player_registrations.parquet', TRUE),
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
    ('club_memberships', 5, 'joined_date'),
    ('club_memberships', 6, 'left_date'),
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
    ('player_master', 1, 'player_id'),
    ('player_master', 2, 'external_player_key'),
    ('player_master', 3, 'first_name'),
    ('player_master', 4, 'last_name'),
    ('player_master', 5, 'gender'),
    ('player_master', 6, 'birth_date'),
    ('player_master', 7, 'dominant_hand'),
    ('player_master', 8, 'home_region_id'),
    ('player_master', 9, 'registration_date'),
    ('player_master', 10, 'player_status'),
    ('player_master', 11, 'rating_value'),
    ('player_master', 12, 'confidence_score'),
    ('player_master', 13, 'volatility_score'),
    ('player_master', 14, 'global_percentile'),
    ('player_master', 15, 'match_count_used'),
    ('player_master', 16, 'rating_date'),
    ('player_master', 17, 'rating_batch_id'),
    ('player_master', 18, 'snapshot_month'),
    ('player_registrations', 1, 'id'),
    ('player_registrations', 2, 'player_id'),
    ('player_registrations', 3, 'batch_id'),
    ('player_registrations', 4, 'registration_month'),
    ('player_registrations', 5, 'registration_source'),
    ('player_registrations', 6, 'assigned_region_id'),
    ('player_registrations', 7, 'initial_rating_value'),
    ('player_registrations', 8, 'initial_confidence_score'),
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
    ('teams', 4, 'country_code'),
    ('teams', 5, 'formation_date'),
    ('teams', 6, 'dissolution_date');

CREATE OR REPLACE TEMP VIEW actual_files AS
SELECT regexp_extract(file, '[^/]+$', 0) AS file_name
FROM glob(getvariable('release_dir') || '/*.parquet');

INSERT INTO qc_results
SELECT
    'files',
    'file_exists:' || table_name,
    CASE WHEN EXISTS (
        SELECT 1 FROM actual_files WHERE file_name = output_file
    ) THEN 'passed' ELSE 'failed' END,
    CASE WHEN EXISTS (
        SELECT 1 FROM actual_files WHERE file_name = output_file
    ) THEN 0 ELSE 1 END,
    output_file
FROM expected_tables;

INSERT INTO qc_results
SELECT
    'files',
    'unexpected_parquet_files_absent',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    COALESCE(string_agg(file_name, ', ' ORDER BY file_name), '')
FROM (
    SELECT file_name FROM actual_files
    EXCEPT
    SELECT output_file FROM expected_tables
) unexpected;

CREATE OR REPLACE VIEW clubs AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/clubs.parquet');

CREATE OR REPLACE VIEW club_memberships AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/club_memberships.parquet');

CREATE OR REPLACE VIEW match_games AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/match_games.parquet');

CREATE OR REPLACE VIEW match_team_players AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/match_team_players.parquet');

CREATE OR REPLACE VIEW match_teams AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/match_teams.parquet');

CREATE OR REPLACE VIEW matches AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/matches.parquet');

CREATE OR REPLACE VIEW monthly_batches AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/monthly_batches.parquet');

CREATE OR REPLACE VIEW player_assessment_history AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/player_assessment_history.parquet');

CREATE OR REPLACE VIEW player_master AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/player_master.parquet');

CREATE OR REPLACE VIEW player_registrations AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/player_registrations.parquet');

CREATE OR REPLACE VIEW regions AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/regions.parquet');

CREATE OR REPLACE VIEW team_memberships AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/team_memberships.parquet');

CREATE OR REPLACE VIEW teams AS
SELECT * FROM read_parquet(getvariable('release_dir') || '/teams.parquet');

CREATE OR REPLACE TEMP VIEW actual_columns AS
SELECT 'clubs' AS table_name, cid + 1 AS ordinal, name AS column_name FROM pragma_table_info('clubs')
UNION ALL SELECT 'club_memberships', cid + 1, name FROM pragma_table_info('club_memberships')
UNION ALL SELECT 'match_games', cid + 1, name FROM pragma_table_info('match_games')
UNION ALL SELECT 'match_team_players', cid + 1, name FROM pragma_table_info('match_team_players')
UNION ALL SELECT 'match_teams', cid + 1, name FROM pragma_table_info('match_teams')
UNION ALL SELECT 'matches', cid + 1, name FROM pragma_table_info('matches')
UNION ALL SELECT 'monthly_batches', cid + 1, name FROM pragma_table_info('monthly_batches')
UNION ALL SELECT 'player_assessment_history', cid + 1, name FROM pragma_table_info('player_assessment_history')
UNION ALL SELECT 'player_master', cid + 1, name FROM pragma_table_info('player_master')
UNION ALL SELECT 'player_registrations', cid + 1, name FROM pragma_table_info('player_registrations')
UNION ALL SELECT 'regions', cid + 1, name FROM pragma_table_info('regions')
UNION ALL SELECT 'team_memberships', cid + 1, name FROM pragma_table_info('team_memberships')
UNION ALL SELECT 'teams', cid + 1, name FROM pragma_table_info('teams');

CREATE OR REPLACE TEMP VIEW expected_column_lists AS
SELECT table_name, to_json(list(column_name ORDER BY ordinal)) AS columns_json
FROM expected_columns
GROUP BY table_name;

CREATE OR REPLACE TEMP VIEW actual_column_lists AS
SELECT table_name, to_json(list(column_name ORDER BY ordinal)) AS columns_json
FROM actual_columns
GROUP BY table_name;

INSERT INTO qc_results
SELECT
    'schema',
    'column_order:' || expected.table_name,
    CASE WHEN expected.columns_json = actual.columns_json THEN 'passed' ELSE 'failed' END,
    CASE WHEN expected.columns_json = actual.columns_json THEN 0 ELSE 1 END,
    'expected=' || expected.columns_json || ' actual=' || actual.columns_json
FROM expected_column_lists expected
JOIN actual_column_lists actual USING (table_name);

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
    UNION ALL SELECT 'player_master', manifest.row_counts.player_master FROM manifest
    UNION ALL SELECT 'player_registrations', manifest.row_counts.player_registrations FROM manifest
    UNION ALL SELECT 'regions', manifest.row_counts.regions FROM manifest
    UNION ALL SELECT 'team_memberships', manifest.row_counts.team_memberships FROM manifest
    UNION ALL SELECT 'teams', manifest.row_counts.teams FROM manifest
);

CREATE OR REPLACE TEMP VIEW actual_row_counts AS
SELECT 'clubs' AS table_name, COUNT(*) AS row_count FROM clubs
UNION ALL SELECT 'club_memberships', COUNT(*) FROM club_memberships
UNION ALL SELECT 'match_games', COUNT(*) FROM match_games
UNION ALL SELECT 'match_team_players', COUNT(*) FROM match_team_players
UNION ALL SELECT 'match_teams', COUNT(*) FROM match_teams
UNION ALL SELECT 'matches', COUNT(*) FROM matches
UNION ALL SELECT 'monthly_batches', COUNT(*) FROM monthly_batches
UNION ALL SELECT 'player_assessment_history', COUNT(*) FROM player_assessment_history
UNION ALL SELECT 'player_master', COUNT(*) FROM player_master
UNION ALL SELECT 'player_registrations', COUNT(*) FROM player_registrations
UNION ALL SELECT 'regions', COUNT(*) FROM regions
UNION ALL SELECT 'team_memberships', COUNT(*) FROM team_memberships
UNION ALL SELECT 'teams', COUNT(*) FROM teams;

INSERT INTO qc_results
SELECT
    'counts',
    'row_count:' || manifest.table_name,
    CASE WHEN manifest.row_count = actual.row_count THEN 'passed' ELSE 'failed' END,
    ABS(manifest.row_count - actual.row_count),
    'manifest=' || manifest.row_count || ' actual=' || actual.row_count
FROM manifest_row_counts manifest
JOIN actual_row_counts actual USING (table_name);

INSERT INTO qc_results
SELECT
    'counts',
    'required_non_empty:' || table_name,
    CASE WHEN row_count > 0 THEN 'passed' ELSE 'failed' END,
    CASE WHEN row_count > 0 THEN 0 ELSE 1 END,
    'row_count=' || row_count
FROM actual_row_counts
WHERE table_name IN (
    SELECT table_name
    FROM expected_tables
    WHERE required_non_empty
);

INSERT INTO qc_results
SELECT
    'manifest',
    'schema_version_is_1_3',
    CASE WHEN student_dataset_schema_version = '1.3' THEN 'passed' ELSE 'failed' END,
    CASE WHEN student_dataset_schema_version = '1.3' THEN 0 ELSE 1 END,
    COALESCE(student_dataset_schema_version, '')
FROM manifest;

INSERT INTO qc_results
SELECT
    'manifest',
    'monthly_batches_match_fact_batch_sequences',
    CASE
        WHEN COALESCE((SELECT to_json(list(batch_sequence ORDER BY batch_sequence)) FROM monthly_batches), '[]')
            = COALESCE((SELECT to_json(fact_batch_sequences) FROM manifest), '[]')
        THEN 'passed' ELSE 'failed'
    END,
    CASE
        WHEN COALESCE((SELECT to_json(list(batch_sequence ORDER BY batch_sequence)) FROM monthly_batches), '[]')
            = COALESCE((SELECT to_json(fact_batch_sequences) FROM manifest), '[]')
        THEN 0 ELSE 1
    END,
    'actual=' || COALESCE((SELECT to_json(list(batch_sequence ORDER BY batch_sequence)) FROM monthly_batches), '[]')
        || ' manifest=' || COALESCE((SELECT to_json(fact_batch_sequences) FROM manifest), '[]');

INSERT INTO qc_results
SELECT
    'relationships',
    'clubs.region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing region refs'
FROM clubs child
LEFT JOIN regions parent ON parent.id = child.region_id
WHERE child.region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'club_memberships.player_id->player_master.player_id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing player refs'
FROM club_memberships child
LEFT JOIN player_master parent ON parent.player_id = child.player_id
WHERE parent.player_id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'club_memberships.club_id->clubs.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing club refs'
FROM club_memberships child
LEFT JOIN clubs parent ON parent.id = child.club_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing region refs'
FROM matches child
LEFT JOIN regions parent ON parent.id = child.region_id
WHERE child.region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing batch refs'
FROM matches child
LEFT JOIN monthly_batches parent ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'matches.winning_team_id->match_teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing winning-team refs'
FROM matches child
LEFT JOIN match_teams parent ON parent.id = child.winning_team_id
WHERE child.winning_team_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_games.match_id->matches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing match refs'
FROM match_games child
LEFT JOIN matches parent ON parent.id = child.match_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_teams.match_id->matches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing match refs'
FROM match_teams child
LEFT JOIN matches parent ON parent.id = child.match_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_team_players.match_team_id->match_teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing match-team refs'
FROM match_team_players child
LEFT JOIN match_teams parent ON parent.id = child.match_team_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'match_team_players.player_id->player_master.player_id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing player refs'
FROM match_team_players child
LEFT JOIN player_master parent ON parent.player_id = child.player_id
WHERE parent.player_id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_assessment_history.player_id->player_master.player_id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing player refs'
FROM player_assessment_history child
LEFT JOIN player_master parent ON parent.player_id = child.player_id
WHERE parent.player_id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_assessment_history.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing batch refs'
FROM player_assessment_history child
LEFT JOIN monthly_batches parent ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_master.home_region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing home-region refs'
FROM player_master child
LEFT JOIN regions parent ON parent.id = child.home_region_id
WHERE child.home_region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.player_id->player_master.player_id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing player refs'
FROM player_registrations child
LEFT JOIN player_master parent ON parent.player_id = child.player_id
WHERE parent.player_id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.batch_id->monthly_batches.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing batch refs'
FROM player_registrations child
LEFT JOIN monthly_batches parent ON parent.id = child.batch_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'player_registrations.assigned_region_id->regions.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing assigned-region refs'
FROM player_registrations child
LEFT JOIN regions parent ON parent.id = child.assigned_region_id
WHERE child.assigned_region_id IS NOT NULL
  AND parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'team_memberships.team_id->teams.id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing team refs'
FROM team_memberships child
LEFT JOIN teams parent ON parent.id = child.team_id
WHERE parent.id IS NULL;

INSERT INTO qc_results
SELECT
    'relationships',
    'team_memberships.player_id->player_master.player_id',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'missing player refs'
FROM team_memberships child
LEFT JOIN player_master parent ON parent.player_id = child.player_id
WHERE parent.player_id IS NULL;

INSERT INTO qc_results
SELECT
    'shape',
    'matches_have_exactly_two_match_teams',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'matches with non-two team counts'
FROM (
    SELECT match_id
    FROM match_teams
    GROUP BY match_id
    HAVING COUNT(*) <> 2
) invalid;

INSERT INTO qc_results
SELECT
    'shape',
    'match_teams_have_players',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'match teams without players'
FROM (
    SELECT mt.id
    FROM match_teams mt
    LEFT JOIN match_team_players mtp ON mtp.match_team_id = mt.id
    GROUP BY mt.id
    HAVING COUNT(mtp.id) = 0
) invalid;

INSERT INTO qc_results
SELECT
    'player_master',
    'player_master_one_row_per_player',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'duplicate player ids'
FROM (
    SELECT player_id
    FROM player_master
    GROUP BY player_id
    HAVING COUNT(*) > 1
) duplicates;

INSERT INTO qc_results
SELECT
    'player_master',
    'player_master_snapshot_month_consistent',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'rows with mismatched snapshot_month'
FROM player_master
WHERE snapshot_month <> (SELECT CAST(snapshot_month AS DATE) FROM manifest);

INSERT INTO qc_results
SELECT
    'player_master',
    'player_master_rating_state_coherent',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'rows with inconsistent rating state'
FROM player_master
WHERE (
    rating_date IS NULL
    AND (
        rating_value IS NOT NULL
        OR rating_batch_id IS NOT NULL
        OR confidence_score IS NOT NULL
        OR volatility_score IS NOT NULL
        OR global_percentile IS NOT NULL
        OR match_count_used IS NOT NULL
    )
) OR (
    rating_date IS NOT NULL
    AND (rating_value IS NULL OR rating_batch_id IS NULL)
);

INSERT INTO qc_results
SELECT
    'temporal',
    'player_master_registration_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'rows on or after snapshot_end_exclusive'
FROM player_master
WHERE registration_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest);

INSERT INTO qc_results
SELECT
    'temporal',
    'player_master_rating_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'rating rows on or after snapshot_end_exclusive'
FROM player_master
WHERE rating_date IS NOT NULL
  AND rating_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest);

INSERT INTO qc_results
SELECT
    'temporal',
    'clubs_founded_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'club rows on or after snapshot_end_exclusive'
FROM clubs
WHERE founding_date IS NOT NULL
  AND founding_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest);

INSERT INTO qc_results
SELECT
    'temporal',
    'club_memberships_dates_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'membership rows leaking future dates'
FROM club_memberships
WHERE joined_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest)
   OR (left_date IS NOT NULL AND left_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest));

INSERT INTO qc_results
SELECT
    'temporal',
    'teams_dates_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'team rows leaking future dates'
FROM teams
WHERE formation_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest)
   OR (dissolution_date IS NOT NULL AND dissolution_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest));

INSERT INTO qc_results
SELECT
    'temporal',
    'team_memberships_dates_before_snapshot_end',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'team membership rows leaking future dates'
FROM team_memberships
WHERE joined_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest)
   OR (left_date IS NOT NULL AND left_date >= (SELECT CAST(snapshot_end_exclusive AS DATE) FROM manifest));

INSERT INTO qc_results
SELECT
    'fact_window',
    'matches_within_fact_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'matches outside fact window'
FROM matches m
LEFT JOIN monthly_batches b ON b.id = m.batch_id
WHERE b.id IS NULL;

INSERT INTO qc_results
SELECT
    'fact_window',
    'player_registrations_within_fact_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'registrations outside fact window'
FROM player_registrations r
LEFT JOIN monthly_batches b ON b.id = r.batch_id
WHERE b.id IS NULL;

INSERT INTO qc_results
SELECT
    'fact_window',
    'player_assessment_history_within_fact_window',
    CASE WHEN COUNT(*) = 0 THEN 'passed' ELSE 'failed' END,
    COUNT(*),
    'assessments outside fact window'
FROM player_assessment_history a
LEFT JOIN monthly_batches b ON b.id = a.batch_id
WHERE b.id IS NULL;

SELECT *
FROM qc_results
ORDER BY
    CASE status WHEN 'failed' THEN 0 ELSE 1 END,
    category,
    check_name;
