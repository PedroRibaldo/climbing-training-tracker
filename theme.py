"""
Design tokens for the Climbing Training Tracker.

Single source of truth for every color, font, and chart template used
across app.py, so nothing is hardcoded inline more than once. The palette
is built around the gym's own grade-color scale (PipelineConfig.GYM_MAPPING)
so hold colors read the same way here as they do on the wall.
"""

import plotly.graph_objects as go

# --- Base palette ---
BASALT = "#1A1918"       # page background
CHALK_BAG = "#242220"    # card / surface background
ROPE = "#3A3733"         # borders, dividers
CHALK = "#EDE8DF"        # primary text
STONE = "#9C948A"        # secondary / muted text
ACCENT = "#E8B923"       # primary interactive color (chalk-tape yellow)

# --- Grade scale (mirrors PipelineConfig.GYM_MAPPING keys) ---
GRADE_COLORS = {
    "White": "#F5F1E8",
    "Yellow": "#E8B923",
    "Green": "#4C9A2A",
    "Blue": "#3E86D6",
    "Red": "#E0483A",
    "Purple": "#9B5DE0",
    "Black": "#4A4540",
}
DANGER = GRADE_COLORS["Red"]  # semantic alias for destructive actions (delete/abandon buttons)

# --- Training category colors (deliberately distinct from GRADE_COLORS) ---
CATEGORY_COLORS = {
    "Strength": "#E4622D",
    "Stamina": "#2FA89A",
    "Technique": "#C2437D",
    "Free": "#6C63FF",
    "Rest": "#6B6560",
}
CATEGORY_FALLBACK_COLOR = "#5A564F"

# --- ACWR risk bands (reuse the grade scale's green/yellow/red) ---
ACWR_BAND_COLORS = {
    "sweet_spot": GRADE_COLORS["Green"],
    "caution": GRADE_COLORS["Yellow"],
    "high_risk": GRADE_COLORS["Red"],
}

# --- Type ---
FONT_DISPLAY = "'Oswald', sans-serif"
FONT_BODY = "'Inter', sans-serif"
FONT_MONO = "'JetBrains Mono', monospace"

# --- Shared Plotly template ---
PLOTLY_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor=CHALK_BAG,
        plot_bgcolor=CHALK_BAG,
        font=dict(family=FONT_BODY, color=CHALK, size=13),
        title=dict(font=dict(family=FONT_DISPLAY, color=CHALK, size=18)),
        xaxis=dict(
            gridcolor=ROPE, zerolinecolor=ROPE, tickfont=dict(family=FONT_MONO, color=STONE),
            linecolor=ROPE,
        ),
        yaxis=dict(
            gridcolor=ROPE, zerolinecolor=ROPE, tickfont=dict(family=FONT_MONO, color=STONE),
            linecolor=ROPE,
        ),
        legend=dict(font=dict(family=FONT_BODY, color=CHALK), bgcolor="rgba(0,0,0,0)"),
        colorway=[ACCENT, GRADE_COLORS["Blue"], GRADE_COLORS["Purple"], GRADE_COLORS["Green"]],
        margin=dict(l=10, r=10, t=40, b=10),
    )
)


def color_key_html(colors: dict, title: str = "Color Key") -> str:
    """A small placard-style legend - circular swatches + labels - styled
    like the color-key sign posted on a real bouldering gym wall. Used to
    explain what a strip of colored chips/blocks means (e.g. the calendar's
    category colors)."""
    swatches = "".join(
        f'<span style="display:inline-flex; align-items:center; gap:0.4rem;">'
        f'<span style="width:11px; height:11px; border-radius:50%; background:{color}; '
        f'display:inline-block; box-shadow:0 0 0 1px {ROPE};"></span>'
        f'<span style="font-family:{FONT_BODY}; font-size:0.85rem; color:{CHALK};">{label}</span>'
        f'</span>'
        for label, color in colors.items()
    )
    return f"""
<div style="display:flex; align-items:center; gap:1.4rem; flex-wrap:wrap;
            padding:0.65rem 1rem; margin:0.4rem 0 1rem 0;
            background:{CHALK_BAG}; border:1px solid {ROPE}; border-radius:8px;">
    <span style="font-family:{FONT_MONO}; font-size:0.7rem; color:{STONE};
                 text-transform:uppercase; letter-spacing:0.08em;">{title}</span>
    {swatches}
</div>
"""


def phase_timeline_html(phase_breakdown: list, total_weeks: int, elapsed_weeks: float) -> str:
    """A horizontal bar showing each plan phase as a proportional colored
    segment, with a vertical marker at the current position."""
    phase_colors = {'Base': STONE, 'Build': ACCENT, 'Peak': GRADE_COLORS['Red']}
    segments = "".join(
        f'<div style="flex:{p["end_week"] - p["start_week"] + 1}; background:{phase_colors.get(p["name"], STONE)}; '
        f'padding:0.35rem 0; text-align:center; font-family:{FONT_MONO}; font-size:0.7rem; color:{BASALT};">{p["name"]}</div>'
        for p in phase_breakdown
    )
    marker_pct = max(0.0, min(1.0, elapsed_weeks / total_weeks)) * 100
    return f"""
<div style="position:relative; margin:0.6rem 0 1rem 0;">
  <div style="display:flex; border-radius:6px; overflow:hidden; border:1px solid {ROPE};">{segments}</div>
  <div style="position:absolute; top:-4px; left:{marker_pct:.1f}%; width:2px; height:calc(100% + 8px); background:{CHALK};"></div>
</div>
"""


def notification_bell_css(count: int) -> str:
    """Styles the header notification bell (Streamlit button key='notif_bell')
    as an icon with a small floating badge showing `count` overdue sessions -
    or dims it with no badge when there's nothing overdue. Returned HTML is
    meant to be passed straight to st.html()."""
    if count > 0:
        rules = f"""
        [class*="st-key-notif_bell"] button {{
            color: {ACCENT} !important;
            border-color: {ACCENT} !important;
            position: relative;
            overflow: visible !important;
        }}
        [class*="st-key-notif_bell"] button::after {{
            content: "{count}";
            position: absolute;
            top: -6px;
            right: -6px;
            background: {DANGER};
            color: {BASALT};
            font-family: {FONT_MONO};
            font-size: 0.65rem;
            font-weight: 700;
            min-width: 16px;
            height: 16px;
            padding: 0 3px;
            border-radius: 999px;
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
        }}
        """
    else:
        rules = f"""
        [class*="st-key-notif_bell"] button {{
            color: {STONE} !important;
            border-color: {ROPE} !important;
            opacity: 0.6;
        }}
        """
    return f"<style>{rules}</style>"


def calendar_css() -> str:
    """FullCalendar day-cell styling: centers the day number, tints event
    backgrounds, adds a hover affordance. Return value is meant to be
    passed straight to st.html().

    The min-height rule works around a Streamlit quirk: the calendar is a
    custom component that measures its own height and reports it back, but
    tab switches never rerun the script - so a rerun triggered while this
    tab is hidden (e.g. from the Goals tab) makes it measure a 0-height
    element and get stuck reporting 0 until a full page reload.
    """
    return f"""
<style>
.fc-daygrid-day-frame {{
    position: relative !important;
}}
.fc-daygrid-day-top {{
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 100% !important;
    z-index: 10 !important;
    margin-top: 0 !important;
}}
.fc-daygrid-day-number {{
    font-family: {FONT_MONO} !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: {CHALK} !important;
    text-shadow: 1px 1px 3px {BASALT}, -1px -1px 3px {BASALT} !important;
    text-decoration: none !important;
}}
.fc-daygrid-day-events {{
    pointer-events: none !important;
}}
.fc-bg-event {{
    opacity: 0.85 !important;
}}
.fc-daygrid-day-frame {{
    cursor: pointer;
}}
@media (prefers-reduced-motion: no-preference) {{
    .fc-daygrid-day-frame {{
        transition: filter 150ms ease;
    }}
    .fc-daygrid-day-frame:hover {{
        filter: brightness(1.15);
    }}
}}
iframe[data-testid="stCustomComponentV1"] {{
    min-height: 650px !important;
}}
</style>
"""


def inject_global_css() -> str:
    """Google Fonts import + base typography/spacing rules for the app.
    Return value is meant to be passed straight to st.html().
    """
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {{
    font-family: {FONT_BODY};
}}

h1, h2, h3 {{
    font-family: {FONT_DISPLAY} !important;
    letter-spacing: 0.02em;
    text-transform: uppercase;
}}

[data-testid="stMetricValue"] {{
    font-family: {FONT_MONO} !important;
}}

[data-testid="stMetricLabel"] {{
    font-family: {FONT_BODY} !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.75rem !important;
}}

.stTabs [data-baseweb="tab"] {{
    font-family: {FONT_DISPLAY};
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}

code, .stCode, .grade-chip-label {{
    font-family: {FONT_MONO} !important;
}}

/* Destructive actions - buttons keyed "danger_*" (see app.py) get a red
   outline that fills solid on hover/press, keeping delete/abandon actions
   visually distinct from primary and neutral actions without shouting. */
[class*="st-key-danger_"] button {{
    color: {DANGER} !important;
    border-color: {DANGER} !important;
}}
[class*="st-key-danger_"] button:hover,
[class*="st-key-danger_"] button:focus-visible {{
    color: {BASALT} !important;
    background-color: {DANGER} !important;
    border-color: {DANGER} !important;
}}

@media (prefers-reduced-motion: no-preference) {{
    .stButton button {{
        transition: background-color 150ms ease, border-color 150ms ease, color 150ms ease, transform 100ms ease;
    }}
    .stButton button:active {{
        transform: scale(0.97);
    }}
}}
</style>
"""
