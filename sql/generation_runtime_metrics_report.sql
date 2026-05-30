-- Runtime instrumentation report for generation runs.
--
-- psql variables:
--   run_id: optional generation_runs.id. If empty, the latest run with
--           generation_runtime_metrics rows is used.

\pset pager off
\pset null '(null)'

\echo ''
\echo '== Selected Generation Run =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
)
SELECT
    gr.id AS generation_run_id,
    gr.generation_name,
    gr.status AS run_status,
    gr.started_at,
    gr.completed_at,
    count(DISTINCT mb.id) AS batch_count_with_metrics,
    min(grm.started_at) AS first_metric_at,
    max(grm.completed_at) AS last_metric_at,
    round(sum(grm.elapsed_ms)::numeric / 1000, 3) AS measured_match_seconds
FROM selected_run sr
JOIN generation_runs gr ON gr.id = sr.generation_run_id
JOIN generation_runtime_metrics grm ON grm.generation_run_id = gr.id
    AND grm.stage_name = 'matches'
    AND COALESCE(grm.metadata_json->>'parent_subphase', '') = ''
LEFT JOIN monthly_batches mb ON mb.id = grm.batch_id
GROUP BY gr.id, gr.generation_name, gr.status, gr.started_at, gr.completed_at
ORDER BY gr.id;

\echo ''
\echo '== Batch-Level Match Runtime Summary =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
batch_metrics AS (
    SELECT
        mb.id AS batch_id,
        mb.batch_sequence,
        mb.batch_month,
        mb.processing_status,
        mb.match_count_generated,
        sum(grm.elapsed_ms) AS measured_elapsed_ms,
        max(grm.completed_at) - min(grm.started_at) AS wall_clock_span,
        sum(grm.elapsed_ms) FILTER (WHERE grm.subphase_name = 'planning') AS planning_ms,
        sum(grm.elapsed_ms) FILTER (WHERE grm.subphase_name = 'load_recent_pair_dates') AS rematch_lookup_ms,
        sum(grm.elapsed_ms) FILTER (
            WHERE grm.subphase_name IN (
                'persist_matches',
                'persist_match_teams',
                'persist_match_related_rows',
                'finalize_batch'
            )
        ) AS persistence_ms,
        max(grm.output_count) FILTER (WHERE grm.subphase_name = 'planning') AS planned_matches,
        max(grm.attempt_count) FILTER (WHERE grm.subphase_name = 'planning') AS planning_attempts
    FROM selected_run sr
    JOIN monthly_batches mb ON mb.generation_run_id = sr.generation_run_id
    LEFT JOIN generation_runtime_metrics grm
        ON grm.batch_id = mb.id
        AND grm.stage_name = 'matches'
        AND COALESCE(grm.metadata_json->>'parent_subphase', '') = ''
    GROUP BY
        mb.id,
        mb.batch_sequence,
        mb.batch_month,
        mb.processing_status,
        mb.match_count_generated
)
SELECT
    batch_sequence,
    batch_month,
    batch_id,
    processing_status,
    match_count_generated,
    round(measured_elapsed_ms::numeric / 1000, 3) AS measured_seconds,
    wall_clock_span,
    round(planning_ms::numeric / 1000, 3) AS planning_seconds,
    round(rematch_lookup_ms::numeric / 1000, 3) AS rematch_lookup_seconds,
    round(persistence_ms::numeric / 1000, 3) AS persistence_seconds,
    planned_matches,
    planning_attempts,
    round(planning_attempts::numeric / nullif(planned_matches, 0), 3) AS attempts_per_match
FROM batch_metrics
ORDER BY batch_sequence;

\echo ''
\echo '== Subphase Duration by Batch =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
)
SELECT
    mb.batch_sequence,
    mb.batch_month,
    grm.batch_id,
    grm.subphase_name,
    grm.event_type,
    round(grm.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    grm.input_count,
    grm.output_count,
    grm.attempt_count,
    grm.started_at,
    grm.completed_at
FROM selected_run sr
JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
LEFT JOIN monthly_batches mb ON mb.id = grm.batch_id
WHERE grm.stage_name = 'matches'
ORDER BY mb.batch_sequence, grm.id;

\echo ''
\echo '== Subphase Totals and Share of Measured Match Time =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
subphase_totals AS (
    SELECT
        grm.subphase_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.input_count) AS input_count,
        sum(grm.output_count) AS output_count,
        sum(grm.attempt_count) AS attempt_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND COALESCE(grm.metadata_json->>'parent_subphase', '') = ''
    GROUP BY grm.subphase_name
),
total AS (
    SELECT sum(elapsed_ms) AS elapsed_ms FROM subphase_totals
)
SELECT
    st.subphase_name,
    st.metric_rows,
    round(st.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((st.elapsed_ms::numeric / nullif(t.elapsed_ms, 0)) * 100, 2) AS pct_of_measured_match_time,
    round(st.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(st.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    st.input_count,
    st.output_count,
    st.attempt_count
FROM subphase_totals st
CROSS JOIN total t
ORDER BY st.elapsed_ms DESC;

\echo ''
\echo '== Monthly Pipeline Stage Totals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
stage_totals AS (
    SELECT
        grm.subphase_name AS stage_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.output_count) AS output_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'monthly_pipeline'
        AND grm.event_type = 'completed'
    GROUP BY grm.subphase_name
),
total AS (
    SELECT sum(elapsed_ms) AS elapsed_ms FROM stage_totals
)
SELECT
    st.stage_name,
    st.metric_rows,
    round(st.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((st.elapsed_ms::numeric / nullif(t.elapsed_ms, 0)) * 100, 2) AS pct_of_pipeline_stage_time,
    round(st.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(st.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    st.output_count
FROM stage_totals st
CROSS JOIN total t
ORDER BY st.elapsed_ms DESC;

\echo ''
\echo '== Ratings Detail Totals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
ratings_totals AS (
    SELECT
        grm.subphase_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.input_count) AS input_count,
        sum(grm.output_count) AS output_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'ratings'
        AND grm.event_type = 'completed'
    GROUP BY grm.subphase_name
),
total AS (
    SELECT sum(elapsed_ms) AS elapsed_ms FROM ratings_totals
)
SELECT
    rt.subphase_name,
    rt.metric_rows,
    round(rt.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((rt.elapsed_ms::numeric / nullif(t.elapsed_ms, 0)) * 100, 2) AS pct_of_ratings_time,
    round(rt.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(rt.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    rt.input_count,
    rt.output_count
FROM ratings_totals rt
CROSS JOIN total t
ORDER BY rt.elapsed_ms DESC;

\echo ''
\echo '== Planning Detail Totals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
planning_total AS (
    SELECT sum(grm.elapsed_ms) AS elapsed_ms
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.subphase_name = 'planning'
        AND grm.event_type = 'completed'
),
planning_details AS (
    SELECT
        grm.subphase_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.input_count) AS input_count,
        sum(grm.output_count) AS output_count,
        sum(grm.attempt_count) AS attempt_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.metadata_json->>'parent_subphase' = 'planning'
    GROUP BY grm.subphase_name
)
SELECT
    pd.subphase_name,
    pd.metric_rows,
    round(pd.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((pd.elapsed_ms::numeric / nullif(pt.elapsed_ms, 0)) * 100, 2) AS pct_of_planning_time,
    round(pd.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(pd.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    pd.input_count,
    pd.output_count,
    pd.attempt_count
FROM planning_details pd
CROSS JOIN planning_total pt
ORDER BY pd.elapsed_ms DESC;

\echo ''
\echo '== Scoring Detail Totals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
scoring_total AS (
    SELECT sum(grm.elapsed_ms) AS elapsed_ms
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.subphase_name = 'scoring'
        AND grm.event_type = 'completed'
),
scoring_details AS (
    SELECT
        grm.subphase_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.input_count) AS input_count,
        sum(grm.output_count) AS output_count,
        sum(grm.attempt_count) AS attempt_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.metadata_json->>'parent_subphase' = 'scoring'
    GROUP BY grm.subphase_name
)
SELECT
    sd.subphase_name,
    sd.metric_rows,
    round(sd.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((sd.elapsed_ms::numeric / nullif(st.elapsed_ms, 0)) * 100, 2) AS pct_of_scoring_time,
    round(sd.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(sd.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    sd.input_count,
    sd.output_count,
    sd.attempt_count
FROM scoring_details sd
CROSS JOIN scoring_total st
ORDER BY sd.elapsed_ms DESC;

\echo ''
\echo '== Related Row Persistence Detail Totals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
persistence_total AS (
    SELECT sum(grm.elapsed_ms) AS elapsed_ms
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.subphase_name = 'persist_match_related_rows'
        AND grm.event_type = 'completed'
),
persistence_details AS (
    SELECT
        grm.subphase_name,
        count(*) AS metric_rows,
        sum(grm.elapsed_ms) AS elapsed_ms,
        avg(grm.elapsed_ms) AS avg_elapsed_ms,
        max(grm.elapsed_ms) AS max_elapsed_ms,
        sum(grm.input_count) AS input_count,
        sum(grm.output_count) AS output_count
    FROM selected_run sr
    JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
    WHERE grm.stage_name = 'matches'
        AND grm.metadata_json->>'parent_subphase' = 'persist_match_related_rows'
    GROUP BY grm.subphase_name
)
SELECT
    pd.subphase_name,
    pd.metric_rows,
    round(pd.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    round((pd.elapsed_ms::numeric / nullif(pt.elapsed_ms, 0)) * 100, 2) AS pct_of_related_persistence_time,
    round(pd.avg_elapsed_ms::numeric / 1000, 3) AS avg_seconds,
    round(pd.max_elapsed_ms::numeric / 1000, 3) AS max_seconds,
    pd.input_count,
    pd.output_count
FROM persistence_details pd
CROSS JOIN persistence_total pt
ORDER BY pd.elapsed_ms DESC;

\echo ''
\echo '== Month-over-Month Slowdown Signals =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
batch_totals AS (
    SELECT
        mb.batch_sequence,
        mb.batch_month,
        mb.id AS batch_id,
        sum(grm.elapsed_ms) AS total_ms,
        sum(grm.elapsed_ms) FILTER (WHERE grm.subphase_name = 'planning') AS planning_ms,
        sum(grm.elapsed_ms) FILTER (WHERE grm.subphase_name = 'load_recent_pair_dates') AS rematch_lookup_ms,
        max(grm.output_count) FILTER (WHERE grm.subphase_name = 'planning') AS planned_matches,
        max(grm.attempt_count) FILTER (WHERE grm.subphase_name = 'planning') AS planning_attempts
    FROM selected_run sr
    JOIN monthly_batches mb ON mb.generation_run_id = sr.generation_run_id
    JOIN generation_runtime_metrics grm
        ON grm.batch_id = mb.id
        AND grm.stage_name = 'matches'
        AND COALESCE(grm.metadata_json->>'parent_subphase', '') = ''
    GROUP BY mb.batch_sequence, mb.batch_month, mb.id
)
SELECT
    batch_sequence,
    batch_month,
    batch_id,
    round(total_ms::numeric / 1000, 3) AS total_seconds,
    round(
        (total_ms - lag(total_ms) OVER (ORDER BY batch_sequence))::numeric / 1000,
        3
    ) AS seconds_delta_from_prior_month,
    round(
        (total_ms::numeric / nullif(first_value(total_ms) OVER (ORDER BY batch_sequence), 0)),
        3
    ) AS multiple_of_first_month,
    round(planning_ms::numeric / 1000, 3) AS planning_seconds,
    round(rematch_lookup_ms::numeric / 1000, 3) AS rematch_lookup_seconds,
    planned_matches,
    planning_attempts,
    round(planning_attempts::numeric / nullif(planned_matches, 0), 3) AS attempts_per_match
FROM batch_totals
ORDER BY batch_sequence;

\echo ''
\echo '== Slowest Individual Metrics =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
)
SELECT
    mb.batch_sequence,
    mb.batch_month,
    grm.batch_id,
    grm.stage_name,
    grm.subphase_name,
    grm.event_type,
    round(grm.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    grm.input_count,
    grm.output_count,
    grm.attempt_count,
    grm.metadata_json
FROM selected_run sr
JOIN generation_runtime_metrics grm ON grm.generation_run_id = sr.generation_run_id
LEFT JOIN monthly_batches mb ON mb.id = grm.batch_id
ORDER BY grm.elapsed_ms DESC
LIMIT 25;

\echo ''
\echo '== Missing or Failed Match Metrics =='
WITH selected_run AS (
    SELECT COALESCE(
        NULLIF(:'run_id', '')::bigint,
        (
            SELECT generation_run_id
            FROM generation_runtime_metrics
            GROUP BY generation_run_id
            ORDER BY max(started_at) DESC
            LIMIT 1
        )
    ) AS generation_run_id
),
expected_subphases AS (
    SELECT unnest(ARRAY[
        'load_active_teams',
        'calculate_team_targets',
        'load_recent_pair_dates',
        'planning',
        'persist_matches',
        'scoring',
        'persist_match_teams',
        'build_match_team_players',
        'persist_match_related_rows',
        'finalize_batch'
    ]) AS subphase_name
),
batch_subphases AS (
    SELECT
        mb.id AS batch_id,
        mb.batch_sequence,
        mb.batch_month,
        mb.processing_status,
        es.subphase_name
    FROM selected_run sr
    JOIN monthly_batches mb ON mb.generation_run_id = sr.generation_run_id
    CROSS JOIN expected_subphases es
)
SELECT
    bs.batch_sequence,
    bs.batch_month,
    bs.batch_id,
    bs.processing_status,
    bs.subphase_name,
    COALESCE(grm.event_type, 'missing') AS metric_status,
    round(grm.elapsed_ms::numeric / 1000, 3) AS elapsed_seconds,
    grm.metadata_json
FROM batch_subphases bs
LEFT JOIN generation_runtime_metrics grm
    ON grm.batch_id = bs.batch_id
    AND grm.stage_name = 'matches'
    AND grm.subphase_name = bs.subphase_name
WHERE grm.id IS NULL OR grm.event_type <> 'completed'
ORDER BY bs.batch_sequence, bs.subphase_name;
