from tests.conftest import login, make_user


async def test_only_admin_can_manage_users(client, annotator, reviewer):
    for h in (annotator, reviewer):
        assert (await client.get("/api/users", headers=h)).status_code == 403
        r = await client.post("/api/users", headers=h, json={"username": "x1x", "role": "annotator", "password": "password123"})
        assert r.status_code == 403 and r.json()["code"] == "forbidden"


async def test_create_list_and_first_login_flow(client, admin):
    r = await client.post("/api/users", headers=admin, json={"username": "Carol", "role": "reviewer", "password": "temp-pass-1"})
    assert r.status_code == 201
    u = r.json()
    assert u["username"] == "carol" and u["must_change_password"] is True and u["active"] is True
    assert "password_hash" not in str(u) and "temp-pass-1" not in str(u)
    names = [x["username"] for x in (await client.get("/api/users", headers=admin)).json()]
    assert names == ["admin", "carol"]
    h = await login(client, "carol", "temp-pass-1")
    assert (await client.get("/api/experiments", headers=h)).status_code == 403  # must change password first


async def test_duplicate_username_and_validation(client, admin):
    body = {"username": "dave", "role": "annotator", "password": "password123"}
    assert (await client.post("/api/users", headers=admin, json=body)).status_code == 201
    r = await client.post("/api/users", headers=admin, json={**body, "username": "DAVE"})
    assert r.status_code == 409 and r.json()["code"] == "username_taken"
    for bad in ({"username": "ab"}, {"username": "has space"}, {"role": "root"}, {"password": "short"}):
        r = await client.post("/api/users", headers=admin, json={**body, "username": "erin", **bad})
        assert r.status_code == 422 and r.json()["code"] == "validation_error", bad


async def test_cannot_remove_the_last_admin(client, admin):
    me = (await client.get("/api/auth/me", headers=admin)).json()["id"]
    r = await client.patch(f"/api/users/{me}", headers=admin, json={"active": False})
    assert r.status_code == 409 and r.json()["code"] == "last_admin"
    r = await client.patch(f"/api/users/{me}", headers=admin, json={"role": "annotator"})
    assert r.status_code == 409
    other = await make_user("admin2", "admin")
    assert (await client.patch(f"/api/users/{me}", headers=admin, json={"role": "annotator"})).status_code == 200
    assert other.id


async def test_reset_password_returns_one_time_password_and_forces_change(client, admin):
    await make_user("alice")
    alice_h = await login(client, "alice")
    uid = (await client.get("/api/auth/me", headers=alice_h)).json()["id"]
    r = await client.post(f"/api/users/{uid}/reset-password", headers=admin)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    temp = r.json()["temporary_password"]
    assert len(temp) >= 12
    assert (await client.post("/api/auth/login", json={"username": "alice", "password": "password123"})).status_code == 401
    h = await login(client, "alice", temp)
    assert (await client.get("/api/auth/me", headers=h)).json()["must_change_password"] is True
    # earlier refresh sessions were revoked
    client.cookies.clear()
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_unknown_user_is_404(client, admin):
    r = await client.patch("/api/users/00000000-0000-0000-0000-000000000000", headers=admin, json={"active": False})
    assert r.status_code == 404 and r.json()["code"] == "not_found"
