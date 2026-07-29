# 🧗 Climbing Training Tracker

A personal climbing training dashboard built with **Streamlit**, backed by a **Google Form + Google Sheets** logging workflow. Log training sessions from your phone via a pair of custom Android home screen widgets, then review progress, edit past sessions, and explore analytics in an interactive web dashboard.

![Python](https://img.shields.io/badge/python-3.10%2B-blue
)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **📅 Training calendar** - sessions color-coded by category (Strength, Stamina, Technique, Free, Rest) on the calendar grid.
- **✏️ Click-to-edit sessions** - click any logged day to edit effort, grades, or exercises, or click a blank day to log a missed session.
- **🏋️ Exercise Library editor** - add, edit, or delete exercises in an Excel-like grid.
- **📈 Analytics dashboard** - effort trend, gym/Moonboard grade progression, and training category distribution over any custom date range.
- **📉 Training load tracking** - Acute:Chronic Workload Ratio (ACWR) chart flags whether recent training load is in a sustainable range or ramping into higher-injury-risk territory.
- **🎯 Effort vs. Grade** - scatterplot relating perceived effort to the grades actually achieved, gym and Moonboard.
- **🏆 Peak Performance Highlights** - surfaces top 3 strongest sessions in any selected date range.
- **📱 One-tap mobile logging** - two Android home screen widgets log a session or register a new exercise directly into the spreadsheet.
- **🔄 Two-way sync with Google Sheets** - reads from and writes back to the same spreadsheet your Google Form feeds into, so no data ever lives in two places.

---

## Data Architecture
📱 **Android widgets** (HTTP Request Shortcuts) ➔ ⚙️ **Google Apps Script** (Web App) ➔ 🗄️ **Google Sheets** (Relational DB) ➔ 🐍 **Pandas/gspread** (Data Pipeline) ➔ 📊 **Streamlit** (Web UI)

---

## Tech Stack

| Layer            | Tool                                              |
|-------------------|----------------------------------------------------|
| Dashboard / UI    | [Streamlit](https://streamlit.io) + [streamlit-calendar](https://github.com/im-perativa/streamlit-calendar) |
| Data processing   | pandas, numpy                                     |
| Charts            | matplotlib, seaborn                               |
| Mobile data entry    | [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch) (Android) → Google Apps Script Web App |
| Data source       | Google Forms + Google Sheets (via [gspread](https://docs.gspread.org)) |

---

## Project Structure

```
.
├── app.py                    # Streamlit dashboard (calendar + analytics)
├── data_pipeline.py          # Google Sheets I/O and data cleaning logic
├── Script.gs                 # Apps Script Web App backend (mobile widget endpoint)
├── tests/
│   └── test_data_pipeline.py # pytest suite for the validation/cleaning logic
├── requirements.txt          # Python dependencies
├── requirements-dev.txt      # Adds pytest, for running the test suite
└── credentials.json          # Google service account key (not committed - see setup)
```

---

## Prerequisites

- Python 3.10+
- A Google account
- A Google Sheet with `Main_Log` and `Exercise_Dictionary` worksheets Sheet already set up (see [Spreadsheet Setup](#spreadsheet-setup) below if you're starting from scratch)
- An Android phone with [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch) installed (only needed if you want to log sessions from your phone, rather than through the dashboard's own edit modal)

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

### 3. Set up Google API credentials

The app authenticates to Google Sheets using a **service account**, not your personal Google login.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or reuse an existing one).
2. Enable the **Google Sheets API** and **Google Drive API** for that project.
3. Go to **APIs & Services → Credentials → Create Credentials → Service Account**.
4. Once created, open the service account, go to **Keys → Add Key → Create new key → JSON**, and download it.
5. Rename the downloaded file to `credentials.json` and place it in the project root.
6. Open your Google Sheet, click **Share**, and give the service account's email address (found inside `credentials.json`, field `client_email`) **Editor** access.

> ⚠️ `credentials.json` contains a private key. Never commit it to version control - it's already excluded via `.gitignore`.

### 4. Configure the spreadsheet name

By default, the app looks for a spreadsheet named `Climbing Tracker`. If yours is named differently, update `SPREADSHEET_NAME` in `data_pipeline.py`:

```python
class PipelineConfig:
    SPREADSHEET_NAME = 'Climbing Tracker'
```

### 5. Run the app

```bash
streamlit run app.py
```

The dashboard will open automatically in your browser at `http://localhost:8501`.

### 6. Cloud Deployment (Streamlit Community Cloud)
To deploy this dashboard live:
1. Push your code to a public GitHub repository (ensuring `credentials.json` is git-ignored).
2. Connect the repository to Streamlit Community Cloud.
3. In the Streamlit deployment **Advanced Settings**, paste the contents of your `credentials.json` into the Secrets manager under a `[gcp_service_account]` header.

### 7. Set up mobile logging (optional)
 
Sessions and new exercises can be logged from an Android home screen instead of through the dashboard, using `Script.gs` as a small JSON API in front of the spreadsheet.
 
1. Open your Google Sheet, go to **Extensions → Apps Script**, and paste in the contents of `Script.gs`.
2. Under **Project Settings → Script Properties**, add a property named `API_TOKEN` with a long random string as its value - this is the shared secret the widgets will send to authenticate.
3. Deploy via **Deploy → New deployment → Web app**, with **Execute as: Me** and **Who has access: Anyone**, then copy the deployment URL.
4. In the [HTTP Request Shortcuts](https://http-shortcuts.rmy.ch) app, create two shortcuts pointed at that URL:
   - **Log Session** → POST to `<deployment-url>?action=log_session`
   - **Add Exercise** → POST to `<deployment-url>?action=add_exercise`
   Each shortcut sends a JSON body with the relevant fields (see the docstrings in `Script.gs` for the exact fields each action expects) plus the `token` value from step 2.
5. Add both shortcuts to your home screen as widgets.
> ⚠️ Because Apps Script web apps can't read custom request headers, access control relies entirely on the `API_TOKEN` value inside the JSON body - keep it private, and treat the deployment URL as a secret.
 
---

## Spreadsheet Setup

The app expects your Google Sheet to contain two worksheets:

### `Main_Log`
Populated by your Google Form responses (one row per submitted session). Expected columns:

| Column                    | Description                                    |
|---------------------------|------------------------------------------------|
| `Carimbo de data/hora`    | Form submission timestamp (auto-filled)        |
| `Date`                    | Date of the training session (DD/MM/YYYY)      |
| `Category`                | Strength / Stamina / Technique / Free / Rest   |
| `Effort Scale`            | Perceived effort, 1-10                         |
| `Max Gym Grade Color`     | Highest gym grade climbed (color scale)        |
| `Max Moonboard Grade`     | Highest Moonboard grade climbed (V-scale)      |
| `Injuries / Tweaks`       | Yes / No                                       |
| `Exercises`               | Comma-separated list of exercises performed    |

### `Exercise_Dictionary`
Populated by the **Add Exercise** widget. A reference table of exercises available for selection in the dashboard's "Add exercise" dropdown. Expected columns:

| Column       | Description                        |
|---------------|--------------------------------------|
| `Name`         | Exercise name                       |
| `Type`         | Reps/Time                           |
| `Sets`         | How many Sets                       |
| `Reps/Time`    | Number of reps or time (mm:ss)      |
| `Rest`         | Number in minutes                   |
| `Comments`     | Use "-" for no comments             |
| `Phase`        | Before / During / After             |

### Data validation

Every row fetched from either worksheet is validated (via [Pydantic](https://docs.pydantic.dev)) before it reaches the dashboard - wrong types, typo'd grades/categories, or a missing date get that row skipped rather than crashing the app.

---

## Roadmap

- [x] Add [Pydantic](https://docs.pydantic.dev) models to validate row schemas coming from Google Sheets before they're processed.
- [x] Exercise Dictionary CRUD screen in the dashboard (`st.data_editor`).
- [x] Add automated tests for the data cleaning logic in `data_pipeline.py`.
- [x] Change Google Form to android widget with google sheets Apps Script.
- [x] Deploy to Streamlit Community Cloud.

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

---

## License

This project is licensed under the [MIT License](LICENSE).