# 🧗 Climbing Training Tracker

A full-stack personal training platform for climbers: fast session logging, sports-science analytics, and an ACWR-guarded engine that generates and adapts multi-week training plans from your own training history.

![Python](https://img.shields.io/badge/python-3.10%2B-blue
)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![Supabase](https://img.shields.io/badge/database-Supabase-3ECF8E)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

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
├── app.py                       # Page setup, caching, tab dispatch
├── theme.py
├── data_pipeline/               # Supabase I/O, Pydantic validation, data cleaning, analytics
│   ├── models.py
│   ├── client.py
│   ├── cleaning.py
│   ├── sessions.py
│   ├── exercises.py
│   └── analytics.py
├── training_plan/               # Training-plan generation engine
│   ├── algorithm.py
│   └── store.py
├── ui/                          # Tab and modal rendering, one module per screen
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

**Local development** - create a `.env` file in the project root:

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
```

> ⚠️ `.env` contains a real credential. Never commit it.

**Streamlit Community Cloud** - in the app's **Advanced Settings → Secrets**, add:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-service-role-key"
```

### 4. Run the app

```bash
streamlit run app.py
```

The dashboard opens automatically at `http://localhost:8501`.

---

## Database Schema

Five tables - a session can reference any number of exercises without repeating data, and a goal drives the sessions it generates.

```sql
-- One row per grade goal; only one 'active' row is expected at a time
CREATE TABLE goals (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
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

-- Reference table of exercises
CREATE TABLE exercise (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    name TEXT UNIQUE NOT NULL,
    type TEXT,             -- 'Reps' | 'Time'
    sets INTEGER,
    reps INTEGER,          -- set when type = 'Reps'
    time TEXT,             -- set when type = 'Time', e.g. '00:15'
    rest INTEGER,
    comments TEXT,
    phase TEXT,            -- 'Before' | 'During' | 'After'
    mandatory BOOLEAN DEFAULT FALSE,         -- always included in generated plans for its phase
    exclude_from_plan BOOLEAN DEFAULT FALSE  -- never included in generated plans
);

-- One row per logged (or scheduled) training session
CREATE TABLE climbing_training (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    date_entry TIMESTAMP,
    date DATE NOT NULL,
    category TEXT,          -- 'Strength' | 'Stamina' | 'Technique' | 'Free' | 'Rest'
    effort INTEGER,          -- 1-10, blank until the session is actually logged
    gym_grade TEXT,
    moonboard_grade TEXT,
    injured BOOLEAN DEFAULT FALSE,
    goal_id BIGINT REFERENCES goals(id) ON DELETE SET NULL  -- which plan (if any) generated this session
);

-- Many-to-many: which exercises belong to which session
CREATE TABLE training_exercises (
    training_id BIGINT REFERENCES climbing_training(id) ON DELETE CASCADE,
    exercise_id BIGINT REFERENCES exercise(id) ON DELETE CASCADE,
    PRIMARY KEY (training_id, exercise_id)
);

-- Many-to-many: which training categories an exercise is tagged for
CREATE TABLE exercise_categories (
    exercise_id BIGINT REFERENCES exercise(id) ON DELETE CASCADE,
    category TEXT NOT NULL,           -- 'Strength' | 'Stamina' | 'Technique' | 'Free'
    PRIMARY KEY (exercise_id, category)
);
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