# 🧗 Climbing Training Tracker

A full-stack, multi-user training platform for climbers: each user gets their own private training history, sports-science analytics, and an ACWR-guarded engine that generates and adapts multi-week training plans from their own history.

![Python](https://img.shields.io/badge/python-3.10%2B-blue
)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![Supabase](https://img.shields.io/badge/database-Supabase-3ECF8E)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

**Accounts**
- Email/password login via Supabase Auth - every user's sessions, goals, and exercise library are private, enforced at the database level with Row-Level Security.

**Logging**
- Click-to-edit calendar - click any day to log or amend a session.
- Before / During / After exercise phasing, pulled from an Exercise Library.
- Smart defaults pre-fill warm-up/cool-down from your last session; a catch-up carousel surfaces anything left unlogged.

**Training Plans**
- Set a target grade and the weekdays you actually train on; get a phased (Base → Build → Peak) plan with a category and exercises for every scheduled day.
- Pace, category emphasis, and effort assumptions are personalized from your own logged history rather than fixed defaults, with a fallback when history is thin.
- Every generated day is checked against a forward-simulated Acute:Chronic Workload Ratio and automatically downgraded if it would spike injury risk.

**Analytics**
- Color-coded training calendar and a live KPI strip (streak, weekly volume, ACWR, days since last session).
- Effort trend and gym/Moonboard grade progression over a custom date range.
- Acute:Chronic Workload Ratio (ACWR) with risk-banded visualization.
- Effort-vs-grade yield and top-session highlights.

---

## Tech Stack

| Layer            | Tool                                                                                                        |
|-------------------|-------------------------------------------------------------------------------------------------------------|
| Dashboard / UI    | [Streamlit](https://streamlit.io) (custom dark theme) + [streamlit-calendar](https://github.com/im-perativa/streamlit-calendar) |
| Charts            | [Plotly](https://plotly.com/python/)                                                                        |
| Data validation   | [Pydantic](https://docs.pydantic.dev)                                                                       |
| Data processing   | pandas, numpy                                                                                                |
| Database          | [Supabase](https://supabase.com) (Postgres) via [supabase-py](https://github.com/supabase/supabase-py)      |

---

## Data Architecture

🗄️ **Supabase** (Postgres) ➔ 🐍 **Pandas + Pydantic** (validation & cleaning) ➔ 📊 **Streamlit** (dashboard)

Every row fetched from Supabase is validated with Pydantic before it reaches the dashboard - validation is enforced at the application layer.

---

## Project Structure

```
.
├── app.py                       # Page setup, auth gate, caching, tab dispatch
├── theme.py
├── auth/                        # Supabase Auth: login, signup, logout, session restore
│   ├── client.py
│   └── session.py
├── data_pipeline/               # Supabase I/O, Pydantic validation, data cleaning, analytics
│   ├── models.py
│   ├── cleaning.py
│   ├── sessions.py
│   ├── exercises.py
│   └── analytics.py
├── training_plan/               # Training-plan generation engine
│   ├── algorithm.py
│   └── store.py
├── ui/                          # Tab and modal rendering, one module per screen
│   ├── auth_gate.py
│   ├── session_modal.py
│   ├── exercise_modals.py
│   ├── calendar_tab.py
│   ├── analytics_tab.py
│   ├── library_tab.py
│   └── goals_tab.py
├── .streamlit/config.toml       # Streamlit theme configuration
├── tests/
│   ├── test_data_pipeline.py    # Validation, cleaning, and analytics tests
│   └── test_training_plan.py    # Training-plan generation engine tests
├── requirements.txt
├── requirements-dev.txt
└── .env                         # Local Supabase credentials
```

---

## Prerequisites

- Python 3.10+
- A free [Supabase](https://supabase.com) account

---

## Setup

### 1. Clone the repository and install dependencies

```bash
git clone https://github.com/PedroRibaldo/climbing-training-tracker.git
cd climbing-training-tracker

python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Provision the database

1. Create a new project at [supabase.com](https://supabase.com) (the free tier is plenty for personal use).
2. Open the **SQL Editor** and run the schema in [Database Schema](#database-schema).
3. Go to **Connect** and note your Project URL and API key.

### 3. Configure credentials

Use the **anon/public** key here, not the service-role key - Row-Level Security (see [Database Schema](#database-schema)) is what keeps users' data separate, and a service-role key bypasses it entirely.

**Local development** - create a `.env` file in the project root:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-public-key
```

Account deletion needs a second, more privileged credential - the **service_role** key (Project Settings → API). Add it too:

```
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

> ⚠️ The service-role key bypasses Row-Level Security. It's only ever used server-side, for account deletion - never sent to the browser.

> ⚠️ `.env` contains real credentials. Never commit it.

**Streamlit Community Cloud** - in the app's **Advanced Settings → Secrets**, add:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-anon-public-key"
service_role_key = "your-service-role-key"
```

### 4. Run the app

```bash
streamlit run app.py
```

The dashboard opens automatically at `http://localhost:8501`.

### 5. Create your account

The app opens to a login/signup screen. Sign up with any email and password - Supabase sends a confirmation email before you can log in. Every session, goal, and exercise you create belongs only to your account.

---

## Database Schema

Six tables - a session can reference any number of exercises without repeating data, a goal drives the sessions it generates, and every user's data is isolated by Postgres Row-Level Security rather than app-code filtering alone.

Run this once, top to bottom, in a fresh project's SQL Editor - each table is fully defined in place, Row-Level Security included, so there's no separate migration pass to run afterward.

```sql
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP DEFAULT now(),
    display_name TEXT,
    avatar_url TEXT,
    weight_kg NUMERIC CHECK (weight_kg IS NULL OR weight_kg > 0),
    height_cm NUMERIC CHECK (height_cm IS NULL OR height_cm > 0),
    current_gym_grade TEXT,
    current_moonboard_grade TEXT
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "select own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "update own profile" ON profiles FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Persistent injury log - separate from climbing_training.injured, which
-- stays as a per-session flag.
CREATE TABLE injuries (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE DEFAULT auth.uid(),
    body_part TEXT NOT NULL,
    description TEXT,
    started_at DATE NOT NULL,
    resolved_at DATE,                 -- NULL = still active
    created_at TIMESTAMP DEFAULT now(),
    CHECK (resolved_at IS NULL OR resolved_at >= started_at)
);

ALTER TABLE injuries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own injuries" ON injuries FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Avatar storage: one object per user, public-read, write-restricted to
-- each user's own folder.
INSERT INTO storage.buckets (id, name, public) VALUES ('avatars', 'avatars', true);

CREATE POLICY "own avatar upload" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);
CREATE POLICY "own avatar update" ON storage.objects FOR UPDATE
    USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);
CREATE POLICY "public avatar read" ON storage.objects FOR SELECT
    USING (bucket_id = 'avatars');

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id) VALUES (NEW.id);
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- One row per grade goal; only one 'active' row per user is expected at a time
CREATE TABLE goals (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE DEFAULT auth.uid(),
    created_at TIMESTAMP DEFAULT now(),
    target_type TEXT NOT NULL,              -- 'gym' | 'moonboard'
    target_grade TEXT NOT NULL,
    start_grade TEXT,                       -- best grade of that type logged when the goal was created
    weekly_frequency INTEGER NOT NULL,      -- derived as len(training_weekdays)
    training_weekdays JSONB NOT NULL,       -- e.g. ["Wednesday","Thursday","Saturday"]
    total_weeks INTEGER NOT NULL,
    phase_breakdown JSONB NOT NULL,         -- [{"name","start_week","end_week","weights"}, ...]
    status TEXT NOT NULL DEFAULT 'active'   -- 'active' | 'completed' | 'abandoned'
);

ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own goals" ON goals FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Reference table of exercises - private per user
CREATE TABLE exercise (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE DEFAULT auth.uid(),
    name TEXT NOT NULL,
    type TEXT,             -- 'Reps' | 'Time'
    sets INTEGER,
    reps INTEGER,          -- set when type = 'Reps'
    time TEXT,             -- set when type = 'Time', e.g. '00:15'
    rest INTEGER,
    comments TEXT,
    phase TEXT,            -- 'Before' | 'During' | 'After'
    mandatory BOOLEAN DEFAULT FALSE,         -- always included in generated plans for its phase
    exclude_from_plan BOOLEAN DEFAULT FALSE, -- never included in generated plans
    UNIQUE (user_id, name)
);

ALTER TABLE exercise ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own exercise" ON exercise FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- One row per logged (or scheduled) training session
CREATE TABLE climbing_training (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE DEFAULT auth.uid(),
    date_entry TIMESTAMP,
    date DATE NOT NULL,
    category TEXT,          -- 'Strength' | 'Stamina' | 'Technique' | 'Free' | 'Rest'
    effort INTEGER,          -- 1-10, blank until the session is actually logged
    gym_grade TEXT,
    moonboard_grade TEXT,
    injured BOOLEAN DEFAULT FALSE,
    goal_id BIGINT REFERENCES goals(id) ON DELETE SET NULL  -- which plan (if any) generated this session
);

ALTER TABLE climbing_training ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own climbing_training" ON climbing_training FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Many-to-many: which exercises belong to which session
CREATE TABLE training_exercises (
    training_id BIGINT REFERENCES climbing_training(id) ON DELETE CASCADE,
    exercise_id BIGINT REFERENCES exercise(id) ON DELETE CASCADE,
    PRIMARY KEY (training_id, exercise_id)
);

ALTER TABLE training_exercises ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own training_exercises" ON training_exercises FOR ALL
    USING (EXISTS (SELECT 1 FROM climbing_training ct WHERE ct.id = training_exercises.training_id AND ct.user_id = auth.uid()))
    WITH CHECK (EXISTS (SELECT 1 FROM climbing_training ct WHERE ct.id = training_exercises.training_id AND ct.user_id = auth.uid()));

-- Many-to-many: which training categories an exercise is tagged for
CREATE TABLE exercise_categories (
    exercise_id BIGINT REFERENCES exercise(id) ON DELETE CASCADE,
    category TEXT NOT NULL,           -- 'Strength' | 'Stamina' | 'Technique' | 'Free'
    PRIMARY KEY (exercise_id, category)
);

ALTER TABLE exercise_categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own exercise_categories" ON exercise_categories FOR ALL
    USING (EXISTS (SELECT 1 FROM exercise e WHERE e.id = exercise_categories.exercise_id AND e.user_id = auth.uid()))
    WITH CHECK (EXISTS (SELECT 1 FROM exercise e WHERE e.id = exercise_categories.exercise_id AND e.user_id = auth.uid()));
```

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Covers Pydantic validation (valid and deliberately invalid rows), the past/future session split, the analytics functions (`compute_acwr`, `get_peak_sessions`), and the training-plan engine all against hand-built edge cases.

---

## License

This project is licensed under the [MIT License](LICENSE).