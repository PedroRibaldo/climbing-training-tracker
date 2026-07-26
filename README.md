# 🧗 Climbing Training Tracker

A personal climbing training dashboard built with **Streamlit**, backed by a **Google Form + Google Sheets** logging workflow. Log training sessions from your phone via a Google Form, then review progress, edit past sessions, and explore analytics in an interactive web dashboard.

![Python](https://img.shields.io/badge/python-3.10%2B-blue
)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **📅 Training calendar** - sessions color-coded by category (Strength, Stamina, Technique, Free, Rest) on the calendar grid.
- **✏️ Click-to-edit sessions** - click any logged day to edit effort, grades, or exercises, or click a blank day to log a missed session.
- **📈 Analytics dashboard** - effort trend, gym/Moonboard grade progression, and training category distribution over any custom date range.
- **🔄 Two-way sync with Google Sheets** - reads from and writes back to the same spreadsheet your Google Form feeds into, so no data ever lives in two places.

---

## Data Architecture
📱 **Google Form** (Mobile Entry) ➔ 🗄️ **Google Sheets** (Relational DB) ➔ 🐍 **Pandas/gspread** (Data Pipeline) ➔ 📊 **Streamlit** (Web UI)

---

## Tech Stack

| Layer            | Tool                                              |
|-------------------|----------------------------------------------------|
| Dashboard / UI    | [Streamlit](https://streamlit.io) + [streamlit-calendar](https://github.com/im-perativa/streamlit-calendar) |
| Data processing   | pandas, numpy                                     |
| Charts            | matplotlib, seaborn                               |
| Data source       | Google Forms + Google Sheets (via [gspread](https://docs.gspread.org)) |

---

## Project Structure

```
.
├── app.py               # Streamlit dashboard (calendar + analytics)
├── data_pipeline.py      # Google Sheets I/O and data cleaning logic
├── requirements.txt       # Python dependencies
└── credentials.json       # Google service account key (not committed - see setup)
```

---

## Prerequisites

- Python 3.10+
- A Google account
- A Google Form + Google Sheet already set up to collect training sessions (see [Spreadsheet Setup](#spreadsheet-setup) below if you're starting from scratch)

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

---

## Spreadsheet Setup

The app expects your Google Sheet to contain two worksheets:

### `Main_Log`
Populated by your Google Form responses (one row per submitted session). Expected columns:

| Column                  | Description                                  |
|---------------------------|-----------------------------------------------|
| `Carimbo de data/hora`    | Form submission timestamp (auto-filled)        |
| `Date`                    | Date of the training session (DD/MM/YYYY)      |
| `Category`                | Strength / Stamina / Technique / Free / Rest   |
| `Effort Scale`            | Perceived effort, 1-10                         |
| `Max Gym Grade Color`     | Highest gym grade climbed (color scale)        |
| `Max Moonboard Grade`     | Highest Moonboard grade climbed (V-scale)      |
| `Injuries / Tweaks`       | Yes / No                                       |
| `Exercises`               | Comma-separated list of exercises performed    |

### `Exercise_Dictionary`
A reference table of exercises available for selection in the dashboard's "Add exercise" dropdown. Expected columns:

| Column       | Description                        |
|---------------|--------------------------------------|
| `Name`         | Exercise name                       |
| `Type`         | Reps/Time                           |
| `Sets`         | How many Sets (1-5)                 |
| `Reps/Time`    | Number of reps or time (mm:ss)      |
| `Rest`         | In minutes (1-5)                    |
| `Comments`     | Use "-" for no comments             |

---

## Roadmap

- [ ] Add [Pydantic](https://docs.pydantic.dev) models to validate row schemas coming from Google Sheets before they're processed.
- [ ] Add automated tests for the data cleaning logic in `data_pipeline.py`.
- [ ] Change Google Form to android widget with google sheets Apps Script.
- [x] Deploy to Streamlit Community Cloud.

---

## License

This project is licensed under the [MIT License](LICENSE).