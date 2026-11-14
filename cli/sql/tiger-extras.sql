-- Applied by `tut db init` right after shared/contracts/tiger-schema.sql.
-- The contract creates the continuous aggregates WITH NO DATA and no refresh policy; on
-- TimescaleDB >= 2.13 they would then return nothing. These make them useful live:

-- metrics_1s: real-time aggregate (materialized buckets + raw rows newer than the watermark),
-- refreshed every 10 s, so live curves and the learner-vs-tutorial query see fresh points.
ALTER MATERIALIZED VIEW metrics_1s SET (timescaledb.materialized_only = false);
SELECT add_continuous_aggregate_policy('metrics_1s',
  start_offset => INTERVAL '7 days', end_offset => INTERVAL '2 seconds',
  schedule_interval => INTERVAL '10 seconds', if_not_exists => TRUE);

ALTER MATERIALIZED VIEW stuck_heatmap SET (timescaledb.materialized_only = false);
SELECT add_continuous_aggregate_policy('stuck_heatmap',
  start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '5 minutes', if_not_exists => TRUE);

-- find the tutorial reference run for a lesson step quickly
CREATE INDEX IF NOT EXISTS runs_source_step ON runs (source, lesson_id, step_id, started_at DESC);
