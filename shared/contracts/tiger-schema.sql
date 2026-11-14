-- Tiger Data (TimescaleDB) schema. Apply with: psql "$TIGER_DATABASE_URL" -f shared/contracts/tiger-schema.sql
CREATE TABLE IF NOT EXISTS lessons (id text PRIMARY KEY, title text, goal text, step_graph jsonb, created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS runs (
  id text PRIMARY KEY, lesson_id text, step_id text, source text DEFAULT 'learner',  -- 'learner' | 'tutorial'
  command text, exit_code int, started_at timestamptz, ended_at timestamptz, tail text);
CREATE TABLE IF NOT EXISTS training_metrics (time timestamptz NOT NULL, run_id text, step int, name text, value double precision);
SELECT create_hypertable('training_metrics', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS training_metrics_run ON training_metrics (run_id, name, step);
CREATE TABLE IF NOT EXISTS learning_events (time timestamptz NOT NULL, lesson_id text, step_id text, source_id text, video_t double precision,
  kind text,  -- step_started | check_pass | check_fail | offtrack | fix_applied | question | step_passed
  payload jsonb);
SELECT create_hypertable('learning_events', 'time', if_not_exists => TRUE);
-- live curves
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1s WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 second', time) AS bucket, run_id, name, avg(value) AS value, max(step) AS step
  FROM training_metrics GROUP BY bucket, run_id, name WITH NO DATA;
-- where learners get stuck, per video position
CREATE MATERIALIZED VIEW IF NOT EXISTS stuck_heatmap WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 hour', time) AS bucket, source_id, floor(video_t/15)*15 AS video_bucket, count(*) AS stuck
  FROM learning_events WHERE kind IN ('offtrack','check_fail') GROUP BY bucket, source_id, video_bucket WITH NO DATA;
