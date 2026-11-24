import pytest

from app.core.config import get_settings
from tests.conftest import login, make_user


async def test_login_sets_httponly_cookie_and_returns_token(client):
    await make_user("alice")
    r = await client.post("/api/auth/login", json={"username": "Alice", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "alice" and body["user"]["role"] == "annotator"
    assert "password_hash" not in str(body)
    cookie = r.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/api/auth" in cookie


async def test_wrong_password_and_unknown_user_share_one_error(client):
    await make_user("alice")
    a = await client.post("/api/auth/login", json={"username": "alice", "password": "nope"})
    b = await client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert a.status_code == b.status_code == 401
    assert a.json()["code"] == b.json()["code"] == "invalid_credentials"


async def test_lockout_after_repeated_failures(client):
    await make_user("alice")
    for _ in range(get_settings().lockout_max_failures):
        assert (await client.post("/api/auth/login", json={"username": "alice", "password": "x"})).status_code == 401
    r = await client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert r.status_code == 429 and r.json()["code"] == "too_many_attempts" and "retry-after" in r.headers


async def test_successful_login_resets_failure_counter(client):
    await make_user("alice")
    for _ in range(3):
        await client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    await login(client, "alice")
    for _ in range(3):
        await client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    assert (await client.post("/api/auth/login", json={"username": "alice", "password": "password123"})).status_code == 200


async def test_me_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    await make_user("alice")
    h = await login(client, "alice")
    assert (await client.get("/api/auth/me", headers=h)).json()["username"] == "alice"
    assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})).status_code == 401


async def test_refresh_rotates_and_returns_new_access_token(client):
    await make_user("alice")
    await login(client, "alice")
    old = client.cookies.get("refresh_token")
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"] and r.json()["user"]["username"] == "alice"
    assert client.cookies.get("refresh_token") != old


async def test_refresh_without_cookie_is_401(client):
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_replayed_refresh_token_revokes_every_session(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_grace_seconds", 0)
    await make_user("alice")
    await login(client, "alice")
    stolen = client.cookies.get("refresh_token")
    assert (await client.post("/api/auth/refresh")).status_code == 200  # legit rotation
    client.cookies.set("refresh_token", stolen, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401  # replay → detected
    # the rotated (legit) token is now dead as well
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_concurrent_refresh_within_grace_window_is_tolerated(client):
    await make_user("alice")
    await login(client, "alice")
    first = client.cookies.get("refresh_token")
    assert (await client.post("/api/auth/refresh")).status_code == 200
    client.cookies.set("refresh_token", first, path="/api/auth")  # second tab still holds the old cookie
    assert (await client.post("/api/auth/refresh")).status_code == 200


async def test_logout_revokes_refresh_token(client):
    await make_user("alice")
    await login(client, "alice")
    mine = client.cookies.get("refresh_token")
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.post("/api/auth/refresh")).status_code == 401  # cookie was cleared
    client.cookies.set("refresh_token", mine, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401  # the old token itself is dead, grace or not


async def test_must_change_password_blocks_api_until_changed(client):
    await make_user("bob", must_change=True)
    h = await login(client, "bob")
    assert (await client.get("/api/auth/me", headers=h)).json()["must_change_password"] is True
    r = await client.get("/api/images", headers=h)
    assert r.status_code == 403 and r.json()["code"] == "password_change_required"
    bad = await client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong", "new_password": "newpassword1"})
    assert bad.status_code == 401
    weak = await client.post("/api/auth/change-password", headers=h, json={"current_password": "password123", "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["code"] == "weak_password"
    ok = await client.post("/api/auth/change-password", headers=h, json={"current_password": "password123", "new_password": "newpassword1"})
    assert ok.status_code == 204
    assert (await client.get("/api/images", headers=h)).status_code == 200
    await login(client, "bob", "newpassword1")


async def test_change_password_keeps_current_session_but_revokes_others(client):
    await make_user("alice")
    await login(client, "alice")
    mine = client.cookies.get("refresh_token")
    other = (await client.post("/api/auth/login", json={"username": "alice", "password": "password123"}))
    other_cookie = client.cookies.get("refresh_token")
    assert other.status_code == 200 and other_cookie != mine
    h = {"Authorization": f"Bearer {other.json()['access_token']}"}
    r = await client.post("/api/auth/change-password", headers=h, json={"current_password": "password123", "new_password": "another-pass1"})
    assert r.status_code == 204
    assert (await client.post("/api/auth/refresh")).status_code == 200  # current session survives
    client.cookies.set("refresh_token", mine, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401  # the other one was revoked


async def test_deactivated_user_loses_access_immediately(client):
    await make_user("admin", "admin")
    await make_user("alice")
    ah = await login(client, "admin")
    h = await login(client, "alice")
    uid = (await client.get("/api/auth/me", headers=h)).json()["id"]
    assert (await client.patch(f"/api/users/{uid}", headers=ah, json={"active": False})).status_code == 200
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401
    r = await client.post("/api/auth/login", json={"username": "alice", "password": "password123"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/api/images", "/api/experiments", "/api/users", "/api/audit"])
async def test_every_data_route_requires_authentication(client, path):
    assert (await client.get(path)).status_code == 401


async def test_admin_deactivation_cannot_be_dodged_by_refresh_grace(client):
    """A session revoked for security reasons must not refresh, even immediately after revocation."""
    from tests.conftest import make_user as mk
    await mk("admin", "admin")
    await mk("alice")
    await login(client, "alice")
    alice_cookie = client.cookies.get("refresh_token")
    ah = await login(client, "admin")
    uid = (await client.get("/api/auth/me", headers=await login(client, "alice"))).json()["id"]
    await client.patch(f"/api/users/{uid}", headers=ah, json={"active": False})
    client.cookies.set("refresh_token", alice_cookie, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401
