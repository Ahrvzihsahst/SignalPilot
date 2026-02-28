"""Tests for strategies API."""



class TestStrategyComparison:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/comparison")
        assert resp.status_code == 200

    async def test_has_strategies_list(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/comparison")
        data = resp.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)

    async def test_strategy_metrics_fields(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/comparison")
        strategies = resp.json()["strategies"]
        if strategies:
            s = strategies[0]
            for field in ("strategy", "total_signals", "total_trades",
                          "wins", "losses", "win_rate", "total_pnl"):
                assert field in s

    async def test_includes_all_strategies_with_data(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/comparison")
        strategies = resp.json()["strategies"]
        names = {s["strategy"] for s in strategies}
        # We seeded signals for all 3 strategies
        assert "gap_go" in names

    async def test_empty_comparison(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/strategies/comparison")
        assert resp.status_code == 200
        assert resp.json()["strategies"] == []


class TestConfirmedPerformance:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/confirmed")
        assert resp.status_code == 200

    async def test_has_single_and_multi(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/confirmed")
        data = resp.json()
        assert "single_signals" in data
        assert "multi_signals" in data
        assert "single_win_rate" in data
        assert "multi_win_rate" in data

    async def test_empty_confirmed(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/strategies/confirmed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["single_signals"] == 0
        assert data["multi_signals"] == 0


class TestStrategyPnlSeries:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/pnl-series")
        assert resp.status_code == 200

    async def test_data_points_structure(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/pnl-series")
        data = resp.json()["data"]
        if data:
            point = data[0]
            assert "date" in point
            assert "strategy" in point
            assert "pnl" in point

    async def test_days_param(self, seeded_client):
        resp = await seeded_client.get("/api/strategies/pnl-series?days=7")
        assert resp.status_code == 200
