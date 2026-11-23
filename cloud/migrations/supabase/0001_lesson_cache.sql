-- miyagi-cloud shared lesson cache on Postgres (Supabase project wssdpsdbaqtnfhoyimit).
--
-- NOT APPLIED. A file for the future move off SQLite (cloud/README.md, "Moving to Postgres"): nothing runs it, and
-- the live cache stays in SQLite (cloud/store.py) until a PostgresStore exists and is reviewed. Apply it by hand
-- (Supabase SQL editor or `supabase db push`) only together with that change.
--
-- It mirrors the SQLite lesson tables in cloud/store.py column for column, so PostgresStore can port the queries
-- as they are:
--   lesson_candidates  every uploaded lesson per (video, schema, uploader); GET /v1/lessons serves the approved one
--   builds             new-lesson builds per install and UTC month (FREE_LESSON_BUILDS_PER_MONTH)
--   lesson_puts        lesson uploads per install and UTC day (LESSON_PUTS_PER_DAY)
--   lesson_revocations videos an operator revoked: never auto-approved again
--   lesson_claims      build claims in progress (LESSON_CLAIM_TTL_S)
-- The legacy first-upload `lessons` table is not ported: store.py empties it into lesson_candidates on startup.
-- `builds` per user also reads `links (token_hash, user_id)`, which moves with the account tables, not here.
--
-- Times stay epoch seconds (double precision) as in SQLite. No raw install token, IP or user id is stored: uploader
-- and token_hash are sha256 hex of the install token, net is a keyed hash ('' once approved).
--
-- Access: only miyagi-cloud writes and reads these, with the service role key, which bypasses RLS. RLS is enabled with
-- NO policies, and anon / authenticated get no grants, so the app's public (anon) key and a signed-in user's JWT can
-- neither read nor write them through PostgREST. The tables live in their own schema, which is not in the API's
-- exposed schemas.

begin;

create schema if not exists miyagi_cloud;
revoke all on schema miyagi_cloud from public, anon, authenticated;
grant usage on schema miyagi_cloud to service_role;

-- GET /v1/lessons/{video_id}?schema=N serves the one approved candidate for (video_id, schema). The cache key is the
-- YouTube video id plus the lesson schema version (LESSON_SCHEMAS): a builder change that alters the lesson shape
-- must bump the schema so old lessons are not served to the new engine.
create table if not exists miyagi_cloud.lesson_candidates (
    video_id   text             not null check (video_id ~ '^[A-Za-z0-9_-]{11}$'),
    schema     integer          not null check (schema > 0),
    uploader   text             not null,                  -- sha256 hex of the uploading install token, or 'deleted-<random>'
    body       text             not null,                  -- the validated lesson JSON (UTF-8), served byte for byte
    bytes      integer          not null check (bytes >= 0),
    body_hash  text             not null,                  -- sha256 of the normalized lesson JSON (sorted keys)
    net        text             not null default '',       -- keyed network hash, '' once approved
    status     text             not null default 'pending' check (status in ('pending', 'approved', 'revoked')),
    created_at double precision not null,
    hits       integer          not null default 0,
    primary key (video_id, schema, uploader)
);
create index if not exists lesson_candidates_status on miyagi_cloud.lesson_candidates (status, video_id);
-- At most one approved lesson per video and schema (store.py keeps this by hand in _approve_row; here it is enforced).
create unique index if not exists lesson_candidates_one_approved
    on miyagi_cloud.lesson_candidates (video_id, schema) where status = 'approved';

create table if not exists miyagi_cloud.builds (
    token_hash text             not null,
    month      text             not null check (month ~ '^\d{4}-\d{2}$'),  -- YYYY-MM, UTC
    video_id   text             not null,
    created_at double precision not null,
    primary key (token_hash, month, video_id)
);
create index if not exists builds_month_video on miyagi_cloud.builds (month, video_id);

create table if not exists miyagi_cloud.lesson_puts (
    token_hash text    not null,
    day        text    not null check (day ~ '^\d{4}-\d{2}-\d{2}$'),     -- YYYY-MM-DD, UTC
    n          integer not null default 0,
    primary key (token_hash, day)
);

create table if not exists miyagi_cloud.lesson_claims (
    video_id   text             not null,
    schema     integer          not null,                  -- 0: the claim named no schema (holds every schema)
    token_hash text             not null,
    claimed_at double precision not null,
    expires_at double precision not null,
    primary key (video_id, schema, token_hash)
);

create table if not exists miyagi_cloud.lesson_revocations (
    video_id   text             not null,
    schema     integer          not null,
    revoked_at double precision not null,
    primary key (video_id, schema)
);

alter table miyagi_cloud.lesson_candidates enable row level security;
alter table miyagi_cloud.builds            enable row level security;
alter table miyagi_cloud.lesson_puts       enable row level security;
alter table miyagi_cloud.lesson_revocations enable row level security;
alter table miyagi_cloud.lesson_claims      enable row level security;
-- Also for the table owner, so a mistaken non-service connection cannot read around RLS.
alter table miyagi_cloud.lesson_candidates force row level security;
alter table miyagi_cloud.builds            force row level security;
alter table miyagi_cloud.lesson_puts       force row level security;
alter table miyagi_cloud.lesson_revocations force row level security;
alter table miyagi_cloud.lesson_claims      force row level security;
-- No policies on purpose: anon and authenticated see and change nothing.

revoke all on all tables in schema miyagi_cloud from public, anon, authenticated;
grant select, insert, update, delete on all tables in schema miyagi_cloud to service_role;
alter default privileges in schema miyagi_cloud revoke all on tables from public, anon, authenticated;

commit;
