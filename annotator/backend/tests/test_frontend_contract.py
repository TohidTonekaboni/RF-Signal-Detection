"""Pins the response shapes the React app relies on (see frontend/src/api/mock.js and features/*)."""
from tests.conftest import upload_image
from tests.test_experiments import CLASSES


async def test_shapes_match_what_the_frontend_reads(client, storage, admin):
    img = await upload_image(client, storage, admin, info={"duration_s": 1, "bandwidth_hz": 1e6, "center_freq_hz": 1e9})
    # LibraryPage / AnnotatePage: items[].{id,filename,url,thumb_url,width,height,size,created_at,meta}
    page = (await client.get("/api/images", headers=admin, params={"page": 1, "page_size": 12})).json()
    assert set(page) == {"items", "total", "page", "page_size"}
    assert {"id", "filename", "url", "thumb_url", "width", "height", "size", "created_at", "meta"} <= set(page["items"][0])
    assert {"duration_s", "bandwidth_hz", "center_freq_hz"} == set(img["meta"])  # units.js keys

    # ExperimentForm payload → ExperimentsPage / ReviewPage / DashboardPage
    e = (await client.post("/api/experiments", headers=admin, json={"name": "Wi-Fi", "description": "", "classes": CLASSES})).json()
    row = (await client.get("/api/experiments", headers=admin)).json()[0]
    assert {"id", "name", "description", "created_at", "classes", "image_count", "annotated_count"} <= set(row)
    assert {"id", "name", "color"} == set(row["classes"][0])
    stats = (await client.get(f"/api/experiments/{e['id']}/stats", headers=admin)).json()
    assert set(stats) == {"total", "annotated", "per_class"} and {"class_id", "name", "color", "count"} == set(stats["per_class"][0])
    assert set((await client.get(f"/api/experiments/{e['id']}/images", headers=admin)).json()) == {"items", "total"}

    # workspaceStore.load() / toPayload(): boxes[{id,class_id,x,y,w,h}], image_labels[names], version; nanoid-style box ids
    url = f"/api/experiments/{e['id']}/images/{img['id']}/annotations"
    assert set((await client.get(url, headers=admin)).json()) == {"boxes", "image_labels", "version"}
    payload = {"boxes": [{"id": "V1StGXR8_Z", "class_id": e["classes"][0]["id"], "x": 0.25, "y": 0.5, "w": 0.25, "h": 0.5}],
               "image_labels": ["Bluetooth"]}
    saved = (await client.put(url, headers={**admin, "If-Match": "1"}, json=payload)).json()
    assert saved == {**payload, "version": 2}

    # UsersPage: [{id,username,role,active,must_change_password}] and audit {items:[{id,at,actor,action}]}
    users = (await client.get("/api/users", headers=admin)).json()
    assert {"id", "username", "role", "active", "must_change_password"} == set(users[0])
    audit_page = (await client.get("/api/audit", headers=admin, params={})).json()
    assert audit_page["page_size"] == 100 and {"id", "at", "actor", "action"} <= set(audit_page["items"][0])

    # client.js: every error is {code, message}; 204 has no body
    err = await client.get("/api/experiments/00000000-0000-0000-0000-000000000000", headers=admin)
    assert set(err.json()) == {"code", "message"}
    assert (await client.post("/api/auth/logout")).content == b""
