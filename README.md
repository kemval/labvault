<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/openFDA-API-0059B3?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCI+PHRleHQgeD0iNCIgeT0iMTgiIGZvbnQtc2l6ZT0iMTYiIGZpbGw9IndoaXRlIj7wn4+bPC90ZXh0Pjwvc3ZnPg==&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

<h1 align="center">🧪 LabVault</h1>
<h3 align="center">Pharmaceutical Laboratory Management & Quality Control System</h3>
<p align="center"><em>A full-stack LIMS prototype powered by real FDA drug recall data</em></p>

<p align="center">
  <a href="https://labvault.streamlit.app/">
    <img src="https://img.shields.io/badge/🔴_LIVE_DEMO-labvault.streamlit.app-FF4B4B?style=for-the-badge&logoColor=white" alt="Live Demo" />
  </a>
</p>

<p align="center">
  <strong>👉 <a href="https://labvault.streamlit.app/">Try the live demo here</a> 👈</strong><br/>
  <sub>Live demo login: <code>admin</code> / <code>admin123</code> or <code>kembly</code> / <code>lab2024</code> (demo mode only)</sub>
</p>

---

## 📋 Table of Contents

- [Executive Summary](#-executive-summary)
- [Problem Statement](#-problem-statement)
- [Solution & Technical Approach](#-solution--technical-approach)
- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Technology Stack](#-technology-stack)
- [Database Schema](#-database-schema)
- [FDA Data Integration](#-fda-data-integration)
- [GxP Compliance Considerations](#-gxp-compliance-considerations)
- [Getting Started](#-getting-started)
- [Project Structure](#-project-structure)
- [Screenshots & Walkthrough](#-screenshots--walkthrough)
- [Skills Demonstrated](#-skills-demonstrated)
- [Future Enhancements](#-future-enhancements)
- [About the Author](#-about-the-author)

---

## 🔬 Executive Summary

**LabVault** is a Laboratory Information Management System (LIMS) prototype that I designed and built from scratch to demonstrate my ability to solve real-world problems in pharmaceutical quality control and regulatory compliance.

The system ingests **real drug recall data** from the [openFDA Enforcement API](https://open.fda.gov/apis/drug/enforcement/), transforms it into laboratory samples, and provides a complete workflow for sample registration, tracking, test result logging, Out-of-Spec (OOS) investigation, protocol management, audit trail compliance, and report generation.

This project was developed as part of my application to **AbbVie's University Internship Program (Engineering and Business)** — REF49688Z — in Heredia, Costa Rica. It reflects my understanding of pharmaceutical manufacturing quality systems and my ability to deliver production-grade software solutions for regulated environments.

> **Key Highlight:** Every sample in the system originates from an actual FDA drug recall record. Test results are simulated based on scientifically accurate specifications (USP/ICH guidelines), making this a realistic representation of pharmaceutical QC workflows.

---

## ❓ Problem Statement

Pharmaceutical laboratories operate under strict regulatory frameworks (FDA 21 CFR Part 11, EU Annex 11, ICH Q7). They face several challenges:

| Challenge | Impact |
|---|---|
| **Manual sample tracking** | Lost samples, delayed testing, no real-time status visibility |
| **Paper-based test results** | Transcription errors, no automatic OOS flagging |
| **Disconnected audit trails** | Regulatory risk during inspections; FDA Warning Letters |
| **No protocol standardization** | Inconsistent testing procedures across analysts |
| **Slow report generation** | Hours spent compiling data for quality reviews |

I asked myself: *What would a modern, digital-first solution look like if a pharmaceutical QC lab needed to manage samples, track results, maintain regulatory compliance, and generate reports — all in one place?*

**LabVault is my answer.**

---

## 💡 Solution & Technical Approach

### Design Philosophy

I approached this project as if I were building an internal tool for a real pharmaceutical QC lab. Every design decision maps to an actual industry need:

1. **Real Data, Not Mock Data** — Instead of fabricating sample records, I pull directly from the FDA's enforcement database. This grounds the system in reality and demonstrates API integration skills.

2. **Scientifically Accurate Test Simulation** — Test results aren't random numbers. The `seed.py` module analyzes the FDA recall *reason* (e.g., "dissolution failure," "superpotency," "microbial contamination") and generates test results with appropriate specifications based on USP/ICH guidelines.

3. **Role-Based Access Control** — Admins and lab technicians have different permissions, mirroring real organizational hierarchies in pharma.

4. **Append-Only Audit Trail** — Every change (sample creation, status change, result entry), report download and sign-in is logged in the same transaction as the change, with a UTC timestamp, the user, old and new values, and the reason for the change. Database triggers reject edits and deletions of audit rows.

5. **OOS Detection & Alerting** — Results that fall outside specification limits are automatically flagged, appearing on the dashboard as alerts requiring investigation — exactly how real OOS workflows operate.

### Methodology

```
┌─────────────────────────────────────────────────────────────────┐
│                        DEVELOPMENT PROCESS                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. RESEARCH          → Study FDA 21 CFR Part 11, USP testing     │
│                          protocols, LIMS market requirements       │
│                                                                   │
│  2. DATA SOURCING     → Identify openFDA API, map enforcement     │
│                          fields to lab sample attributes           │
│                                                                   │
│  3. SCHEMA DESIGN     → Normalize data into 5 relational tables   │
│                          with foreign key constraints              │
│                                                                   │
│  4. BACKEND           → Build SQLite data layer with CRUD ops,    │
│                          audit logging, and query optimizations    │
│                                                                   │
│  5. FDA INTEGRATION   → Parse API responses, detect sample types, │
│                          simulate scientifically valid test data   │
│                                                                   │
│  6. FRONTEND          → Design 8 modular Streamlit views with     │
│                          custom CSS, responsive layout, badges     │
│                                                                   │
│  7. REPORTING         → Implement PDF (ReportLab) and Excel       │
│                          (openpyxl) export with filtering          │
│                                                                   │
│  8. VALIDATION        → Test all workflows end-to-end, verify     │
│                          OOS flagging accuracy, audit completeness │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ System Architecture

```
                    ┌──────────────────────────────┐
                    │         openFDA API           │
                    │  (Drug Enforcement Records)   │
                    └──────────┬───────────────────┘
                               │ HTTPS / JSON
                               ▼
┌─────────────────────────────────────────────────────────┐
│                      LabVault Application                │
│                                                          │
│  ┌────────────┐   ┌────────────┐   ┌────────────────┐   │
│  │  seed.py   │──▶│   db.py    │──▶│  labvault.db   │   │
│  │ FDA Parser │   │ Data Layer │   │    (SQLite)    │   │
│  │ Test Sim.  │   │ Auth/CRUD  │   │   5 tables     │   │
│  └────────────┘   └─────┬──────┘   └────────────────┘   │
│                         │                                │
│                         ▼                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │                   app.py                          │   │
│  │         (Session State / Router / Auth)            │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                                │
│          ┌──────────────┼──────────────┐                 │
│          ▼              ▼              ▼                 │
│  ┌─────────────┐ ┌───────────┐ ┌─────────────┐         │
│  │  Dashboard  │ │  Sample   │ │   Reports   │         │
│  │  Tracking   │ │  Intake   │ │  PDF/Excel  │         │
│  │  Results    │ │ Protocols │ │ Audit Trail │         │
│  └─────────────┘ └───────────┘ └─────────────┘         │
│          │              │              │                 │
│          └──────────────┼──────────────┘                 │
│                         ▼                                │
│              ┌──────────────────┐                        │
│              │  Streamlit UI    │                        │
│              │  (Browser)       │                        │
│              └──────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 1. 📊 Real-Time Dashboard
- **KPI metrics**: Total samples, pending, in-progress, completed, OOS count
- **Interactive charts**: Sample status distribution and priority breakdown (bar charts)
- **OOS alert panel**: Immediate visibility into out-of-spec results requiring investigation
- **Recent activity feed**: Live audit trail of the last 8 system actions
- **Recent samples**: Quick-glance cards with priority and status badges

### 2. 🧫 Sample Intake (Manual Registration)
- Full registration form with product name, manufacturer, lot number, sample type
- FDA classification (Class I/II/III) and priority assignment (Critical/Major/Minor)
- Automatic UUID-based sample ID generation (`LV-XXXXXXXX`)
- Protocol assignment capability
- Lab technician assignment from registered users

### 3. 🔬 Sample Tracking
- Paged sample table (25 per page) filtered, searched and sorted in the database, so the page
  stays fast at thousands of samples; "Assigned to me" and "Unassigned" views
- Open one sample at a time for its full metadata, assigned protocol and result review counts
- Controlled status changes: Pending → In Progress → Completed (every result reviewed, ≥ 1 approved),
  or → Rejected; only allowed next steps are offered, every change needs a reason, and
  Rejected/Completed need an explicit confirmation
- Only the assigned lab tech or an admin can change a sample; techs can claim unassigned samples;
  reassignment and reopening a Completed/Rejected sample are admin-only
- Color-coded priority indicators (red = Critical, orange = Major, green = Minor)

### 4. 📋 Test Result Management
- **New result entry**: Select one of your In Progress samples (any, for admins), choose the test, enter the value — the limits come from the specification for that sample type and test and can't be edited by the analyst
- **Automatic OOS detection**: Results outside the specification are flagged as `Fail (OOS)`; each result records which specification version judged it
- **No specification, no numeric result**: entry is blocked until an admin defines one
- **Second-person review with e-signature**: anyone except the analyst signs each result as approved or rejected, re-entering their password; a rejection needs a reason and the result stays on record but no longer counts. Wrong signature passwords count toward the lockout
- **Completion needs review**: a sample completes only when every result is signed and at least one is approved
- **Result viewer**: Filterable table with color-coded Pass/Fail styling and each result's review
- **10 pre-defined test types**: Potency, Dissolution, pH, Sterility, Particulates, Hardness, Friability, Disintegration, Water Content, Label Review

### 5. 🔎 OOS Investigations
- **Every OOS result opens an investigation** automatically, in the same save as the result
- **Closed only by an admin (QA)**, never on a result they logged, with an e-signature and written findings
- **The conclusion decides the result's signature**: *assignable laboratory error* → the result can only be rejected (retest); *OOS confirmed* → it can only be approved, so a failure can't be thrown out without QA finding a lab error
- Investigations can't be deleted, and once closed can't be changed (database triggers)

### 6. 📏 Specifications
- Acceptance limits per sample type × test (e.g. Tablet × Dissolution ≥ 80 %), visible to everyone
- Admin-only maintenance; every change is versioned and audited with old value, new value and reason
- Demo instances start with defaults matching the demo data; secure instances start empty, for QA to define

### 7. 📄 Protocol Management
- **5 pre-seeded GxP protocols** based on real USP/ICH standards:
  - Dissolution Testing (USP Apparatus II, USP ⟨711⟩)
  - Potency Assay (HPLC Method)
  - Sterility Testing (Membrane Filtration, USP ⟨71⟩)
  - pH Measurement (USP ⟨791⟩)
  - Microbial Limits Testing (USP ⟨61⟩/⟨62⟩)
- Step-by-step procedural instructions
- Admin-only protocol creation
- Linked to sample types for contextual relevance

### 8. 📈 Report Generation
- **Excel export** (.xlsx) with 3 sheets: Samples, Test Results, OOS-Only
- **PDF export** (.pdf) with formatted tables, headers, and OOS highlights
- **Filterable exports**: Choose which statuses and priorities to include
- Audit-logged: every download is recorded in the audit trail

### 9. 🕵️ Audit Trail
- **Append-only log**: database triggers reject UPDATE and DELETE on audit rows
- Captured fields: Timestamp (UTC), User, Action, Module, Target ID, Old Value, New Value, Reason, Detail
- Status and assignment changes require a reason
- Sign-ins, failed sign-ins and sign-outs are recorded
- Filterable by user and action type; paged, so every entry is reachable
- Color-coded action types for rapid scanning

### 10. ⚙️ Admin Panel
- System overview with key metrics
- Account table: role, active/disabled, lockout and forced-password-change state
- User management (ADR 0017): create accounts with a temporary password, reset passwords,
  unlock locked accounts, disable/enable, change roles. Each change needs a reason and is
  audited; accounts are disabled, never deleted; an admin can't change their own account;
  disabling (or promoting) a tech with open samples is refused until they're reassigned
- **My Account** page for every user to change their own password; a temporary password
  must be changed before anything else
- Default credential reference (demo mode)
- FDA import statistics

### 11. ♿ Accessibility (WCAG 2.2 AA)
- Every page has its own URL; navigation titles are plain text with icons that screen readers skip
- Press Enter to sign in
- All custom text colours are at least 4.5:1 contrast, checked by `tests/test_accessibility.py`
- Theme and navy sidebar come from `.streamlit/config.toml`, so Streamlit's alerts and focus
  rings keep their own readable colours

---

## 🛠️ Technology Stack

| Layer | Technology | Why I Chose It |
|---|---|---|
| **Frontend** | Streamlit 1.32+ | Rapid prototyping with Python-native UI; ideal for data-heavy applications in regulated environments |
| **Backend** | Python 3.11+ | Industry standard for scientific computing, data pipelines, and lab automation |
| **Database** | SQLite 3 | Zero-config, file-based, ACID-compliant; suitable for single-site LIMS |
| **External API** | openFDA Drug Enforcement | Real-world regulatory data source maintained by the U.S. FDA |
| **PDF Generation** | ReportLab | Professional-grade PDF output used in pharma document management |
| **Excel Export** | openpyxl + pandas | Multi-sheet workbook generation for QA/QC report distribution |
| **Auth** | Salted scrypt (stdlib), lockout, idle timeout | OWASP-recommended hashing with no compiled dependency; 5 failures lock an account for 15 min; 30 min idle signs out (ADR 0013) |
| **Styling** | Custom CSS | Hand-crafted UI matching pharmaceutical industry aesthetics |

---

## 🗄️ Database Schema

```sql
┌─────────────────┐       ┌──────────────────┐
│     users        │       │    protocols      │
├─────────────────┤       ├──────────────────┤
│ id (PK)         │       │ id (PK)          │
│ username (UQ)   │       │ name             │
│ password (SHA)  │       │ sample_type      │
│ role            │       │ description      │
└────────┬────────┘       │ steps            │
         │                │ created_by       │
         │                │ created_at       │
         │                └────────┬─────────┘
         │                         │
         │    ┌────────────────────┐│
         │    │     samples        ││
         │    ├────────────────────┤│
         │    │ id (PK)           ││
         │    │ sample_id (UQ)    ││
         │    │ product_name      ││
         │    │ lot_number        ││
         │    │ manufacturer      ││
         │    │ sample_type       ││
         │    │ recall_class      ││
         │    │ priority          ││
         │    │ reason_for_recall ││
         │    │ collection_date   ││
         │    │ status            ││
         ├───▶│ assigned_to (FK)  ││
         │    │ protocol_id (FK) ─┘│
         │    │ notes             │
         │    │ source            │
         │    └────────┬──────────┘
         │             │
         │             │ 1:N
         │             ▼
         │    ┌────────────────────┐
         │    │   test_results     │
         │    ├────────────────────┤
         │    │ id (PK)           │
         │    │ sample_id (FK)    │
         │    │ test_name         │
         │    │ result_value      │
         │    │ result_unit       │
         │    │ spec_min          │
         │    │ spec_max          │
         │    │ status            │
         │    │ tested_by         │
         │    │ tested_at         │
         │    │ notes             │
         │    └───────────────────┘
         │
         │    ┌────────────────────┐
         │    │   audit_trail      │
         │    ├────────────────────┤
         │    │ id (PK)           │
         │    │ timestamp         │
         ├───▶│ user              │
              │ action            │
              │ module            │
              │ target_id         │
              │ detail            │
              └───────────────────┘
```

**5 tables** · **Foreign key constraints enforced** · **PRAGMA foreign_keys = ON**

---

## 🌐 FDA Data Integration

### How It Works

LabVault connects to the [openFDA Drug Enforcement API](https://open.fda.gov/apis/drug/enforcement/) to pull real pharmaceutical recall records. Here's the data pipeline:

```
FDA API Response                    LabVault Mapping
─────────────────                   ─────────────────
recall_number          ──────▶      sample_id
product_description    ──────▶      product_name + sample_type (auto-detected)
recalling_firm         ──────▶      manufacturer
reason_for_recall      ──────▶      reason_for_recall + test result simulation
classification         ──────▶      recall_class → priority mapping
status                 ──────▶      status (Ongoing→In Progress, Completed→Completed)
recall_initiation_date ──────▶      collection_date
```

### Intelligent Sample Type Detection

The `detect_sample_type()` function parses product descriptions to automatically classify dosage forms:

| Keywords Detected | Classified As |
|---|---|
| "tablet", "tab " | Tablet |
| "capsule", "cap " | Capsule |
| "injection", "injectable", "vial", "iv", "infusion" | Injectable |
| "solution", "liquid", "syrup", "suspension" | Liquid |
| "cream", "ointment", "gel", "topical" | Topical |
| "powder", "granule" | Powder |

### Scientifically Grounded Test Simulation

The most technically interesting part of LabVault is how it generates test results. Rather than random numbers, the system analyzes the **reason for recall** and produces results that reflect the actual failure mode:

| Recall Reason | Test Generated | Spec Range | Simulated OOS Range |
|---|---|---|---|
| Dissolution failure | Dissolution (60 min) | ≥ 80% | 42–74% |
| Superpotency | Potency (% Label Claim) | 90–110% | 112–135% |
| Subpotency | Potency (% Label Claim) | 90–110% | 68–88% |
| Sterility failure | Microbial Count | 0 CFU/mL | 150–800 CFU/mL |
| Particulate matter | Visible Particulates | ≤ 10/container | 15–85/container |
| pH out of range | pH | 4.5–7.5 | 2.5–3.8 or 8.2–9.5 |
| Labeling issues | Label Review + Potency | N/A | Fail on label, Pass on potency |

> All specification ranges are based on real USP (United States Pharmacopeia) and ICH (International Council for Harmonisation) guidelines.

---

## ✅ GxP Compliance Considerations

While LabVault is a prototype, it was designed with pharmaceutical regulatory awareness:

| GxP Principle | LabVault Implementation |
|---|---|
| **Data Integrity (ALCOA+)** | Each change and its audit row are saved in one transaction, with old value, new value and reason |
| **Attributable** | Every test result, status change, and sample creation is linked to a specific user |
| **Legible** | Structured data storage in normalized SQLite tables |
| **Contemporaneous** | UTC timestamps recorded at the moment of action |
| **Original** | Audit trail is append-only, enforced by database triggers |
| **Accurate** | OOS detection uses defined specification limits, not manual judgment |
| **21 CFR Part 11** | User authentication, audit trail, role-based access, e-signatures with signer, time and meaning (§11.50, §11.200) |
| **EU Annex 11** | Computerized systems validation awareness in design |

### What Would Be Needed for Production

- [x] Password hashing upgrade (salted scrypt instead of SHA-256)
- [x] Electronic signatures for result approval workflows
- [ ] Database migration to PostgreSQL for multi-user concurrency
- [ ] TLS/HTTPS enforcement
- [ ] Formal IQ/OQ/PQ validation documentation
- [ ] Backup and disaster recovery procedures
- [x] User session timeout and lockout policies

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12** (pinned in `.python-version`; 3.11 is also tested in CI)
- **pip** package manager
- Internet connection (for initial FDA data import)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/kemval/labvault.git
cd labvault

# 2. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install the locked dependencies (exact versions, hash-checked)
pip install --require-hashes -r requirements.txt

# 4. Run the application (demo mode — see Configuration below)
LABVAULT_DEMO_MODE=true streamlit run app.py
```

### First Launch

On first launch, LabVault will automatically:
1. Create the SQLite database (`labvault.db`)
2. Seed users: the 4 demo accounts in demo mode, or a single `admin` in secure mode
3. Seed 5 GxP test protocols based on USP standards
4. Import ~100 real FDA drug recall records via the openFDA API
5. Simulate scientifically accurate test results for each sample

### Configuration

LabVault runs in one of two modes (see [ADR 0001](docs/adr/0001-deployment-modes.md)).
Settings are read from environment variables or `.streamlit/secrets.toml`.

| Setting | Purpose |
|---|---|
| `LABVAULT_DEMO_MODE=true` | Demo mode: seeds the public demo accounts below and shows their credentials on the login screen |
| `LABVAULT_ADMIN_PASSWORD` | Secure mode (the default): password for the initial `admin` account, at least 12 characters. Used only when no users exist yet |

With neither setting, the app stops with a configuration error and does not create any accounts.
In secure mode it also refuses to start on a database that still contains demo passwords.

After the first start, manage accounts on the **Admin** page (ADR 0017). Keep at least two
admin accounts: an admin can't reset or unlock their own account, so a sole admin who loses
their password can only be recovered by editing the database.

### Demo Credentials (demo mode only)

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `admin123` |
| Lab Technician | `kembly` | `lab2024` |
| Lab Technician | `carlos` | `lab2024` |
| Lab Technician | `maria` | `lab2024` |

### Backups

Use `scripts/backup_db.py` for verified online backups and safe restores. See the
[backup & restore runbook](docs/operations/backup-restore.md). On Streamlit Community
Cloud the app's disk is not durable, so treat that instance as disposable demo data.

### Running Tests

```bash
pip install --require-hashes -r requirements-dev.txt
python -m pytest
ruff check .
```

CI (`.github/workflows/ci.yml`) runs ruff, the test suite on Python 3.11 and 3.12, a lock-file
freshness check, and `pip-audit` on every pull request, all from the hashed lock files.

### Dependencies

`requirements.in` / `requirements-dev.in` hold the allowed version ranges; `requirements.txt` /
`requirements-dev.txt` are generated universal locks (one file for macOS, Linux and Windows, Python 3.11+) with exact
versions and hashes (see ADR 0010).
Streamlit Cloud installs `requirements.txt`. To add or upgrade a package:

```bash
# edit requirements.in (or requirements-dev.in), then regenerate both locks:
uv pip compile --universal --generate-hashes --python-version 3.11 requirements.in -o requirements.txt
uv pip compile --universal --generate-hashes --python-version 3.11 requirements-dev.in -o requirements-dev.txt
# upgrade within the ranges: add --upgrade (or --upgrade-package NAME)
```

Dependabot proposes weekly updates as pull requests, which CI tests before anything is merged.

---

## 📁 Project Structure

```
labvault/
├── app.py                  # Main entry point — auth, routing, global styles
├── config.py               # Deployment settings (demo vs. secure mode)
├── domain.py               # Statuses, priorities, roles… defined once (must match the DB rules)
├── services.py             # Use cases: every data change + its audit row in one transaction
├── db.py                   # Cached reads for the views (the only Streamlit-aware data module)
├── seed.py                 # openFDA fetch + test-result simulation (pure, no database)
├── repo/                   # Streamlit-free persistence: SQLite connection, schema +
│   │                       #   migrations, users, samples, results, protocols, audit, FDA batch
│   └── ...
├── scripts/                # backup_db.py (backup/restore), dedupe_simulated_results.py
├── docs/                   # adr/ (architecture decisions), operations/ (runbooks)
├── tests/                  # pytest + Streamlit AppTest suite
├── requirements.in         # Allowed version ranges (edit these)
├── requirements.txt        # Generated lock: exact versions + hashes (Streamlit Cloud installs this)
├── requirements-dev.*      # Same for test/lint tools, constrained to the runtime lock
├── .python-version         # Python 3.12
├── views/
│   ├── __init__.py         # Package marker
│   ├── ui.py               # Shared rendering helpers (HTML escaping, SIMULATED labels)
│   ├── dashboard.py        # KPI dashboard with charts, OOS alerts, activity feed
│   ├── sample_intake.py    # Manual sample registration form
│   ├── sample_tracking.py  # Paged sample table, detail panel, status updates, reassignment
│   ├── test_results.py     # Test result entry & OOS-flagged result viewer
│   ├── protocols.py        # GxP protocol viewer & creator
│   ├── specifications.py   # Acceptance limits per sample type × test (admin-maintained)
│   ├── investigations.py   # OOS investigations, closed by an admin with an e-signature
│   ├── reports.py          # PDF/Excel report generation with filters
│   ├── audit_trail.py      # Append-only audit log, filtered and paged
│   ├── admin.py            # System overview & account management
│   └── account.py          # Change your own password
├── README.md               # This file
├── LICENSE                 # MIT License
└── .gitignore              # Git ignore rules
```

---

## 📸 Screenshots & Walkthrough

### Login Screen
The login screen provides secure access with role-based authentication. Demo credentials are displayed for easy evaluation.

### Dashboard
The dashboard presents a real-time overview of laboratory operations: total samples, pending/in-progress/completed counts, OOS alerts, recent samples with priority badges, and the latest audit trail entries.

### Sample Tracking
The tracking module shows a paged table filtered by status, priority, assignee and free-text search, with a choice of sort order. Opening a sample shows its full metadata and protocol next to the status/assignee update form.

### Test Results
The results module features dual tabs: one for logging new test results with automatic OOS detection, and another for viewing all results with color-coded Pass/Fail indicators.

### Audit Trail
Every action in the system is immutably logged and displayed with color-coded action types, filterable by user and action category.

### Reports
Export filtered data as professional PDF reports with OOS highlights or multi-sheet Excel workbooks for further analysis.

> **Note**: To see the application in action, clone the repo and run `LABVAULT_DEMO_MODE=true streamlit run app.py`. The system is fully self-contained and seeds its own data on first launch.

---

## 🎯 Skills Demonstrated

This project demonstrates competencies directly aligned with AbbVie's internship requirements:

### Engineering & Technical Skills

| Skill | Evidence in LabVault |
|---|---|
| **Python Development** | 1,500+ lines of structured, documented Python code across 11 modules |
| **Database Design** | Normalized SQLite schema with 5 tables, foreign keys, and indexed queries |
| **API Integration** | Real-time data ingestion from the openFDA REST API with error handling |
| **Data Analysis** | Pandas-based data transformation, aggregation, and visualization |
| **UI/UX Design** | Custom CSS-styled Streamlit interface with responsive layouts and micro-interactions |
| **Report Generation** | Dual-format export (PDF via ReportLab, Excel via openpyxl) with filtering |
| **Quality Systems** | GxP-aware audit trail, OOS detection, protocol management |
| **Process Improvement** | Automated workflows replacing manual paper-based lab processes |

### Professional & Soft Skills

| Skill | Evidence |
|---|---|
| **Initiative** | Self-directed project conception, design, and execution |
| **Attention to Detail** | Scientifically accurate test specifications, proper USP references |
| **Communication** | Comprehensive documentation, clean code comments, structured README |
| **Problem Solving** | Novel approach to using FDA recall data for realistic lab simulation |
| **Adaptability** | Full-stack development spanning backend, frontend, data, and DevOps |
| **Ethical Commitment** | Built with regulatory compliance and data integrity as core principles |

### Tools & Technologies

- **Advanced Excel**: Programmatic Excel generation with multi-sheet workbooks (openpyxl)
- **Data Visualization**: Interactive charts and formatted data tables (Streamlit + Pandas)
- **Version Control**: Git-managed project with proper .gitignore and documentation
- **Systems Thinking**: End-to-end workflow design from data ingestion to report export

---

## 🔮 Future Enhancements

If I were to continue developing LabVault into a production system, the roadmap would include:

1. ~~**Electronic Signatures**~~ — done: second-person review with e-signature (ADR 0014)
2. **CAPA Module** — Corrective and Preventive Action tracking linked to OOS results
3. **Stability Studies** — Time-based testing with shelf-life predictions
4. **Instrument Integration** — Direct data import from HPLC, UV-Vis, pH meters
5. **Multi-Site Support** — PostgreSQL backend with site-level access control
6. **API Endpoints** — RESTful API for integration with ERP/SAP systems
7. **Batch Record Management** — Complete batch production records with e-signatures
8. **Statistical Process Control** — Control charts, capability indices (Cpk), trend analysis
9. **Regulatory Submission Prep** — Automated formatting for FDA 510(k) or NDA submissions
10. **Mobile Companion App** — React Native app for warehouse/lab floor sample scanning

---

## 👤 About the Author

This project was designed and developed as a demonstration of technical capability and domain knowledge for the **AbbVie University Internship Program** (REF49688Z) in Heredia, Costa Rica.

I built LabVault to show that I can:
- **Understand the problem domain** — pharmaceutical quality control, regulatory compliance, laboratory operations
- **Design and implement solutions** — from database schema to user interface to report generation
- **Work with real-world data** — leveraging the FDA's public enforcement database
- **Write production-quality code** — documented, modular, and maintainable
- **Think about the bigger picture** — GxP compliance, audit trails, data integrity, and continuous improvement

I am passionate about applying engineering and technology to solve challenges in the pharmaceutical and healthcare industries, and I would welcome the opportunity to bring this mindset to AbbVie's team.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <em>Built with ❤️ for pharmaceutical quality, regulatory excellence, and continuous improvement.</em>
</p>
