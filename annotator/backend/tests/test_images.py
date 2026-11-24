from datetime import timedelta

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.db.types import utcnow
from app.models import Image
from tests.conftest import png_bytes, upload_image


async def test_upload_flow_presign_put_complete(client, storage, annotator):
    data = png_bytes(1, size=(80, 40))
    r = await client.post("/api/images/presign", headers=annotator,
                          json={"filename": "../../etc/passwd.png", "content_type": "image/png", "size": len(data)})
    assert r.status_code == 201
    url, image_id = r.json()["upload_url"], r.json()["image_id"]
    assert "passwd" not in url  # storage key never derives from the user-supplied filename
    # not visible while pending
    assert (await client.get("/api/images", headers=annotator)).json()["total"] == 0
    storage.browser_upload(url, data)
    done = await client.post(f"/api/images/{image_id}/complete", headers=annotator)
    assert done.status_code == 200
    img = done.json()
    assert (img["width"], img["height"]) == (80, 40) and img["size"] == len(data)
    assert img["url"].startswith("https://files.test/get/images/") and img["thumb_url"].startswith("https://files.test/get/thumbs/")
    assert img["uploaded_by"] == "ann" and img["content_type"] == "image/png" and img["meta"] == {}
    assert any(b == "thumbs" for b, _ in storage.objects)
    # idempotent retry
    assert (await client.post(f"/api/images/{image_id}/complete", headers=annotator)).json()["id"] == image_id
    assert (await client.get("/api/images", headers=annotator)).json()["total"] == 1


async def test_png_text_chunks_become_physical_metadata(client, storage, annotator):
    img = await upload_image(client, storage, annotator, info={"duration_s": "0.5", "bandwidth_hz": "20e6", "center_freq_hz": "2.437e9", "junk": "x"})
    assert img["meta"] == {"duration_s": 0.5, "bandwidth_hz": 20e6, "center_freq_hz": 2.437e9}


async def test_rejects_non_image_bytes_and_cleans_up(client, storage, annotator):
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 20})
    storage.browser_upload(r.json()["upload_url"], b"<html><script>alert(1)</script></html>")
    bad = await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=annotator)
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_image"
    assert not storage.objects
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(Image))).first() is None


async def test_rejects_gif_even_if_declared_png(client, storage, annotator):
    import io

    from PIL import Image as P
    buf = io.BytesIO()
    P.new("P", (4, 4)).save(buf, format="GIF")
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 10})
    storage.browser_upload(r.json()["upload_url"], buf.getvalue())
    assert (await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=annotator)).status_code == 422


async def test_presign_validation(client, annotator):
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.svg", "content_type": "image/svg+xml", "size": 10})
    assert r.status_code == 415 and r.json()["code"] == "unsupported_media_type"
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 5 * 1024 * 1024})
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 0})
    assert r.status_code == 422


async def test_oversized_object_is_discarded_on_complete(client, storage, annotator):
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 100})
    storage.browser_upload(r.json()["upload_url"], b"x" * (2 * 1024 * 1024))  # client lied about size
    bad = await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=annotator)
    assert bad.status_code == 413 and not storage.objects


async def test_complete_without_upload_is_400(client, annotator):
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 100})
    bad = await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=annotator)
    assert bad.status_code == 400 and bad.json()["code"] == "upload_missing"


async def test_duplicate_content_is_rejected(client, storage, annotator):
    first = await upload_image(client, storage, annotator, seed=3)
    data = png_bytes(3)
    r = await client.post("/api/images/presign", headers=annotator, json={"filename": "copy.png", "content_type": "image/png", "size": len(data)})
    storage.browser_upload(r.json()["upload_url"], data)
    dup = await client.post(f"/api/images/{r.json()['image_id']}/complete", headers=annotator)
    assert dup.status_code == 409 and dup.json()["code"] == "duplicate_image"
    assert dup.json()["details"]["existing_id"] == first["id"]
    assert (await client.get("/api/images", headers=annotator)).json()["total"] == 1


async def test_reviewer_cannot_upload_and_others_cannot_complete_my_upload(client, storage, annotator, reviewer, admin):
    r = await client.post("/api/images/presign", headers=reviewer, json={"filename": "a.png", "content_type": "image/png", "size": 10})
    assert r.status_code == 403
    pre = await client.post("/api/images/presign", headers=annotator, json={"filename": "a.png", "content_type": "image/png", "size": 10})
    from tests.conftest import login, make_user
    await make_user("ann2")
    h2 = await login(client, "ann2")
    assert (await client.post(f"/api/images/{pre.json()['image_id']}/complete", headers=h2)).status_code == 404


async def test_list_pagination_search_and_date_filter(client, storage, annotator):
    ids = []
    for i in range(5):
        ids.append((await upload_image(client, storage, annotator, seed=i, filename=f"capture_{i}.png"))["id"])
    # spread created_at over five days so date filters are meaningful
    base = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    async with get_sessionmaker()() as db:
        for i, iid in enumerate(ids):
            (await db.get(Image, __import__("uuid").UUID(iid))).created_at = base - timedelta(days=i)
        await db.commit()

    p1 = (await client.get("/api/images", headers=annotator, params={"page": 1, "page_size": 2})).json()
    assert p1["total"] == 5 and p1["page"] == 1 and p1["page_size"] == 2
    assert [i["filename"] for i in p1["items"]] == ["capture_0.png", "capture_1.png"]  # newest first
    p3 = (await client.get("/api/images", headers=annotator, params={"page": 3, "page_size": 2})).json()
    assert [i["filename"] for i in p3["items"]] == ["capture_4.png"]

    only = (await client.get("/api/images", headers=annotator, params={"q": "ure_3"})).json()
    assert [i["filename"] for i in only["items"]] == ["capture_3.png"]
    assert (await client.get("/api/images", headers=annotator, params={"q": "%"})).json()["total"] == 0  # wildcard is escaped

    frm = (base - timedelta(days=3, hours=1)).isoformat().replace("+00:00", "Z")
    to = (base - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    rng = (await client.get("/api/images", headers=annotator, params={"from": frm, "to": to})).json()
    assert sorted(i["filename"] for i in rng["items"]) == ["capture_1.png", "capture_2.png", "capture_3.png"]  # inclusive ends
    assert (await client.get("/api/images", headers=annotator, params={"page_size": 500})).status_code == 422


async def test_delete_is_admin_only_and_soft(client, storage, annotator, admin):
    img = await upload_image(client, storage, annotator)
    assert (await client.delete(f"/api/images/{img['id']}", headers=annotator)).status_code == 403
    assert (await client.delete(f"/api/images/{img['id']}", headers=admin)).status_code == 204
    assert (await client.get("/api/images", headers=annotator)).json()["total"] == 0
    assert (await client.get(f"/api/images/{img['id']}", headers=annotator)).status_code == 404
    async with get_sessionmaker()() as db:
        row = await db.get(Image, __import__("uuid").UUID(img["id"]))
        assert row is not None and row.deleted_at is not None  # row kept until housekeeping
    assert storage.objects  # objects too
    # the same bytes can be uploaded again after deletion
    await upload_image(client, storage, annotator)


async def test_patch_meta(client, storage, annotator):
    img = await upload_image(client, storage, annotator)
    r = await client.patch(f"/api/images/{img['id']}", headers=annotator, json={"meta": {"duration_s": 2, "bandwidth_hz": 1e6}})
    assert r.status_code == 200 and r.json()["meta"] == {"duration_s": 2.0, "bandwidth_hz": 1e6}
    r = await client.patch(f"/api/images/{img['id']}", headers=annotator, json={"meta": {"duration_s": -1}})
    assert r.status_code == 422
