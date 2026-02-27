"""Tests for adaptation API."""



class TestAdaptationStatus:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/status")
        assert resp.status_code == 200

    async def test_has_mode_and_flags(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/status")
        data = resp.json()
        assert "mode" in data
        assert "auto_rebalance_enabled" in data
        assert "adaptive_learning_enabled" in data

    async def test_has_strategies_list(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/status")
        data = resp.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)

    async def test_strategy_status_fields(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/status")
        strategies = resp.json()["strategies"]
        if strategies:
            s = strategies[0]
            assert "strategy" in s
            assert "enabled" in s
            assert "current_weight_pct" in s
            assert "recent_win_rate" in s

    async def test_includes_all_default_strategies(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/status")
        strategies = resp.json()["strategies"]
        names = {s["strategy"] for s in strategies}
        assert "gap_go" in names
        assert "ORB" in names
        assert "VWAP Reversal" in names

    async def test_default_status_no_config(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/adaptation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "aggressive"


class TestAdaptationLog:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log")
        assert resp.status_code == 200

    async def test_has_data_and_pagination(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log")
        data = resp.json()
        assert "data" in data
        assert "pagination" in data

    async def test_log_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log")
        items = resp.json()["data"]
        assert len(items) >= 1
        item = items[0]
        assert "id" in item
        assert "date" in item
        assert "strategy" in item
        assert "event_type" in item
        assert "details" in item
        assert "old_weight" in item
        assert "new_weight" in item

    async def test_strategy_filter(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log?strategy=gap_go")
        items = resp.json()["data"]
        for item in items:
            assert item["strategy"] == "gap_go"

    async def test_event_type_filter(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log?event_type=rebalance")
        items = resp.json()["data"]
        for item in items:
            assert item["event_type"] == "rebalance"

    async def test_pagination(self, seeded_client):
        resp = await seeded_client.get("/api/adaptation/log?page=1&page_size=1")
        data = resp.json()
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 1

    async def test_empty_log(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/adaptation/log")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["pagination"]["total_items"] == 0
