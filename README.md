<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Streamlit-1.32+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white" />
  <img src="https://img.shields.io/badge/openFDA-API-0059B3?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCI+PHRleHQgeD0iNCIgeT0iMTgiIGZvbnQtc2l6ZT0iMTYiIGZpbGw9IndoaXRlIj7wn4+bPC90ZXh0Pjwvc3ZnPg==&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

<h1 align="center">🧪 LabVault</h1>
<h3 align="center">Pharmaceutical Laboratory Management & Quality Control System</h3>
<p align="center"><em>A full-stack LIMS prototype powered by real FDA drug recall data</em></p>

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

4. **Immutable Audit Trail** — Every action (sample creation, status change, result entry, report export) is logged with timestamp, user, and detail. This is a core GxP requirement.

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
- Filterable sample list by status, priority, and free-text search
- Expandable sample detail cards with full metadata
- Inline status updates (Pending → In Progress → Completed / Rejected)
- Analyst reassignment capability
- Color-coded priority indicators (red = Critical, orange = Major, green = Minor)

### 4. 📋 Test Result Management
- **New result entry**: Select sample, choose test type, enter result value, define spec limits
- **Automatic OOS detection**: Results outside `spec_min`–`spec_max` are flagged as `Fail (OOS)`
- **Result viewer**: Filterable table with color-coded Pass/Fail styling
- **10 pre-defined test types**: Potency, Dissolution, pH, Sterility, Particulates, Hardness, Friability, Disintegration, Water Content, Label Review

### 5. 📄 Protocol Management
- **5 pre-seeded GxP protocols** based on real USP/ICH standards:
  - Dissolution Testing (USP Apparatus II, USP ⟨711⟩)
  - Potency Assay (HPLC Method)
  - Sterility Testing (Membrane Filtration, USP ⟨71⟩)
  - pH Measurement (USP ⟨791⟩)
  - Microbial Limits Testing (USP ⟨61⟩/⟨62⟩)
- Step-by-step procedural instructions
- Admin-only protocol creation
- Linked to sample types for contextual relevance

### 6. 📈 Report Generation
- **Excel export** (.xlsx) with 3 sheets: Samples, Test Results, OOS-Only
- **PDF export** (.pdf) with formatted tables, headers, and OOS highlights
- **Filterable exports**: Choose which statuses and priorities to include
- Audit-logged: Every export is recorded in the audit trail

### 7. 🕵️ Audit Trail (GxP Compliance)
- **Immutable log** of every system action
- Captured fields: Timestamp, User, Action, Module, Target ID, Detail
- Filterable by user and action type
- Color-coded action types for rapid scanning
- Supports up to 500 entries per view with scroll

### 8. ⚙️ Admin Panel
- System overview with key metrics
- Registered user list with role badges
- Default credential reference
- FDA import statistics

---

## 🛠️ Technology Stack

| Layer | Technology | Why I Chose It |
|---|---|---|
| **Frontend** | Streamlit 1.32+ | Rapid prototyping with Python-native UI; ideal for data-heavy applications in regulated environments |
| **Backend** | Python 3.10+ | Industry standard for scientific computing, data pipelines, and lab automation |
| **Database** | SQLite 3 | Zero-config, file-based, ACID-compliant; suitable for single-site LIMS |
| **External API** | openFDA Drug Enforcement | Real-world regulatory data source maintained by the U.S. FDA |
| **PDF Generation** | ReportLab | Professional-grade PDF output used in pharma document management |
| **Excel Export** | openpyxl + pandas | Multi-sheet workbook generation for QA/QC report distribution |
| **Auth** | SHA-256 hashing | Demonstration of password hashing principles (production would use bcrypt/argon2) |
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
| **Data Integrity (ALCOA+)** | Audit trail captures every action with timestamp, user, and detail |
| **Attributable** | Every test result, status change, and sample creation is linked to a specific user |
| **Legible** | Structured data storage in normalized SQLite tables |
| **Contemporaneous** | Timestamps automatically recorded at the moment of action |
| **Original** | Audit trail is append-only (INSERT only, no UPDATE/DELETE) |
| **Accurate** | OOS detection uses defined specification limits, not manual judgment |
| **21 CFR Part 11** | User authentication, audit trail, role-based access (electronic records) |
| **EU Annex 11** | Computerized systems validation awareness in design |

### What Would Be Needed for Production

- [ ] Password hashing upgrade (bcrypt/argon2 instead of SHA-256)
- [ ] Electronic signatures for result approval workflows
- [ ] Database migration to PostgreSQL for multi-user concurrency
- [ ] TLS/HTTPS enforcement
- [ ] Formal IQ/OQ/PQ validation documentation
- [ ] Backup and disaster recovery procedures
- [ ] User session timeout and lockout policies

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+** installed
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

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
streamlit run app.py
```

### First Launch

On first launch, LabVault will automatically:
1. Create the SQLite database (`labvault.db`)
2. Seed 4 default users (1 admin + 3 lab technicians)
3. Seed 5 GxP test protocols based on USP standards
4. Import ~100 real FDA drug recall records via the openFDA API
5. Simulate scientifically accurate test results for each sample

### Default Credentials

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `admin123` |
| Lab Technician | `kembly` | `lab2024` |
| Lab Technician | `carlos` | `lab2024` |
| Lab Technician | `maria` | `lab2024` |

---

## 📁 Project Structure

```
labvault/
├── app.py                  # Main entry point — auth, routing, global styles
├── db.py                   # Database layer — schema, CRUD, auth, audit logging
├── seed.py                 # FDA API integration — data fetching & test simulation
├── requirements.txt        # Python dependencies
├── views/
│   ├── __init__.py         # Package marker
│   ├── dashboard.py        # KPI dashboard with charts, OOS alerts, activity feed
│   ├── sample_intake.py    # Manual sample registration form
│   ├── sample_tracking.py  # Sample list with filters, status updates, reassignment
│   ├── test_results.py     # Test result entry & OOS-flagged result viewer
│   ├── protocols.py        # GxP protocol viewer & creator
│   ├── reports.py          # PDF/Excel report generation with filters
│   ├── audit_trail.py      # Immutable action log with color-coded entries
│   └── admin.py            # System overview & user management
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
The tracking module allows filtering by status, priority, and free-text search. Each sample expands to show full metadata and provides inline status/assignee updates.

### Test Results
The results module features dual tabs: one for logging new test results with automatic OOS detection, and another for viewing all results with color-coded Pass/Fail indicators.

### Audit Trail
Every action in the system is immutably logged and displayed with color-coded action types, filterable by user and action category.

### Reports
Export filtered data as professional PDF reports with OOS highlights or multi-sheet Excel workbooks for further analysis.

> **Note**: To see the application in action, clone the repo and run `streamlit run app.py`. The system is fully self-contained and seeds its own data on first launch.

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

1. **Electronic Signatures** — Dual approval workflow for test results (analyst + reviewer)
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
