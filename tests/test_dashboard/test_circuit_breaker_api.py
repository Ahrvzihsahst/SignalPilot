"""Tests for circuit breaker API."""



class TestCircuitBreakerStatus:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker")
        assert resp.status_code == 200

    async def test_has_status_fields(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker")
        data = resp.json()
        assert "date" in data
        assert "sl_count" in data
        assert "sl_limit" in data
        assert "is_active" in data
        assert "is_overridden" in data

    async def test_triggered_breaker(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker")
        data = resp.json()
        # We seeded a triggered breaker
        assert data["sl_count"] == 3
        assert data["triggered_at"] is not None

    async def test_no_breaker(self, api_client):
        client, conn = api_client
        from datetime import datetime

        from signalpilot.utils.constants import IST

        now = datetime.now(IST)
        await conn.execute(
            """INSERT INTO user_config
                   (telegram_chat_id, total_capital, max_positions, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("123", 50000, 8, now.isoformat(), now.isoformat()),
        )
        await conn.commit()
        resp = await client.get("/api/circuit-breaker")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        assert data["sl_count"] == 0


class TestCircuitBreakerOverride:
    async def test_override_returns_200(self, seeded_client):
        resp = await seeded_client.post(
            "/api/circuit-breaker/override",
            json={"action": "override"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_reset_returns_200(self, seeded_client):
        resp = await seeded_client.post(
            "/api/circuit-breaker/override",
            json={"action": "reset"},
        )
        assert resp.status_code == 200

    async def test_invalid_action_rejected(self, seeded_client):
        resp = await seeded_client.post(
            "/api/circuit-breaker/override",
            json={"action": "invalid"},
        )
        assert resp.status_code == 422


class TestCircuitBreakerHistory:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker/history")
        assert resp.status_code == 200

    async def test_has_data(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker/history")
        data = resp.json()["data"]
        assert len(data) >= 1

    async def test_history_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker/history")
        data = resp.json()["data"]
        if data:
            item = data[0]
            assert "date" in item
            assert "sl_count" in item
            assert "triggered_at" in item
            assert "manual_override" in item

    async def test_limit_param(self, seeded_client):
        resp = await seeded_client.get("/api/circuit-breaker/history?limit=1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) <= 1
