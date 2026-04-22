"""
pages/dashboard.py — LabVault Dashboard
Overview of all KPIs, sample status, OOS alerts, and recent audit activity.
"""

import streamlit as st
import pandas as pd
from db import (
    get_recent_samples, get_oos_results, get_audit_trail,
    count_samples_by_status, count_samples_by_priority, count_oos_results
)


def show():
    user = st.session_state.user

    # Header bar — uses the .lv-header CSS class defined in app.py.
    # We inject the username and today's date to make it feel personalized.
    st.markdown(f"""
        <div class="lv-header">
            <div>
                <h1>📊 Dashboard</h1>
                <span>Welcome back, {user['username']} — {pd.Timestamp.now().strftime('%A, %B %d %Y')}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # These are targeted queries — we only fetch exactly what this page needs.
    # No point loading 100 full sample rows when the dashboard just needs 8 cards
    # and a few aggregate counts. Each function has its own cache, too.
    samples      = get_recent_samples(8)        # 8 rows, 6 columns only
    oos_results  = get_oos_results(10)          # OOS rows straight from SQL, not filtered in Python
    status_map   = count_samples_by_status()    # {"Pending": 12, "Completed": 45, ...}
    priority_map = count_samples_by_priority()  # {"Critical": 5, "Major": 30, ...}
    oos_count    = count_oos_results()          # single integer — COUNT(*) query
    audit        = get_audit_trail(limit=8)     # 8 most recent log entries

    # Pull individual status counts out of the map — default to 0 if missing
    total       = len(samples)
    pending     = status_map.get("Pending", 0)
    in_progress = status_map.get("In Progress", 0)
    completed   = status_map.get("Completed", 0)

    # If the database is empty, nudge the admin to import data rather than
    # just showing a confusing blank dashboard
    if total == 0:
        st.warning("📭 No samples loaded yet. Click **🔄 Import FDA Data** in the sidebar to get started.")
        st.markdown("---")

    # ── KPI METRICS ─────────────────────────────────────────
    st.markdown("### Key Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Samples",  total)
    c2.metric("Pending",        pending)
    c3.metric("In Progress",    in_progress)
    c4.metric("Completed",      completed)
    # The OOS metric uses delta_color="inverse" so Streamlit shows it in red
    # when there are failures — "inverse" flips the normal green/red convention.
    c5.metric("⚠️ OOS Results", oos_count,
              delta="Requires review" if oos_count > 0 else "None",
              delta_color="inverse" if oos_count > 0 else "off")

    st.markdown("---")

    # ── CHARTS ───────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Sample Status Distribution")
        if status_map:
            # pd.DataFrame from a plain dict creates a single-column DataFrame
            # with the dict keys as the index — exactly what st.bar_chart wants.
            st.bar_chart(pd.DataFrame({"Count": status_map}), color="#1a4a8a")
        else:
            st.info("No sample data yet.")

    with col_right:
        st.markdown("#### Priority Breakdown")
        if priority_map:
            st.bar_chart(pd.DataFrame({"Count": priority_map}))
        else:
            st.info("No priority data yet.")

    st.markdown("---")

    # ── OOS ALERTS ───────────────────────────────────────────
    # Only render this section if there's actually something to flag —
    # no point showing an empty "OOS Alerts" header to worry the user.
    if oos_results:
        st.markdown("#### 🚨 Out-of-Spec (OOS) Alerts")
        st.error(f"{oos_count} result(s) flagged as Out-of-Spec — review required.")
        oos_df = pd.DataFrame(oos_results)
        # Rename columns to something readable — the DB column names aren't user-friendly
        oos_df.columns = ["Sample ID", "Test", "Result", "Unit",
                          "Spec Min", "Spec Max", "Tested By", "Date"]
        st.dataframe(oos_df, use_container_width=True, hide_index=True)
        st.markdown("---")

    # ── RECENT SAMPLES + AUDIT FEED ──────────────────────────
    col_samples, col_audit = st.columns(2)

    with col_samples:
        st.markdown("#### 🧫 Recent Samples")
        if samples:
            for s in samples:
                # Map each status/priority to its CSS badge class.
                # .get() with a default means unknown statuses still get styled.
                badge_class = {
                    "Pending":     "badge-pending",
                    "In Progress": "badge-progress",
                    "Completed":   "badge-completed",
                    "Rejected":    "badge-rejected",
                }.get(s.get("status"), "badge-pending")
                priority_class = {
                    "Critical": "badge-critical",
                    "Major":    "badge-major",
                    "Minor":    "badge-minor",
                }.get(s.get("priority"), "badge-major")
                name = s.get("product_name", "")
                # Truncate long product names so the card doesn't overflow
                st.markdown(f"""
                    <div style="background:white;border-radius:8px;padding:10px 14px;
                                margin-bottom:8px;border-left:4px solid #1a4a8a;
                                box-shadow:0 1px 4px rgba(0,0,0,0.06)">
                        <div style="font-weight:600;font-size:13px;color:#0f2942">
                            {s['sample_id']}
                            <span class="badge {priority_class}" style="margin-left:6px">{s.get('priority','—')}</span>
                            <span class="badge {badge_class}" style="margin-left:4px">{s.get('status','—')}</span>
                        </div>
                        <div style="font-size:12px;color:#555;margin-top:3px">
                            {name[:60]}{'...' if len(name) > 60 else ''}
                        </div>
                        <div style="font-size:11px;color:#888;margin-top:2px">
                            {s.get('manufacturer','—')} · {s.get('assigned_to','—')}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No samples yet — import FDA data from the sidebar.")

    with col_audit:
        st.markdown("#### 🕵️ Recent Activity")
        if audit:
            # Each action type gets a different emoji — quick visual scanning
            icons = {
                "SAMPLE_IMPORTED":  "📥",
                "SAMPLE_CREATED":   "🆕",
                "STATUS_UPDATED":   "🔄",
                "SAMPLE_ASSIGNED":  "👤",
                "RESULT_LOGGED":    "📋",
                "PROTOCOL_CREATED": "📄",
                "REPORT_EXPORTED":  "📊",
            }
            for e in audit:
                icon   = icons.get(e.get("action", ""), "📌")  # 📌 as fallback for unknown actions
                detail = (e.get("detail") or "")[:80]           # cap detail length for display
                st.markdown(f"""
                    <div style="background:white;border-radius:8px;padding:10px 14px;
                                margin-bottom:8px;box-shadow:0 1px 4px rgba(0,0,0,0.06)">
                        <div style="font-size:13px;color:#0f2942">
                            {icon} <strong>{e.get('user','—')}</strong>
                            — {e.get('action','').replace('_',' ').title()}
                        </div>
                        <div style="font-size:11px;color:#666;margin-top:2px">{detail}</div>
                        <div style="font-size:10px;color:#aaa;margin-top:2px">
                            {e.get('timestamp','')} · {e.get('module','')}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No activity logged yet.")
