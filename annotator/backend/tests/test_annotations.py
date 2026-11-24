import asyncio

from tests.conftest import upload_image
from tests.test_experiments import make_exp


async def setup(client, storage, admin):
    img = await upload_image(client, storage, admin)
    e = await make_exp(client, admin)
    return e, img, f"/api/experiments/{e['id']}/images/{img['id']}/annotations"


def box(cid, bid="b1", **kw):
    return {"id": bid, "class_id": cid, "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, **kw}


async def test_fresh_image_has_empty_annotations_at_version_1(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    r = await client.get(url, headers=admin)
    assert r.status_code == 200 and r.json() == {"boxes": [], "image_labels": [], "version": 1}
    assert r.headers["etag"] == '"1"'


async def test_save_roundtrip_bumps_version_and_preserves_client_ids_and_order(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    wifi, bt = (c["id"] for c in e["classes"])
    body = {"boxes": [box(bt, "zz9"), box(wifi, "aa1", x=0.5)], "image_labels": ["Wi-Fi"]}
    r = await client.put(url, headers={**admin, "If-Match": "1"}, json=body)
    assert r.status_code == 200 and r.json()["version"] == 2 and r.headers["etag"] == '"2"'
    got = (await client.get(url, headers=admin)).json()
    assert [b["id"] for b in got["boxes"]] == ["zz9", "aa1"]  # client ids + order echoed back
    assert got["boxes"][1]["x"] == 0.5 and got["image_labels"] == ["Wi-Fi"] and got["version"] == 2


async def test_save_replaces_the_whole_set(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    await client.put(url, headers={**admin, "If-Match": "1"}, json={"boxes": [box(wifi, "a"), box(wifi, "b")], "image_labels": []})
    r = await client.put(url, headers={**admin, "If-Match": "2"}, json={"boxes": [box(wifi, "b")], "image_labels": []})
    assert [b["id"] for b in r.json()["boxes"]] == ["b"]
    r = await client.put(url, headers={**admin, "If-Match": "3"}, json={"boxes": [], "image_labels": []})
    assert r.json() == {"boxes": [], "image_labels": [], "version": 4}


async def test_stale_version_conflicts_with_409(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    await client.put(url, headers={**admin, "If-Match": "1"}, json={"boxes": [box(wifi)], "image_labels": []})
    r = await client.put(url, headers={**admin, "If-Match": "1"}, json={"boxes": [], "image_labels": []})
    assert r.status_code == 409 and r.json()["code"] == "conflict" and r.json()["details"]["current_version"] == 2
    assert len((await client.get(url, headers=admin)).json()["boxes"]) == 1  # losing write changed nothing


async def test_if_match_is_required_and_accepts_etag_form(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    r = await client.put(url, headers=admin, json={"boxes": [], "image_labels": []})
    assert r.status_code == 428 and r.json()["code"] == "precondition_required"
    r = await client.put(url, headers={**admin, "If-Match": "abc"}, json={"boxes": [], "image_labels": []})
    assert r.status_code == 400
    r = await client.put(url, headers={**admin, "If-Match": '"1"'}, json={"boxes": [], "image_labels": []})
    assert r.status_code == 200


async def test_concurrent_saves_exactly_one_wins(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    h = {**admin, "If-Match": "1"}
    rs = await asyncio.gather(*(client.put(url, headers=h, json={"boxes": [box(wifi, f"b{i}")], "image_labels": []}) for i in range(4)))
    codes = sorted(r.status_code for r in rs)
    assert codes == [200, 409, 409, 409], codes
    assert len((await client.get(url, headers=admin)).json()["boxes"]) == 1


async def test_validation(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    h = {**admin, "If-Match": "1"}
    bad = [
        {"boxes": [box("00000000-0000-0000-0000-000000000000")], "image_labels": []},   # foreign class
        {"boxes": [box(wifi, x=0.9, w=0.3)], "image_labels": []},                        # outside the image
        {"boxes": [box(wifi, w=0)], "image_labels": []},                                 # zero size
        {"boxes": [box(wifi, x=-0.1)], "image_labels": []},
        {"boxes": [box(wifi, "dup"), box(wifi, "dup")], "image_labels": []},             # duplicate ids
        {"boxes": [box(wifi, "bad id!")], "image_labels": []},
        {"boxes": [], "image_labels": ["NotAClass"]},
        {"boxes": [], "image_labels": ["Wi-Fi", "Wi-Fi"]},
        {"boxes": [{"id": "a"}], "image_labels": []},
    ]
    for b in bad:
        r = await client.put(url, headers=h, json=b)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", b
    assert (await client.get(url, headers=admin)).json()["version"] == 1
    ok = await client.put(url, headers=h, json={"boxes": [box(wifi, x=0.7, w=0.3)], "image_labels": []})  # touches the edge
    assert ok.status_code == 200


async def test_roles(client, storage, admin, annotator, reviewer):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    body = {"boxes": [box(wifi)], "image_labels": []}
    assert (await client.put(url, headers={**reviewer, "If-Match": "1"}, json=body)).status_code == 403
    assert (await client.get(url, headers=reviewer)).status_code == 200
    assert (await client.put(url, headers={**annotator, "If-Match": "1"}, json=body)).status_code == 200


async def test_image_not_in_experiment_or_deleted_is_404(client, storage, admin):
    e, img, url = await setup(client, storage, admin)
    other = await upload_image(client, storage, admin, seed=99)  # uploaded after the experiment was created
    r = await client.get(f"/api/experiments/{e['id']}/images/{other['id']}/annotations", headers=admin)
    assert r.status_code == 404
    await client.delete(f"/api/images/{img['id']}", headers=admin)
    assert (await client.get(url, headers=admin)).status_code == 404


async def test_save_is_audited_and_visible_to_admin_only(client, storage, admin, annotator):
    e, img, url = await setup(client, storage, admin)
    wifi = e["classes"][0]["id"]
    await client.put(url, headers={**annotator, "If-Match": "1"}, json={"boxes": [box(wifi)], "image_labels": []})
    assert (await client.get("/api/audit", headers=annotator)).status_code == 403
    log = (await client.get("/api/audit", headers=admin)).json()
    saves = [a for a in log["items"] if a["action"] == f"annotations.save {img['id']}"]
    assert len(saves) == 1 and saves[0]["actor"] == "ann" and saves[0]["at"].endswith("Z")
    assert {"id", "at", "actor", "action"} <= set(saves[0])
    assert log["total"] >= 3 and log["page"] == 1
    only = (await client.get("/api/audit", headers=admin, params={"actor": "ann"})).json()
    assert {a["actor"] for a in only["items"]} == {"ann"}
