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
-- ---------------------------------------------------------------------------
-- GENERALITY RULE additions (additive only). Writers: server.checks.tiger.record_event / record_metric.
-- learning_events.payload conventions: check_* → {"check_id", "detail"}; step_passed → {"duration_s"} (filled by record_event).
ALTER TABLE learning_events ADD COLUMN IF NOT EXISTS session_id text;   -- one learner session (engine process / app launch)
ALTER TABLE learning_events ADD COLUMN IF NOT EXISTS check_id text;     -- for check_pass / check_fail
CREATE INDEX IF NOT EXISTS learning_events_lesson ON learning_events (lesson_id, step_id, time DESC);
-- how long each step takes (from step_started to step_passed), per lesson step
CREATE MATERIALIZED VIEW IF NOT EXISTS time_per_step WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 hour', time) AS bucket, lesson_id, step_id, count(*) AS passes,
         avg((payload->>'duration_s')::double precision) AS avg_s,
         min((payload->>'duration_s')::double precision) AS min_s,
         max((payload->>'duration_s')::double precision) AS max_s
  FROM learning_events WHERE kind = 'step_passed' GROUP BY bucket, lesson_id, step_id WITH NO DATA;
-- how often each check fails (fail_rate = fails / evaluations)
CREATE MATERIALIZED VIEW IF NOT EXISTS check_fail_rate WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 hour', time) AS bucket, lesson_id, step_id, check_id,
         sum(CASE WHEN kind = 'check_fail' THEN 1 ELSE 0 END) AS fails,
         sum(CASE WHEN kind = 'check_pass' THEN 1 ELSE 0 END) AS passes,
         count(*) AS evaluations
  FROM learning_events WHERE kind IN ('check_pass','check_fail') GROUP BY bucket, lesson_id, step_id, check_id WITH NO DATA;
-- a learner's progress over time (cumulative = running sum over buckets)
CREATE MATERIALIZED VIEW IF NOT EXISTS learner_progress WITH (timescaledb.continuous) AS
  SELECT time_bucket('1 minute', time) AS bucket, session_id, lesson_id,
         sum(CASE WHEN kind = 'step_passed' THEN 1 ELSE 0 END) AS steps_passed,
         sum(CASE WHEN kind = 'check_pass' THEN 1 ELSE 0 END) AS checks_passed,
         sum(CASE WHEN kind = 'check_fail' THEN 1 ELSE 0 END) AS checks_failed,
         sum(CASE WHEN kind = 'offtrack' THEN 1 ELSE 0 END) AS offtracks,
         max(video_t) AS video_t
  FROM learning_events GROUP BY bucket, session_id, lesson_id WITH NO DATA;
