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


def render(df_past):
    today_date = pd.to_datetime('today').date()
    last_month_date = today_date - pd.Timedelta(days=30)

    date_range = st.date_input(
        ":material/date_range: Select analytics date range",
        value=(last_month_date, today_date),
        max_value=today_date
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        # Rest days are excluded from analytics since they carry no effort/grade data
        mask = (df_past['date'].dt.date >= start_date) & (df_past['date'].dt.date <= end_date) & (df_past['category'] != 'Rest')
        df_analytics = df_past[mask].copy()

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader(":material/local_fire_department: Training intensity")
            df_effort = df_analytics.dropna(subset=['effort']).sort_values(by='date')

            if not df_effort.empty:
                fig = px.line(df_effort, x='date', y='effort', markers=True, template=theme.PLOTLY_TEMPLATE)
                fig.update_traces(line_color=theme.ACCENT, marker=dict(color=theme.ACCENT, size=8))
                fig.update_yaxes(title="Effort (1-10)", range=[0, 10.5])
                fig.update_xaxes(title="", tickformat="%d/%m")
                st.plotly_chart(fig)
            else:
                st.info("No effort data logged.")

        with col2:
            st.subheader(":material/trending_up: Grade progression")
            # -1 encodes "no grade logged that day" (see clean_data), so those rows are excluded here
            df_gym = df_analytics[df_analytics['gym_numeric'] != -1].sort_values(by='date')
            df_moonboard = df_analytics[df_analytics['moonboard_numeric'] != -1].sort_values(by='date')

            if not df_gym.empty or not df_moonboard.empty:
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
            else:
                st.info("No grade data logged.")

        with col3:
            st.subheader(":material/pie_chart: Distribution")
            df_dist = df_analytics[df_analytics['category'] != 'Rest']

            if not df_dist.empty:
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
            else:
                st.info("No training sessions logged.")

        st.subheader(":material/query_stats: Advanced analytics")

        col4, col5 = st.columns(2)

        with col4:
            st.markdown("**:material/monitoring: Acute:Chronic Workload Ratio**")
            # Computed over the full training history (not just the selected
            # range)
            acwr_df = compute_acwr(df_past)
            acwr_windowed = acwr_df[(acwr_df.index.date >= start_date) & (acwr_df.index.date <= end_date)]

            if not acwr_windowed.empty and acwr_windowed['acwr'].notna().any():
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
            else:
                st.info("Not enough training history yet to compute ACWR.")

        with col5:
            st.markdown("**:material/scatter_plot: Effort vs. grade yield**")
            df_yield = df_analytics.dropna(subset=['effort'])
            df_gym_yield = df_yield[df_yield['gym_numeric'] != -1]
            df_mb_yield = df_yield[df_yield['moonboard_numeric'] != -1]

            if not df_gym_yield.empty or not df_mb_yield.empty:
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
            else:
                st.info("No grade data logged in this range.")

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
    else:
        st.warning("Please select an end date to view analytics.")
