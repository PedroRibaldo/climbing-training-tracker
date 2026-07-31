# 🧗 Climbing Training Tracker

A personal climbing training dashboard built with **Streamlit** and backed by **Supabase (Postgres)**. Log a session in seconds from an Android home screen widget, or from the dashboard itself. Review progress, catch up on anything you forgot to log, and dig into sports-science-grade analytics like training load trend and peak-session highlights.

![Python](https://img.shields.io/badge/python-3.10%2B-blue
)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![Supabase](https://img.shields.io/badge/database-Supabase-3ECF8E)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

**Logging**
- **One-tap mobile logging** - two Android home screen widgets log a session or register a new exercise.
- **Click-to-edit sessions** - click any day on the calendar to edit or log a missed session.
- **Before / During / After exercise phasing** - warm-up, climbing, and cool-down exercises live in their own tabs within each session, pulled from Exercise Library.
- **Smart defaults** - logging a new session pre-fills the usual warm-up and cool-down from the most recent session.
- **Catch-up carousel** - on load, any past session that never got its effort filled in pops up automatically.

**Exercise Library**
- Browse exercises grouped by phase; click one to edit or delete it.
- A dedicated "Add Exercise" modal checks for an existing name before creating a duplicate.

**Analytics**
- Color-coded training calendar (Strength / Stamina / Technique / Free / Rest).
- Effort trend and gym/Moonboard grade progression over a custom date range.
- **Acute:Chronic Workload Ratio (ACWR)** - flags whether recent training load is in a sustainable range or ramping into higher-injury-risk territory.
- **Effort vs. Grade Yield** - relates perceived effort to the grades actually achieved.
- **Peak Performance Highlights** - the top 3 strongest sessions in any selected range.

---

## Data Architecture

📱 **Android widgets** (HTTP Request Shortcuts) ➔ ⚙️ **Google Apps Script** (bridge) ➔ 🗄️ **Supabase** (Postgres) ➔ 🐍 **Pandas + Pydantic** (validation & cleaning) ➔ 📊 **Streamlit** (dashboard)

---

## Tech Stack

| Layer                   | Tool                                                                                                        |
|-------------------------|-------------------------------------------------------------------------------------------------------------|
| Dashboard / UI          | [Streamlit](https://streamlit.io) + [streamlit-calendar](https://github.com/im-perativa/streamlit-calendar) |
| Data validation         | [Pydantic](https://docs.pydantic.dev)                                                                       |
| Data processing         | pandas, numpy                                                                                               |
| Charts                  | matplotlib, seaborn                                                                                         |
| Database                | [Supabase](https://supabase.com) (Postgres) via [supabase-py](https://github.com/supabase/supabase-py)      |
| Mobile data entry       | [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch) (Android) → Google Apps Script → Supabase REST API  |

---

## Project Structure

```
.
├── app.py                     # Streamlit dashboard: calendar, exercise library, analytics
├── data_pipeline.py           # Supabase I/O, Pydantic validation, data cleaning, and analytics functions
├── Script.gs                  # Apps Script bridge: mobile widgets → Supabase REST API
├── tests/
│   └── test_data_pipeline.py  # pytest suite for validation, cleaning, and analytics logic
├── requirements.txt           # Python dependencies
├── requirements-dev.txt       # Adds pytest, for running the test suite
└── .env                       # Local Supabase credentials
```

---

## Prerequisites

- Python 3.10+
- A free [Supabase](https://supabase.com) account
- An Android phone with [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch) installed (only needed for mobile logging - the dashboard's own modals work standalone)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/PedroRibaldo/climbing-training-tracker.git
cd climbing-training-tracker
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Provision the database

1. Create a new project at [supabase.com](https://supabase.com) (the free tier is plenty for personal use).
2. Open the **SQL Editor** and run the schema below (also see [Database Schema](#database-schema) for what each column means).
3. Go to **Connect** and note your **`NEXT_PUBLIC_SUPABASE_URL`** and **`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` key**.

### 4. Configure credentials

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

### 5. Run the app

```bash
streamlit run app.py
```

The dashboard opens automatically at `http://localhost:8501`.

### 6. Set up mobile logging (optional)

Sessions and new exercises can be logged from an Android home screen instead of through the dashboard, using `Script.gs` as a small bridge between the widgets and Supabase's REST API.

1. In Supabase, go to **Connect** and copy your Project URL and key (same ones from step 3).
2. Create a new Google Sheet (used only to host the Apps Script), go to **Extensions → Apps Script**, and paste in the contents of `Script.gs`.
3. Under **Project Settings → Script Properties**, add three properties:
   - `API_TOKEN` - a long random string you generate once; this is the shared secret the widgets send to authenticate.
   - `SUPABASE_URL` - your Supabase Project URL.
   - `SUPABASE_KEY` - your Supabase key.
4. Deploy via **Deploy → New deployment → Web app**, with **Execute as: Me** and **Who has access: Anyone**, then copy the deployment URL.
5. In [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch), create two shortcuts pointed at that URL:
   - **Log Session** → POST to `<deployment-url>?action=log_session`
   - **Add Exercise** → POST to `<deployment-url>?action=add_exercise`

   Each shortcut sends a JSON body with the relevant fields (see the docstrings in `Script.gs` for exactly what each action expects) plus the `token` value from step 3.
6. Add both shortcuts to your home screen as widgets.

> ⚠️ Apps Script web apps can't read custom request headers, so access control relies entirely on the `API_TOKEN` value inside the JSON body - keep it private, and treat the deployment URL as a secret.

---

## Database Schema

Three tables - a session can reference any number of exercises without repeating data.

```sql
-- Reference table of exercises
CREATE TABLE exercise (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    name TEXT UNIQUE NOT NULL,
    type TEXT,            -- 'Reps' | 'Time'
    sets INTEGER,
    reps INTEGER,         -- set when type = 'Reps'
    time TEXT,            -- set when type = 'Time', e.g. '00:15'
    rest INTEGER,
    comments TEXT,
    phase TEXT            -- 'Before' | 'During' | 'After'
);

-- One row per logged (or scheduled) training session
CREATE TABLE climbing_training (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    date_entry TIMESTAMP,
    date DATE NOT NULL,
    category TEXT,        -- 'Strength' | 'Stamina' | 'Technique' | 'Free' | 'Rest'
    effort INTEGER,        -- 1-10, blank until the session is actually logged
    gym_grade TEXT,
    moonboard_grade TEXT,
    injured BOOLEAN DEFAULT FALSE
);

-- Many-to-many: which exercises belong to which session
CREATE TABLE training_exercises (
    training_id BIGINT REFERENCES climbing_training(id) ON DELETE CASCADE,
    exercise_id BIGINT REFERENCES exercise(id) ON DELETE CASCADE,
    PRIMARY KEY (training_id, exercise_id)
);
```

Every row fetched from Supabase is validated with [Pydantic](https://docs.pydantic.dev) before it reaches the dashboard. Validation is enforced at the application layer.

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Covers row validation (valid and deliberately invalid rows for both tables), the past/future session split, and the analytics functions (`compute_acwr`, `get_peak_sessions`) against hand-built edge cases.

---

## License

This project is licensed under the [MIT License](LICENSE).