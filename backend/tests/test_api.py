"""FastAPI integration tests covering auth, masked secrets, theme persistence, and SSRF."""

from __future__ import annotations

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_api_auth_secrets_theme_and_ssrf(tmp_settings: Settings) -> None:
    app = create_app(tmp_settings)
    headers = {"Authorization": f"Bearer {tmp_settings.web_admin_token}"}

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200

        # Unauthenticated request must fail closed
        unauth = client.get("/api/v1/overview")
        assert unauth.status_code == 401
        assert unauth.json()["error"]["code"] == "UNAUTHORIZED"

        # Save encrypted secret -> masked hint returned, never plaintext
        sec_resp = client.put(
            "/api/v1/secrets/gemini", headers=headers, json={"value": "AIzaSyTopSecret9876"}
        )
        assert sec_resp.status_code == 200
        assert sec_resp.json()["hint"] == "AIza...9876"

        ov = client.get("/api/v1/overview", headers=headers)
        assert ov.status_code == 200
        assert "AIzaSyTopSecret9876" not in ov.text
        assert ov.json()["secrets"]["gemini"]["hint"] == "AIza...9876"

        # Update theme preset & custom colors
        theme_payload = {
            "mode": "dark",
            "preset": "night-owl",
            "accent": "#82aaff",
            "background": "#011627",
            "foreground": "#d6deeb",
            "fontFamily": "mono",
            "radius": "md",
            "language": "vi",
        }
        th = client.put("/api/v1/settings/theme", headers=headers, json=theme_payload)
        assert th.status_code == 200
        assert th.json()["preset"] == "night-owl"

        # SSRF blocked on digest endpoint
        ssrf_resp = client.post(
            "/api/v1/digest", headers=headers, json={"url": "http://127.0.0.1:8000/ready"}
        )
        assert ssrf_resp.status_code == 400
        assert ssrf_resp.json()["error"]["code"] == "UNSAFE_URL"

        # CRUD lifecycle: note edit + delete, transaction edit + delete, secret delete
        note = client.post(
            "/api/v1/notes",
            headers=headers,
            json={"title": "Ban đầu", "content": "Nội dung 1", "tags": "tag1"},
        )
        assert note.status_code == 201
        note_id = note.json()["id"]
        edited_note = client.put(
            f"/api/v1/notes/{note_id}",
            headers=headers,
            json={"title": "Đã sửa", "content": "Nội dung mới", "tags": "tag2"},
        )
        assert edited_note.status_code == 200
        assert edited_note.json()["title"] == "Đã sửa"
        assert client.delete(f"/api/v1/notes/{note_id}", headers=headers).status_code == 200

        tx = client.post(
            "/api/v1/finance/transactions",
            headers=headers,
            json={"kind": "expense", "amount": "55k", "category": "Ăn uống", "note": "Cơm"},
        )
        assert tx.status_code == 201
        tx_id = tx.json()["id"]
        edited_tx = client.put(
            f"/api/v1/finance/transactions/{tx_id}",
            headers=headers,
            json={"kind": "expense", "amount": "75k", "category": "Ăn uống", "note": "Cơm thêm"},
        )
        assert edited_tx.status_code == 200
        assert edited_tx.json()["amount_minor"] == 75000

        del_sec = client.delete("/api/v1/secrets/gemini", headers=headers)
        assert del_sec.status_code == 200
        assert del_sec.json()["configured"] is False
        assert client.delete("/api/v1/audit-logs", headers=headers).status_code == 200

        brief_upd = client.put(
            "/api/v1/settings/briefing",
            headers=headers,
            json={"enabled": True, "time_hhmm": "08:15"},
        )
        assert brief_upd.status_code == 200
        assert brief_upd.json()["enabled"] is True
        assert brief_upd.json()["time_hhmm"] == "08:15"
