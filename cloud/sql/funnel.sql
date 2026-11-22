-- Activation funnel: dashboard queries (Postgres, for the Supabase SQL editor once the funnel table lives there;
-- see migrations/20261122_funnel.sql). Until then GET /admin/funnel?days=N returns query 1 + 2 from SQLite.
--
-- Funnel: download → first_launch → signed_in → permissions_granted → lesson_started → step_passed → lesson_finished
-- Who is in it: installs whose learner turned on "Share crash reports and usage" and signed in. That is an opted-in
-- slice, so read shares as "of opted-in installs", not of all downloads. Download counts come from the site or the
-- GitHub release (download_count), not from here; installs minted (first launch, everyone) are `tokens` on the cloud.

-- 1. Installs per step and share of first launch (last 30 days of first launches).
with cohort as (
    select token_hash from funnel where name = 'first_launch' and first_at >= now() - interval '30 days'
),
steps(ord, name) as (
    values (1, 'first_launch'), (2, 'signed_in'), (3, 'permissions_granted'),
           (4, 'lesson_started'), (5, 'step_passed'), (6, 'lesson_finished')
)
select s.ord, s.name,
       count(f.token_hash)                                                          as installs,
       round(100.0 * count(f.token_hash) / nullif((select count(*) from cohort), 0), 1) as pct_of_first_launch
from steps s
left join funnel f on f.name = s.name and f.token_hash in (select token_hash from cohort)
group by s.ord, s.name
order by s.ord;

-- 2. Median and p75 time between consecutive steps (minutes), installs that reached both.
with p as (
    select token_hash,
           max(first_at) filter (where name = 'first_launch')        as first_launch,
           max(first_at) filter (where name = 'signed_in')           as signed_in,
           max(first_at) filter (where name = 'permissions_granted') as permissions_granted,
           max(first_at) filter (where name = 'lesson_started')      as lesson_started,
           max(first_at) filter (where name = 'step_passed')         as step_passed,
           max(first_at) filter (where name = 'lesson_finished')     as lesson_finished
    from funnel group by token_hash
),
gaps as (
    select 'first_launch → signed_in' as step, extract(epoch from signed_in - first_launch) / 60 as m from p
    union all select 'signed_in → permissions_granted', extract(epoch from permissions_granted - signed_in) / 60 from p
    union all select 'permissions_granted → lesson_started', extract(epoch from lesson_started - permissions_granted) / 60 from p
    union all select 'lesson_started → step_passed', extract(epoch from step_passed - lesson_started) / 60 from p
    union all select 'step_passed → lesson_finished', extract(epoch from lesson_finished - step_passed) / 60 from p
    union all select 'first_launch → lesson_finished (total)', extract(epoch from lesson_finished - first_launch) / 60 from p
)
select step,
       count(m)                                                          as installs,
       round((percentile_cont(0.5)  within group (order by m))::numeric, 1) as median_min,
       round((percentile_cont(0.75) within group (order by m))::numeric, 1) as p75_min
from gaps where m >= 0
group by step
order by min(case step when 'first_launch → signed_in' then 1 when 'signed_in → permissions_granted' then 2
                       when 'permissions_granted → lesson_started' then 3 when 'lesson_started → step_passed' then 4
                       when 'step_passed → lesson_finished' then 5 else 6 end);

-- 3. Weekly cohorts: of installs first launched each week, % reaching each step.
with p as (
    select token_hash,
           date_trunc('week', max(first_at) filter (where name = 'first_launch')) as week,
           bool_or(name = 'signed_in')           as signed_in,
           bool_or(name = 'permissions_granted') as permissions,
           bool_or(name = 'lesson_started')      as started,
           bool_or(name = 'step_passed')         as passed,
           bool_or(name = 'lesson_finished')     as finished
    from funnel group by token_hash
)
select week::date,
       count(*)                                                as installs,
       round(100.0 * avg(signed_in::int), 1)                   as pct_signed_in,
       round(100.0 * avg(permissions::int), 1)                 as pct_permissions,
       round(100.0 * avg(started::int), 1)                     as pct_lesson_started,
       round(100.0 * avg(passed::int), 1)                      as pct_step_passed,
       round(100.0 * avg(finished::int), 1)                    as pct_lesson_finished
from p where week is not null
group by week order by week desc limit 12;

-- 4. Where installs stall: the last step each install reached (installs older than 7 days, so they had time).
with last as (
    select f.token_hash,
           (array_agg(f.name order by array_position(array['first_launch', 'signed_in', 'permissions_granted',
                       'lesson_started', 'step_passed', 'lesson_finished'], f.name) desc))[1] as last_step
    from funnel f
    where f.token_hash in (select token_hash from funnel where name = 'first_launch' and first_at < now() - interval '7 days')
    group by f.token_hash
)
select last_step, count(*) as installs from last group by last_step order by installs desc;

-- 5. Time to first passed step, bucketed (the "aha" moment).
select case when m < 5 then 'a. < 5 min' when m < 15 then 'b. 5-15 min' when m < 60 then 'c. 15-60 min'
            when m < 1440 then 'd. 1-24 h' else 'e. > 1 day' end as bucket,
       count(*) as installs
from (
    select extract(epoch from max(first_at) filter (where name = 'step_passed')
                            - max(first_at) filter (where name = 'first_launch')) / 60 as m
    from funnel group by token_hash
) t
where m >= 0
group by bucket order by bucket;
