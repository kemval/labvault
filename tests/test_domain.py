"""domain.py must match the database rules (migration 3) exactly."""
import domain
from repo import schema


def test_domain_values_match_the_database_constraints():
    # A value added to domain.py without a migration would be rejected by the
    # database; one removed would leave stored rows the app no longer knows.
    assert domain.SAMPLE_STATUSES == schema._M003_STATUSES
    assert domain.PRIORITIES == schema._M003_PRIORITIES
    assert domain.RECALL_CLASSES == schema._M003_CLASSES
    assert domain.PROTOCOL_SAMPLE_TYPES == schema._M003_SAMPLE_TYPES
    assert domain.SOURCES == schema._M003_SOURCES
    assert domain.RESULT_STATUSES == schema._M003_RESULT_STATUSES
    assert domain.ROLES == schema._M003_ROLES
    assert domain.SYSTEM_ACCOUNTS == schema._M003_SYSTEM_ACCOUNTS
