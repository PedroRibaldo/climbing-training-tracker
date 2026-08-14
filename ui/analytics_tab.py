"""
The Analytics tab: effort trend, grade progression, category mix, ACWR,
effort-vs-grade yield, and peak session highlights over a selected range.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_pipeline import PipelineConfig, compute_acwr, get_peak_sessions
import theme
from . import components


def render(df_past, whoop_enabled=False, df_whoop=None):
    today_date = pd.to_datetime('today').date()
    last_month_date = today_date - pd.Timedelta(days=30)

    if 'analytics_date_range' not in st.session_state:
        st.session_state.analytics_date_range = (last_month_date, today_date)

    date_range = st.date_input(
        ":material/date_range: Select analytics date range",
        value=st.session_state.analytics_date_range,
        max_value=today_date
    )

    if len(date_range) == 2:
        st.session_state.analytics_date_range = date_range

    start_date, end_date = st.session_state.analytics_date_range

    # Rest days are excluded from analytics since they carry no effort/grade data
    mask = (df_past['date'].dt.date >= start_date) & (df_past['date'].dt.date <= end_date) & (df_past['category'] != 'Rest')
    df_analytics = df_past[mask].copy()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader(":material/local_fire_department: Training intensity")
        df_effort = df_analytics.dropna(subset=['effort']).sort_values(by='date')

        def _render_effort_chart():
            fig = px.line(df_effort, x='date', y='effort', markers=True, template=theme.PLOTLY_TEMPLATE)
            fig.update_traces(line_color=theme.ACCENT, marker=dict(color=theme.ACCENT, size=8))
            fig.update_yaxes(title="Effort (1-10)", range=[0, 10.5])
            fig.update_xaxes(title="", tickformat="%d/%m")
            st.plotly_chart(fig)

        components.chart_or_empty(not df_effort.empty, _render_effort_chart, "No effort data logged.")

    with col2:
        st.subheader(":material/trending_up: Grade progression")
        # -1 encodes "no grade logged that day" (see clean_data), so those rows are excluded here
        df_gym = df_analytics[df_analytics['gym_numeric'] != -1].sort_values(by='date')
        df_moonboard = df_analytics[df_analytics['moonboard_numeric'] != -1].sort_values(by='date')

        def _render_grade_chart():
            gym_rev_map = {v: k for k, v in PipelineConfig.GYM_MAPPING.items()}
            mb_rev_map = {v: k for k, v in PipelineConfig.MOONBOARD_MAPPING.items()}

            # Gym grade and Moonboard grade use different scales, so they
            # share the x-axis (date) but get independent y-axes
            fig_grades = make_subplots(specs=[[{"secondary_y": True}]])
            if not df_gym.empty:
                fig_grades.add_trace(go.Scatter(
                    x=df_gym['date'], y=df_gym['gym_numeric'], name='Gym Grade',
                    mode='lines+markers', marker=dict(symbol='square'),
                    line_color=theme.GRADE_COLORS["Blue"],
                ), secondary_y=False)
            if not df_moonboard.empty:
                fig_grades.add_trace(go.Scatter(
                    x=df_moonboard['date'], y=df_moonboard['moonboard_numeric'], name='Moonboard',
                    mode='lines+markers', marker=dict(symbol='triangle-up'),
                    line_color=theme.GRADE_COLORS["Purple"],
                ), secondary_y=True)

            fig_grades.update_layout(template=theme.PLOTLY_TEMPLATE, legend=dict(orientation='h', y=1.15))
            fig_grades.update_yaxes(
                title_text="Gym Color", secondary_y=False, color=theme.GRADE_COLORS["Blue"],
                tickvals=list(gym_rev_map.keys()), ticktext=list(gym_rev_map.values()),
            )
            fig_grades.update_yaxes(
                title_text="Moonboard (V)", secondary_y=True, color=theme.GRADE_COLORS["Purple"],
                tickvals=list(mb_rev_map.keys()), ticktext=list(mb_rev_map.values()),
            )
            fig_grades.update_xaxes(title="", tickformat="%d/%m")
            st.plotly_chart(fig_grades)

        components.chart_or_empty(not df_gym.empty or not df_moonboard.empty, _render_grade_chart, "No grade data logged.")

    with col3:
        st.subheader(":material/pie_chart: Distribution")
        df_dist = df_analytics[df_analytics['category'] != 'Rest']

        def _render_distribution_chart():
            category_counts = df_dist['category'].value_counts()
            fig_dist = px.pie(
                names=category_counts.index,
                values=category_counts.values,
                color=category_counts.index,
                color_discrete_map=theme.CATEGORY_COLORS,
                template=theme.PLOTLY_TEMPLATE,
            )
            fig_dist.update_traces(
                textinfo='percent+label',
                marker=dict(line=dict(color=theme.BASALT, width=1.5)),
            )
            st.plotly_chart(fig_dist)

        components.chart_or_empty(not df_dist.empty, _render_distribution_chart, "No training sessions logged.")

    st.subheader(":material/query_stats: Advanced analytics")

    col4, col5 = st.columns(2)

    with col4:
        st.markdown("**:material/monitoring: Acute:Chronic Workload Ratio**")
        # Computed over the full training history (not just the selected
        # range)
        acwr_df = compute_acwr(df_past)
        acwr_windowed = acwr_df[(acwr_df.index.date >= start_date) & (acwr_df.index.date <= end_date)]

        def _render_acwr_chart():
            band_top = max(2.0, acwr_windowed['acwr'].max(skipna=True) + 0.2)
            band_defs = [
                (0.8, 1.3, "sweet_spot", "Sweet spot"),
                (1.3, 1.5, "caution", "Caution"),
                (1.5, band_top, "high_risk", "High risk"),
            ]
            fig_acwr = go.Figure()
            for y0, y1, key, label in band_defs:
                fig_acwr.add_hrect(y0=y0, y1=y1, fillcolor=theme.ACWR_BAND_COLORS[key], opacity=0.15, line_width=0)
                fig_acwr.add_trace(go.Scatter(
                    x=[None], y=[None], mode='markers',
                    marker=dict(size=10, color=theme.ACWR_BAND_COLORS[key]), name=label,
                ))
            fig_acwr.add_trace(go.Scatter(
                x=acwr_windowed.index, y=acwr_windowed['acwr'], mode='lines+markers',
                line_color=theme.ACCENT, name='ACWR', showlegend=False,
            ))
            fig_acwr.update_layout(template=theme.PLOTLY_TEMPLATE, legend=dict(orientation='h', y=1.2, x=0))
            fig_acwr.update_yaxes(title="ACWR", range=[0, band_top])
            fig_acwr.update_xaxes(title="", type='date', tickformat="%d/%m")
            st.plotly_chart(fig_acwr)
            st.caption("Recent (7-day) vs. baseline (28-day) training load. Needs a few weeks of consistent logging to be meaningful.")

        components.chart_or_empty(
            not acwr_windowed.empty and acwr_windowed['acwr'].notna().any(),
            _render_acwr_chart,
            "Not enough training history yet to compute ACWR.",
        )

    with col5:
        st.markdown("**:material/scatter_plot: Effort vs. grade yield**")
        df_yield = df_analytics.dropna(subset=['effort'])
        df_gym_yield = df_yield[df_yield['gym_numeric'] != -1]
        df_mb_yield = df_yield[df_yield['moonboard_numeric'] != -1]

        def _render_yield_chart():
            fig_yield = go.Figure()
            if not df_gym_yield.empty:
                fig_yield.add_trace(go.Scatter(
                    x=df_gym_yield['effort'], y=df_gym_yield['gym_numeric'], mode='markers', name='Gym',
                    marker=dict(color=theme.GRADE_COLORS["Blue"], opacity=0.7),
                ))
            if not df_mb_yield.empty:
                fig_yield.add_trace(go.Scatter(
                    x=df_mb_yield['effort'], y=df_mb_yield['moonboard_numeric'], mode='markers', name='Moonboard',
                    marker=dict(color=theme.GRADE_COLORS["Purple"], opacity=0.7),
                ))
            fig_yield.update_layout(template=theme.PLOTLY_TEMPLATE, xaxis_title="Effort (1-10)", yaxis_title="Max grade (encoded)")
            st.plotly_chart(fig_yield)

        components.chart_or_empty(not df_gym_yield.empty or not df_mb_yield.empty, _render_yield_chart, "No grade data logged in this range.")

    st.markdown("**:material/emoji_events: Peak performance highlights**")
    top_sessions = get_peak_sessions(df_analytics, n=3)

    if not top_sessions.empty:
        gym_rev_map = {v: k for k, v in PipelineConfig.GYM_MAPPING.items()}
        mb_rev_map = {v: k for k, v in PipelineConfig.MOONBOARD_MAPPING.items()}
        highlight_cols = st.columns(len(top_sessions))

        for col, (_, session) in zip(highlight_cols, top_sessions.iterrows()):
            with col:
                st.markdown(f"**{session['date'].strftime('%d/%m/%Y')}**")
                st.caption(session['category'])
                if session['gym_numeric'] != -1:
                    st.markdown(f":material/terrain: Gym: {gym_rev_map.get(int(session['gym_numeric']), '-')}")
                if session['moonboard_numeric'] != -1:
                    st.markdown(f":material/grid_view: Moonboard: {mb_rev_map.get(int(session['moonboard_numeric']), '-')}")
                if pd.notna(session['effort']):
                    st.markdown(f":material/local_fire_department: Effort: {int(session['effort'])}/10")
    else:
        st.info("No sessions to highlight in this range yet.")

    if whoop_enabled and df_whoop is not None and not df_whoop.empty:
        whoop_mask = (df_whoop['date'].dt.date >= start_date) & (df_whoop['date'].dt.date <= end_date)
        df_whoop_range = df_whoop[whoop_mask].sort_values(by='date')

        st.subheader(":material/monitor_heart: WHOOP recovery trends")

        if not df_whoop_range.empty:
            col_hrv, col_strain, col_rhr = st.columns(3)

            with col_hrv:
                st.markdown("**HRV**")
                df_hrv = df_whoop_range.dropna(subset=['hrv_ms'])

                def _render_hrv_chart():
                    fig_hrv = px.line(df_hrv, x='date', y='hrv_ms', markers=True, template=theme.PLOTLY_TEMPLATE)
                    fig_hrv.update_traces(line_color=theme.GRADE_COLORS["Blue"], marker=dict(color=theme.GRADE_COLORS["Blue"]))
                    fig_hrv.update_yaxes(title="HRV (ms)")
                    fig_hrv.update_xaxes(title="", tickformat="%d/%m")
                    st.plotly_chart(fig_hrv)

                components.chart_or_empty(not df_hrv.empty, _render_hrv_chart, "No HRV data in this range.")

            with col_strain:
                st.markdown("**Strain**")
                df_strain = df_whoop_range.dropna(subset=['strain'])

                def _render_strain_chart():
                    fig_strain = px.line(df_strain, x='date', y='strain', markers=True, template=theme.PLOTLY_TEMPLATE)
                    fig_strain.update_traces(line_color=theme.GRADE_COLORS["Red"], marker=dict(color=theme.GRADE_COLORS["Red"]))
                    fig_strain.update_yaxes(title="Strain (0-21)", range=[0, 21])
                    fig_strain.update_xaxes(title="", tickformat="%d/%m")
                    st.plotly_chart(fig_strain)

                components.chart_or_empty(not df_strain.empty, _render_strain_chart, "No strain data in this range.")

            with col_rhr:
                st.markdown("**Resting HR**")
                df_rhr = df_whoop_range.dropna(subset=['resting_hr'])

                def _render_rhr_chart():
                    fig_rhr = px.line(df_rhr, x='date', y='resting_hr', markers=True, template=theme.PLOTLY_TEMPLATE)
                    fig_rhr.update_traces(line_color=theme.GRADE_COLORS["Green"], marker=dict(color=theme.GRADE_COLORS["Green"]))
                    fig_rhr.update_yaxes(title="Resting HR (bpm)")
                    fig_rhr.update_xaxes(title="", tickformat="%d/%m")
                    st.plotly_chart(fig_rhr)

                components.chart_or_empty(not df_rhr.empty, _render_rhr_chart, "No resting HR data in this range.")
        else:
            st.info("No WHOOP data logged in this range yet.")
