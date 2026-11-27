"""
pages/reports.py — Export sample and test result data as PDF or Excel
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from db import get_all_samples, get_all_results
import services
from views.ui import simulated_text


def _frame(rows, columns):
    """DataFrame of `columns`, with is_simulated rendered as Yes/No."""
    df = pd.DataFrame(rows)
    if "is_simulated" not in df:
        df["is_simulated"] = 0
    df["is_simulated"] = df["is_simulated"].map(simulated_text)
    return df[columns + ["is_simulated"]]


def _sim_mark(row):
    """PDF tables are too narrow for an extra column — mark simulated IDs with *."""
    return f"{row['sample_id']} *" if row.get("is_simulated") else row["sample_id"]


def build_excel(samples, results):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Sheet 1 — Samples
        if samples:
            df_samples = _frame(samples, [
                "sample_id", "product_name", "manufacturer", "lot_number",
                "sample_type", "recall_class", "priority", "status",
                "assigned_to", "collection_date", "reason_for_recall"
            ])
            df_samples.columns = [
                "Sample ID", "Product Name", "Manufacturer", "Lot Number",
                "Sample Type", "Classification", "Priority", "Status",
                "Assigned To", "Collection Date", "Reason for Recall", "Simulated"
            ]
            df_samples.to_excel(writer, sheet_name="Samples", index=False)

        # Sheet 2 — Test Results
        if results:
            df_results = _frame(results, [
                "sample_id", "test_name", "result_value", "result_unit",
                "spec_min", "spec_max", "status", "tested_by", "tested_at", "notes"
            ])
            df_results.columns = [
                "Sample ID", "Test Name", "Result Value", "Unit",
                "Spec Min", "Spec Max", "Status", "Tested By", "Test Date", "Notes",
                "Simulated"
            ]
            df_results.to_excel(writer, sheet_name="Test Results", index=False)

        # Sheet 3 — OOS Only
        oos = [r for r in results if r["status"] == "Fail (OOS)"]
        if oos:
            df_oos = _frame(oos, [
                "sample_id", "test_name", "result_value", "result_unit",
                "spec_min", "spec_max", "tested_by", "tested_at", "notes"
            ])
            df_oos.columns = [
                "Sample ID", "Test Name", "Result", "Unit",
                "Spec Min", "Spec Max", "Tested By", "Date", "Notes", "Simulated"
            ]
            df_oos.to_excel(writer, sheet_name="OOS Results", index=False)

        # openpyxl stores any string starting with "=" as a live formula.
        # Exported values come from user input and the openFDA API, so force
        # every such cell back to plain text — content is kept exactly, but
        # Excel will never evaluate it (formula injection).
        for ws in writer.book.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        cell.data_type = "s"

    return output.getvalue()


def build_pdf(samples, results):
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    output = io.BytesIO()
    doc    = SimpleDocTemplate(output, pagesize=letter, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    story.append(Paragraph("LabVault — Quality Control Report", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Total Samples: {len(samples)} | "
        f"OOS Results: {len([r for r in results if r['status'] == 'Fail (OOS)'])}",
        styles["Normal"]
    ))
    sim_samples = sum(1 for s in samples if s.get("is_simulated"))
    sim_results = sum(1 for r in results if r.get("is_simulated"))
    if sim_samples or sim_results:
        story.append(Paragraph(
            f"<b>Contains simulated demo data:</b> {sim_samples} samples and {sim_results} "
            "results are simulated (Sample ID marked *) and are not real QC records.",
            styles["Normal"]
        ))
    story.append(Spacer(1, 20))

    # Sample summary table
    story.append(Paragraph("Sample Summary", styles["Heading2"]))
    sample_data = [["Sample ID", "Product", "Priority", "Status", "Assigned To"]]
    for s in samples[:50]:  # cap at 50 for PDF readability
        sample_data.append([
            _sim_mark(s),
            s["product_name"][:40],
            s["priority"],
            s["status"],
            s["assigned_to"],
        ])

    table = Table(sample_data, colWidths=[90, 200, 65, 80, 75])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2942")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9ff")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # OOS results
    oos = [r for r in results if r["status"] == "Fail (OOS)"]
    if oos:
        story.append(Paragraph("Out-of-Spec (OOS) Results", styles["Heading2"]))
        oos_data = [["Sample ID", "Test", "Result", "Unit", "Spec", "Tested By"]]
        for r in oos[:30]:
            spec = f"{r.get('spec_min','—')} – {r.get('spec_max','—')}"
            oos_data.append([
                _sim_mark(r), r["test_name"],
                str(r["result_value"]), r["result_unit"],
                spec, r["tested_by"]
            ])
        oos_table = Table(oos_data, colWidths=[90, 140, 55, 45, 90, 70])
        oos_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c62828")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fff8f8"), colors.white]),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ]))
        story.append(oos_table)

    doc.build(story)
    return output.getvalue()


def _log_download(username, detail):
    """download_button callback: the export is audited when it leaves the app."""
    services.log_event(username, "REPORT_EXPORTED", "Reports", "", f"Downloaded {detail}")


def show():
    st.markdown("""
        <div class="lv-header">
            <div><h1>📈 Reports</h1>
            <span>Export quality control data as PDF or Excel</span></div>
        </div>
    """, unsafe_allow_html=True)

    user    = st.session_state.user
    samples = get_all_samples()
    results = get_all_results()

    if not samples:
        st.info("No data to export yet.")
        return

    # ── SUMMARY ──────────────────────────────────────────────
    oos_count = len([r for r in results if r["status"] == "Fail (OOS)"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Samples",  len(samples))
    c2.metric("Total Results",  len(results))
    c3.metric("OOS Results",    oos_count)

    st.markdown("---")

    # ── FILTERS ──────────────────────────────────────────────
    st.markdown("#### Filter Report Data")
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.multiselect(
            "Include Sample Statuses",
            ["Pending", "In Progress", "Completed", "Rejected"],
            default=["Pending", "In Progress", "Completed", "Rejected"]
        )
    with col2:
        priority_filter = st.multiselect(
            "Include Priorities",
            ["Critical", "Major", "Minor"],
            default=["Critical", "Major", "Minor"]
        )

    filtered_samples = [s for s in samples
                        if s["status"] in status_filter
                        and s["priority"] in priority_filter]

    filtered_ids     = {s["sample_id"] for s in filtered_samples}
    filtered_results = [r for r in results if r["sample_id"] in filtered_ids]

    st.markdown(f"**{len(filtered_samples)} samples** and **{len(filtered_results)} results** will be included in the export.")
    st.markdown("---")

    # ── EXPORT BUTTONS ────────────────────────────────────────
    st.markdown("#### Export")
    col_excel, col_pdf = st.columns(2)

    with col_excel:
        st.markdown("**Excel Report (.xlsx)**")
        st.markdown("3 sheets: Samples · Test Results · OOS Only")
        if st.button("📊 Generate Excel", use_container_width=True, type="primary"):
            with st.spinner("Building Excel report..."):
                try:
                    excel_data = build_excel(filtered_samples, filtered_results)
                    st.download_button(
                        label="⬇️ Download Excel",
                        # Audited when the file is actually downloaded, not built.
                        on_click=_log_download,
                        args=(user["username"], f"Excel: {len(filtered_samples)} samples, {len(filtered_results)} results"),
                        data=excel_data,
                        file_name=f"LabVault_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Excel export failed: {e}")

    with col_pdf:
        st.markdown("**PDF Report (.pdf)**")
        st.markdown("Formatted QC report with OOS highlights")
        if st.button("📄 Generate PDF", use_container_width=True):
            with st.spinner("Building PDF report..."):
                try:
                    pdf_data = build_pdf(filtered_samples, filtered_results)
                    st.download_button(
                        label="⬇️ Download PDF",
                        # Audited when the file is actually downloaded, not built.
                        on_click=_log_download,
                        args=(user["username"], f"PDF: {len(filtered_samples)} samples"),
                        data=pdf_data,
                        file_name=f"LabVault_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"PDF export failed: {e}. Make sure reportlab is installed.")
