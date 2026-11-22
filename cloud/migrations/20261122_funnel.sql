-- Activation funnel table for Supabase Postgres. A FILE ONLY: not applied anywhere yet.
--
-- Today miyagi-cloud keeps this table in its SQLite store (store.py SCHEMA `funnel`, filled by POST /v1/funnel).
-- This is the same table for the planned PostgresStore (store.py: "moving to Postgres (Supabase) later"). Apply it
-- only together with that move, and with Michael's yes: supabase db push, or paste it in the SQL editor.
--
-- Names and times only. The install's user comes from `links` (POST /v1/link), never from this table.
-- Retention (store.py prune): rows older than 35 days are counted into funnel_daily (no install), then deleted.
-- Note (Nov 22): no Postgres move is planned; this file documents the table for if that changes.

create table if not exists public.funnel (
    token_hash text        not null,           -- sha256 hex of the install token (never the token)
    name       text        not null check (name in ('first_launch', 'signed_in', 'permissions_granted',
                                                    'lesson_started', 'step_passed', 'lesson_finished')),
    first_at   timestamptz not null,           -- the earliest time this milestone happened on that install
    primary key (token_hash, name)
);

create index if not exists funnel_name_first_at on public.funnel (name, first_at);

-- Only the cloud's service role reads or writes it: RLS on, no policies, nothing granted to the public roles.
alter table public.funnel enable row level security;
revoke all on public.funnel from anon, authenticated;

create table if not exists public.funnel_daily (
    day      date    not null,
    name     text    not null,
    installs integer not null default 0,
    primary key (day, name)
);
alter table public.funnel_daily enable row level security;
revoke all on public.funnel_daily from anon, authenticated;

comment on table public.funnel is
    'Activation milestones per install (earliest time). Written by miyagi-cloud POST /v1/funnel; deleted with the account.';

-- The upsert the PostgresStore will run (keeps the earliest time):
--   insert into public.funnel (token_hash, name, first_at) values ($1, $2, $3)
--   on conflict (token_hash, name) do update set first_at = least(public.funnel.first_at, excluded.first_at);
