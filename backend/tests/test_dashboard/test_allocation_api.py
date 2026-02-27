"""Tests for allocation API."""



class TestCurrentAllocation:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/current")
        assert resp.status_code == 200

    async def test_has_total_capital(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/current")
        data = resp.json()
        assert data["total_capital"] == 100000.0

    async def test_has_allocations(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/current")
        data = resp.json()
        assert "allocations" in data
        assert isinstance(data["allocations"], list)
        assert len(data["allocations"]) > 0

    async def test_allocation_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/current")
        allocs = resp.json()["allocations"]
        for item in allocs:
            assert "strategy" in item
            assert "weight_pct" in item
            assert "capital_allocated" in item

    async def test_default_allocation_when_no_data(self, api_client):
        """When there is no strategy_performance data, returns equal weights."""
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
        resp = await client.get("/api/allocation/current")
        assert resp.status_code == 200
        allocs = resp.json()["allocations"]
        assert len(allocs) == 3  # 3 default strategies


class TestAllocationHistory:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/history")
        assert resp.status_code == 200

    async def test_has_data(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/history")
        data = resp.json()["data"]
        assert len(data) > 0

    async def test_history_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/allocation/history")
        data = resp.json()["data"]
        if data:
            item = data[0]
            assert "date" in item
            assert "strategy" in item
            assert "weight_pct" in item


class TestAllocationOverride:
    async def test_override_returns_200(self, seeded_client):
        resp = await seeded_client.post(
            "/api/allocation/override",
            json={"strategy": "gap_go", "weight_pct": 50.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_override_updates_weight(self, seeded_client):
        await seeded_client.post(
            "/api/allocation/override",
            json={"strategy": "gap_go", "weight_pct": 60.0},
        )
        resp = await seeded_client.get("/api/allocation/current")
        allocs = resp.json()["allocations"]
        gap_go = next((a for a in allocs if a["strategy"] == "gap_go"), None)
        assert gap_go is not None
        assert gap_go["weight_pct"] == 60.0


class TestAllocationReset:
    async def test_reset_returns_200(self, seeded_client):
        resp = await seeded_client.post("/api/allocation/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
