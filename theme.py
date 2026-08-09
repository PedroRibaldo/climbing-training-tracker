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


def inject_global_css() -> str:
    """Google Fonts import + base typography/spacing rules for the app.
    Return value is meant to be passed straight to st.markdown(unsafe_allow_html=True).
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
</style>
"""
