create table if not exists public.user_profiles (
  user_id text primary key,
  email text unique not null,
  name text,
  role text check (role in ('child', 'parent')),
  is_confirmed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_login_at timestamptz
);

create table if not exists public.family_invites (
  invite_id text primary key,
  invite_code text not null check (invite_code ~ '^[0-9]{4}$'),
  child_user_id text not null,
  status text not null check (status in ('pending', 'used', 'expired')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  used_at timestamptz
);

create unique index if not exists family_invites_pending_code_uniq
  on public.family_invites (invite_code)
  where status = 'pending';

create unique index if not exists family_invites_pending_child_uniq
  on public.family_invites (child_user_id)
  where status = 'pending';

create index if not exists family_invites_child_created_at_idx
  on public.family_invites (child_user_id, created_at desc);

create table if not exists public.family_links (
  link_id text primary key,
  parent_user_id text not null,
  child_user_id text not null,
  status text not null check (status in ('active')),
  created_at timestamptz not null default now(),
  connected_at timestamptz not null default now()
);

create unique index if not exists family_links_active_parent_uniq
  on public.family_links (parent_user_id)
  where status = 'active';

create unique index if not exists family_links_active_child_uniq
  on public.family_links (child_user_id)
  where status = 'active';

create index if not exists family_links_parent_connected_at_idx
  on public.family_links (parent_user_id, connected_at desc);

create index if not exists family_links_child_connected_at_idx
  on public.family_links (child_user_id, connected_at desc);

create table if not exists public.answers (
  answer_id text primary key,
  type text not null check (type in ('health', 'meal', 'mood')),
  user_id text not null,
  question_id text not null,
  answer_type text not null check (answer_type in ('choice', 'voice')),
  answer text,
  voice_status text check (voice_status in ('pending', 'uploaded', 'analyzed')),
  voice_file_key text,
  original_filename text,
  stored_filename text,
  content_type text,
  file_size integer,
  created_at timestamptz not null default now()
);

create index if not exists answers_user_type_created_at_idx
  on public.answers (user_id, type, created_at desc);

create index if not exists answers_user_created_at_idx
  on public.answers (user_id, created_at desc);

create table if not exists public.photos (
  photo_id text primary key,
  sender_user_id text not null,
  receiver_user_id text not null,
  image_url text not null,
  caption text,
  scheduled_at timestamptz,
  status text not null check (status in ('sent', 'scheduled', 'seen')),
  created_at timestamptz not null default now()
);

create index if not exists photos_sender_created_at_idx
  on public.photos (sender_user_id, created_at desc);

create index if not exists photos_receiver_status_created_at_idx
  on public.photos (receiver_user_id, status, created_at desc);

create table if not exists public.photo_reactions (
  reaction_id text primary key,
  photo_id text not null,
  user_id text not null,
  reaction_type text not null check (reaction_type in ('quick', 'voice')),
  label text,
  voice_url text,
  duration_seconds integer,
  created_at timestamptz not null default now()
);

create index if not exists photo_reactions_photo_created_at_idx
  on public.photo_reactions (photo_id, created_at desc);

create table if not exists public.dementia_analyses (
  analysis_id text primary key,
  answer_id text not null,
  user_id text not null,
  status text not null check (status in ('pending', 'transcribing', 'transcribed', 'analyzing', 'completed', 'failed')),
  transcript text,
  risk_level text check (risk_level in ('low', 'medium', 'high')),
  risk_score double precision,
  analysis_summary text,
  indicators jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists dementia_analyses_user_created_at_idx
  on public.dementia_analyses (user_id, created_at desc);

create table if not exists public.device_tokens (
  user_id text primary key,
  fcm_token text not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.notifications (
  notification_id text primary key,
  user_id text not null,
  title text not null,
  body text not null,
  data jsonb,
  is_read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists notifications_user_created_at_idx
  on public.notifications (user_id, created_at desc);
