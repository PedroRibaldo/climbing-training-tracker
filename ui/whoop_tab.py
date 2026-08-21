"""
The Whoop tab: HRV, strain, and resting heart rate trends over a selected
date range. Only rendered when the WHOOP sidebar toggle is enabled.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import theme
from . import components


def render(df_whoop, df_whoop_workouts):
    if df_whoop.empty:
        st.info("No WHOOP data logged yet.", icon=":material/info:")
        return

    today_date = pd.to_datetime('today').date()
    last_month_date = today_date - pd.Timedelta(days=30)

    if 'whoop_date_range' not in st.session_state:
        st.session_state.whoop_date_range = (last_month_date, today_date)

    date_range = st.date_input(
        ":material/date_range: Select Whoop date range",
        value=st.session_state.whoop_date_range,
        max_value=today_date
    )

    if len(date_range) == 2:
        st.session_state.whoop_date_range = date_range

    start_date, end_date = st.session_state.whoop_date_range

    whoop_mask = (df_whoop['date'].dt.date >= start_date) & (df_whoop['date'].dt.date <= end_date)
    df_whoop_range = df_whoop[whoop_mask].sort_values(by='date')

    if df_whoop_range.empty:
        st.info("No WHOOP data logged in this range yet.", icon=":material/info:")
        return

    col_hrv, col_strain, col_rhr = st.columns(3)

    with col_hrv:
        st.markdown("**HRV**")
        df_hrv = df_whoop_range.dropna(subset=['hrv_ms'])

        def _render_hrv_chart():
            fig_hrv = px.line(df_hrv, x='date', y='hrv_ms', markers=True, template=theme.PLOTLY_TEMPLATE)
            fig_hrv.update_traces(line_color=theme.GRADE_COLORS["Blue"], marker=dict(color=theme.GRADE_COLORS["Blue"]))
            fig_hrv.update_yaxes(title="HRV (ms)")
            fig_hrv.update_xaxes(title="", tickformat="%d/%m")
            components.render_chart(fig_hrv)

        components.chart_or_empty(not df_hrv.empty, _render_hrv_chart, "No HRV data in this range.")

    with col_strain:
        st.markdown("**Strain**")
        df_strain = df_whoop_range.dropna(subset=['strain'])

        def _render_strain_chart():
            fig_strain = px.line(df_strain, x='date', y='strain', markers=True, template=theme.PLOTLY_TEMPLATE)
            fig_strain.update_traces(line_color=theme.GRADE_COLORS["Red"], marker=dict(color=theme.GRADE_COLORS["Red"]))
            fig_strain.update_yaxes(title="Strain (0-21)", range=[0, 21])
            fig_strain.update_xaxes(title="", tickformat="%d/%m")
            components.render_chart(fig_strain)

        components.chart_or_empty(not df_strain.empty, _render_strain_chart, "No strain data in this range.")

    with col_rhr:
        st.markdown("**Resting HR**")
        df_rhr = df_whoop_range.dropna(subset=['resting_hr'])

        def _render_rhr_chart():
            fig_rhr = px.line(df_rhr, x='date', y='resting_hr', markers=True, template=theme.PLOTLY_TEMPLATE)
            fig_rhr.update_traces(line_color=theme.GRADE_COLORS["Green"], marker=dict(color=theme.GRADE_COLORS["Green"]))
            fig_rhr.update_yaxes(title="Resting HR (bpm)")
            fig_rhr.update_xaxes(title="", tickformat="%d/%m")
            components.render_chart(fig_rhr)

        components.chart_or_empty(not df_rhr.empty, _render_rhr_chart, "No resting HR data in this range.")

    workouts_mask = (df_whoop_workouts['date'].dt.date >= start_date) & (df_whoop_workouts['date'].dt.date <= end_date) if not df_whoop_workouts.empty else pd.Series(dtype=bool)
    df_workouts_range = df_whoop_workouts[workouts_mask].sort_values(by='date') if not df_whoop_workouts.empty else df_whoop_workouts

    col_zones, col_calories = st.columns(2)

    with col_zones:
        st.markdown("**HR zone breakdown**")

        def _render_zone_chart():
            zone_labels = ["Zone 0", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"]
            zone_colors = [
                theme.STONE, theme.GRADE_COLORS["Blue"], theme.GRADE_COLORS["Green"],
                theme.GRADE_COLORS["Yellow"], theme.GRADE_COLORS["Red"], theme.GRADE_COLORS["Purple"],
            ]
            fig_zones = go.Figure()
            for n, (label, color) in enumerate(zip(zone_labels, zone_colors)):
                fig_zones.add_trace(go.Bar(
                    x=df_workouts_range['date'], y=df_workouts_range[f'zone_{n}_min'], name=label,
                    marker=dict(color=color), hovertemplate=f"{label}: %{{y:.0f}} min<extra></extra>",
                ))
            fig_zones.update_layout(template=theme.PLOTLY_TEMPLATE, barmode='stack')
            fig_zones.update_yaxes(title="Minutes")
            fig_zones.update_xaxes(title="", tickformat="%d/%m")
            components.render_chart(fig_zones)

        components.chart_or_empty(not df_workouts_range.empty, _render_zone_chart, "No climbing workouts logged in this range.")

    with col_calories:
        st.markdown("**Calories**")

        def _render_calories_chart():
            fig_calories = px.bar(df_workouts_range, x='date', y='calories', template=theme.PLOTLY_TEMPLATE)
            fig_calories.update_traces(marker_color=theme.ACCENT)
            fig_calories.update_yaxes(title="Calories")
            fig_calories.update_xaxes(title="", tickformat="%d/%m")
            components.render_chart(fig_calories)

        components.chart_or_empty(not df_workouts_range.empty, _render_calories_chart, "No climbing workouts logged in this range.")

    st.markdown("**Avg / Max heart rate**")
    df_hr = df_workouts_range.dropna(subset=['avg_hr', 'max_hr'])

    def _render_hr_chart():
        fig_hr = go.Figure()
        fig_hr.add_trace(go.Scatter(
            x=df_hr['date'], y=df_hr['avg_hr'], mode='lines+markers',
            name='Avg HR', line=dict(color=theme.GRADE_COLORS["Blue"]), marker=dict(color=theme.GRADE_COLORS["Blue"]),
        ))
        fig_hr.add_trace(go.Scatter(
            x=df_hr['date'], y=df_hr['max_hr'], mode='lines+markers',
            name='Max HR', line=dict(color=theme.GRADE_COLORS["Red"]), marker=dict(color=theme.GRADE_COLORS["Red"]),
        ))
        fig_hr.update_layout(template=theme.PLOTLY_TEMPLATE)
        fig_hr.update_yaxes(title="Heart rate (bpm)")
        fig_hr.update_xaxes(title="", tickformat="%d/%m")
        components.render_chart(fig_hr)

    components.chart_or_empty(not df_hr.empty, _render_hr_chart, "No heart rate data in this range.")
