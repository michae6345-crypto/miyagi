-- Learner curve vs the tutorial's reference curve, read from the metrics_1s continuous aggregate.
--
-- Runs happen at different wall-clock times, so the two curves are aligned by TRAINING STEP:
-- each 1-second bucket of the learner's run (avg value, max step) is paired with the tutorial
-- bucket whose step is nearest, if that one lies within 10 percent of the step (min 50 steps).
-- gap_decades = log10(learner / tutorial): 0 = on track, +1 = loss 10x higher than the tutorial.
--
-- params: %(learner)s run id, %(tutorial)s run id, %(metric)s metric name (e.g. 'loss')
WITH learner AS (
  SELECT bucket, step, value FROM metrics_1s
  WHERE run_id = %(learner)s AND name = %(metric)s
), tutorial AS (
  SELECT step, value FROM metrics_1s
  WHERE run_id = %(tutorial)s AND name = %(metric)s
)
SELECT l.bucket,
       l.step,
       l.value AS learner,
       t.value AS tutorial,
       t.step  AS tutorial_step,
       CASE WHEN l.value > 0 AND t.value > 0 THEN log10(l.value / t.value) END AS gap_decades
FROM learner l
LEFT JOIN LATERAL (
  SELECT step, value FROM tutorial
  WHERE abs(tutorial.step - l.step) <= GREATEST(50, 0.1 * l.step)
  ORDER BY abs(tutorial.step - l.step)
  LIMIT 1
) t ON TRUE
ORDER BY l.step;
