from tests.conftest import upload_image

CLASSES = [{"name": "Wi-Fi", "color": "#E69F00"}, {"name": "Bluetooth", "color": "#56B4E9"}]


async def make_exp(client, admin, **over):
    body = {"name": "Wi-Fi detection", "description": "d", "classes": CLASSES, **over}
    r = await client.post("/api/experiments", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_includes_existing_images_and_returns_class_ids(client, storage, admin):
    for i in range(3):
        await upload_image(client, storage, admin, seed=i)
    e = await make_exp(client, admin)
    assert e["image_count"] == 3 and e["annotated_count"] == 0
    assert [c["name"] for c in e["classes"]] == ["Wi-Fi", "Bluetooth"]  # order preserved
    assert all(c["id"] and c["color"].startswith("#") for c in e["classes"])
    got = (await client.get(f"/api/experiments/{e['id']}", headers=admin)).json()
    assert got["classes"] == e["classes"]
    items = (await client.get(f"/api/experiments/{e['id']}/images", headers=admin)).json()
    assert items["total"] == 3 and all("url" in i and i["annotated"] is False for i in items["items"])


async def test_only_admin_creates_but_everyone_reads(client, annotator, reviewer, admin):
    for h in (annotator, reviewer):
        r = await client.post("/api/experiments", headers=h, json={"name": "nope", "classes": CLASSES})
        assert r.status_code == 403
    e = await make_exp(client, admin)
    for h in (annotator, reviewer):
        assert len((await client.get("/api/experiments", headers=h)).json()) == 1
        assert (await client.get(f"/api/experiments/{e['id']}", headers=h)).status_code == 200


async def test_experiment_validation_mirrors_frontend_schema(client, admin):
    bad_bodies = [
        {"name": "x", "classes": CLASSES},
        {"name": "ok name", "classes": []},
        {"name": "ok name", "classes": [{"name": "A", "color": "red"}]},
        {"name": "ok name", "classes": [{"name": "A", "color": "#112233"}, {"name": "a", "color": "#445566"}]},
        {"name": "ok name", "classes": [{"name": "  ", "color": "#112233"}]},
    ]
    for b in bad_bodies:
        r = await client.post("/api/experiments", headers=admin, json=b)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", b


async def test_stats_and_counts_follow_annotations(client, storage, admin):
    imgs = [await upload_image(client, storage, admin, seed=i) for i in range(2)]
    e = await make_exp(client, admin)
    wifi, bt = e["classes"][0]["id"], e["classes"][1]["id"]
    boxes = [{"id": "b1", "class_id": wifi, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
             {"id": "b2", "class_id": wifi, "x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2},
             {"id": "b3", "class_id": bt, "x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]
    r = await client.put(f"/api/experiments/{e['id']}/images/{imgs[0]['id']}/annotations",
                         headers={**admin, "If-Match": "1"}, json={"boxes": boxes, "image_labels": []})
    assert r.status_code == 200
    s = (await client.get(f"/api/experiments/{e['id']}/stats", headers=admin)).json()
    assert s["total"] == 2 and s["annotated"] == 1
    assert {p["name"]: p["count"] for p in s["per_class"]} == {"Wi-Fi": 2, "Bluetooth": 1}
    assert [p["name"] for p in s["per_class"]] == ["Wi-Fi", "Bluetooth"]
    listed = (await client.get("/api/experiments", headers=admin)).json()[0]
    assert (listed["image_count"], listed["annotated_count"]) == (2, 1)
    flags = {i["id"]: i["annotated"] for i in (await client.get(f"/api/experiments/{e['id']}/images", headers=admin)).json()["items"]}
    assert flags == {imgs[0]["id"]: True, imgs[1]["id"]: False}


async def test_deleted_images_leave_counts(client, storage, admin):
    img = await upload_image(client, storage, admin)
    e = await make_exp(client, admin)
    await client.delete(f"/api/images/{img['id']}", headers=admin)
    assert (await client.get(f"/api/experiments/{e['id']}", headers=admin)).json()["image_count"] == 0
    assert (await client.get(f"/api/experiments/{e['id']}/stats", headers=admin)).json()["total"] == 0


async def test_add_images_later(client, storage, admin):
    e = await make_exp(client, admin)
    assert e["image_count"] == 0
    a = await upload_image(client, storage, admin, seed=1)
    await upload_image(client, storage, admin, seed=2)
    r = await client.post(f"/api/experiments/{e['id']}/images", headers=admin, json={"image_ids": [a["id"]]})
    assert r.json() == {"added": 1}
    r = await client.post(f"/api/experiments/{e['id']}/images", headers=admin, json={"all": True})
    assert r.json() == {"added": 1}  # only the missing one
    assert (await client.post(f"/api/experiments/{e['id']}/images", headers=admin, json={})).status_code == 422
    assert (await client.get(f"/api/experiments/{e['id']}", headers=admin)).json()["image_count"] == 2


async def test_update_classes_rename_add_swap_and_protect_used(client, storage, admin):
    img = await upload_image(client, storage, admin)
    e = await make_exp(client, admin)
    wifi, bt = e["classes"]
    # swap names + recolor + add one
    r = await client.put(f"/api/experiments/{e['id']}", headers=admin, json={"name": "Renamed", "classes": [
        {"id": bt["id"], "name": "Wi-Fi", "color": "#111111"},
        {"id": wifi["id"], "name": "Bluetooth", "color": "#222222"},
        {"name": "LTE", "color": "#333333"}]})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["name"] == "Renamed" and [c["name"] for c in got["classes"]] == ["Wi-Fi", "Bluetooth", "LTE"]
    assert got["classes"][0]["id"] == bt["id"] and got["classes"][0]["color"] == "#111111"
    # use LTE, then try to delete it
    lte = got["classes"][2]["id"]
    await client.put(f"/api/experiments/{e['id']}/images/{img['id']}/annotations", headers={**admin, "If-Match": "1"},
                     json={"boxes": [{"id": "b1", "class_id": lte, "x": 0, "y": 0, "w": .5, "h": .5}], "image_labels": []})
    r = await client.put(f"/api/experiments/{e['id']}", headers=admin, json={"classes": got["classes"][:2]})
    assert r.status_code == 409 and r.json()["code"] == "class_in_use"
    # unused ones can go
    r = await client.put(f"/api/experiments/{e['id']}", headers=admin, json={"classes": [got["classes"][0], got["classes"][2]]})
    assert r.status_code == 200 and [c["name"] for c in r.json()["classes"]] == ["Wi-Fi", "LTE"]
    # unknown class id
    r = await client.put(f"/api/experiments/{e['id']}", headers=admin, json={"classes": [{"id": "00000000-0000-0000-0000-000000000000", "name": "X", "color": "#111111"}]})
    assert r.status_code == 422


async def test_unknown_experiment_404(client, admin):
    for path in ("", "/stats", "/images"):
        r = await client.get(f"/api/experiments/00000000-0000-0000-0000-000000000000{path}", headers=admin)
        assert r.status_code == 404 and r.json()["code"] == "not_found"
