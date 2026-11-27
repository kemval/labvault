import pytest

from config import ConfigError, demo_mode


def usernames(db):
    return sorted(u["username"] for u in db.get_all_users())


def test_demo_mode_seeds_demo_accounts(fresh_db):
    fresh_db.seed_users(demo=True)
    assert usernames(fresh_db) == ["admin", "carlos", "kembly", "maria"]
    assert fresh_db.authenticate("admin", "admin123")["role"] == "admin"
    assert fresh_db.authenticate("kembly", "lab2024")["role"] == "lab_tech"


def test_secure_mode_seeds_only_configured_admin(fresh_db):
    fresh_db.seed_users(demo=False, admin_password="a-long-secret-pw")
    assert usernames(fresh_db) == ["admin"]
    assert fresh_db.authenticate("admin", "a-long-secret-pw")["role"] == "admin"
    assert fresh_db.authenticate("admin", "admin123") is None
    assert fresh_db.authenticate("kembly", "lab2024") is None


def test_secure_mode_without_password_refuses(fresh_db):
    with pytest.raises(ConfigError, match="LABVAULT_ADMIN_PASSWORD"):
        fresh_db.seed_users(demo=False, admin_password=None)
    assert usernames(fresh_db) == []


def test_secure_mode_rejects_short_password(fresh_db):
    with pytest.raises(ConfigError, match="at least"):
        fresh_db.seed_users(demo=False, admin_password="short")
    assert usernames(fresh_db) == []


def test_secure_mode_refuses_db_with_demo_passwords(fresh_db):
    fresh_db.seed_users(demo=True)
    with pytest.raises(ConfigError, match="admin, kembly, carlos, maria"):
        fresh_db.seed_users(demo=False, admin_password="a-long-secret-pw")


def test_reseeding_never_recreates_deleted_accounts(fresh_db):
    fresh_db.seed_users(demo=True)
    conn = fresh_db.get_conn()
    conn.execute("DELETE FROM users WHERE username = 'maria'")
    conn.commit()
    conn.close()
    fresh_db.get_all_users.clear()

    fresh_db.seed_users(demo=True)
    assert "maria" not in usernames(fresh_db)


def test_reseeding_secure_mode_keeps_existing_admin(fresh_db):
    fresh_db.seed_users(demo=False, admin_password="first-long-secret")
    fresh_db.seed_users(demo=False, admin_password="second-long-secret")
    assert fresh_db.authenticate("admin", "first-long-secret") is not None
    assert fresh_db.authenticate("admin", "second-long-secret") is None


@pytest.mark.parametrize("value,expected", [
    ("true", True), ("TRUE", True), ("1", True), ("yes", True),
    ("", False), ("false", False), ("0", False), ("no", False),
])
def test_demo_mode_requires_explicit_opt_in(settings, value, expected):
    settings(demo=value)
    assert demo_mode() is expected
