"""
The Whoop tab: HRV, strain, and resting heart rate trends over a selected
date range. Only rendered when the WHOOP sidebar toggle is enabled.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

import theme
from . import components


def render(df_whoop):
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
