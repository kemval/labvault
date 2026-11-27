"""
domain.py — LabVault's domain vocabulary, defined once (audit TD1).

These strings are stored in the database, so changing or adding one needs
a migration: the database CHECK constraints (migration 3) hold a frozen
copy, and tests/test_domain.py fails if the two drift apart.
No imports from the rest of the app — every layer may use this module.
"""

# Samples
STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_REJECTED = (
    "Pending", "In Progress", "Completed", "Rejected")
SAMPLE_STATUSES = (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_REJECTED)

PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR = "Critical", "Major", "Minor"
PRIORITIES = (PRIORITY_CRITICAL, PRIORITY_MAJOR, PRIORITY_MINOR)

RECALL_CLASSES = ("Class I", "Class II", "Class III")

# Dosage forms a sample can have. Protocols may also target "Non-sterile"
# products as a group (e.g. the microbial-limits protocol).
SAMPLE_TYPES = ("Tablet", "Capsule", "Injectable", "Liquid", "Topical", "Powder")
PROTOCOL_SAMPLE_TYPES = SAMPLE_TYPES + ("Non-sterile",)

SOURCE_FDA, SOURCE_MANUAL = "FDA", "Manual"
SOURCES = (SOURCE_FDA, SOURCE_MANUAL)

# Test results
RESULT_PASS, RESULT_OOS = "Pass", "Fail (OOS)"   # OOS = out of specification
RESULT_STATUSES = (RESULT_PASS, RESULT_OOS)

# Accounts
ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM = "admin", "lab_tech", "system"
ROLES = (ROLE_ADMIN, ROLE_LAB_TECH, ROLE_SYSTEM)

# Non-login accounts that own automated work (role ROLE_SYSTEM).
SYSTEM_USER = "system"         # migrations, default data, unattended imports
SIMULATOR_USER = "simulator"   # simulated test results
SYSTEM_ACCOUNTS = (SYSTEM_USER, SIMULATOR_USER)
