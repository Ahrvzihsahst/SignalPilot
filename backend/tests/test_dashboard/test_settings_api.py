"""Tests for settings API."""



class TestGetSettings:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/settings")
        assert resp.status_code == 200

    async def test_settings_fields(self, seeded_client):
        resp = await seeded_client.get("/api/settings")
        data = resp.json()
        assert data["total_capital"] == 100000.0
        assert data["max_positions"] == 8
        assert "gap_go_enabled" in data
        assert "orb_enabled" in data
        assert "vwap_enabled" in data

    async def test_phase3_settings(self, seeded_client):
        resp = await seeded_client.get("/api/settings")
        data = resp.json()
        assert "circuit_breaker_limit" in data
        assert "confidence_boost_enabled" in data
        assert "adaptive_learning_enabled" in data
        assert "auto_rebalance_enabled" in data
        assert "adaptation_mode" in data

    async def test_default_settings_no_config(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_capital"] == 50000.0


class TestUpdateSettings:
    async def test_update_capital(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings",
            json={"total_capital": 200000.0},
        )
        assert resp.status_code == 200

        # Verify update
        resp2 = await seeded_client.get("/api/settings")
        assert resp2.json()["total_capital"] == 200000.0

    async def test_update_max_positions(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings",
            json={"max_positions": 10},
        )
        assert resp.status_code == 200

    async def test_update_phase3_field(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings",
            json={"circuit_breaker_limit": 5},
        )
        assert resp.status_code == 200

    async def test_update_adaptation_mode(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings",
            json={"adaptation_mode": "conservative"},
        )
        assert resp.status_code == 200


class TestStrategyToggles:
    async def test_toggle_strategy(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings/strategies",
            json={"gap_go_enabled": False},
        )
        assert resp.status_code == 200

    async def test_toggle_multiple_strategies(self, seeded_client):
        resp = await seeded_client.put(
            "/api/settings/strategies",
            json={"orb_enabled": False, "vwap_enabled": False},
        )
        assert resp.status_code == 200
