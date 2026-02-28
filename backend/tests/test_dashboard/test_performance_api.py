"""Tests for performance API."""



class TestEquityCurve:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/performance/equity-curve")
        assert resp.status_code == 200

    async def test_has_data_key(self, seeded_client):
        resp = await seeded_client.get("/api/performance/equity-curve")
        data = resp.json()
        assert "data" in data

    async def test_data_points_have_date_and_pnl(self, seeded_client):
        resp = await seeded_client.get("/api/performance/equity-curve")
        points = resp.json()["data"]
        if points:
            assert "date" in points[0]
            assert "cumulative_pnl" in points[0]

    async def test_cumulative_pnl_is_running_total(self, seeded_client):
        resp = await seeded_client.get("/api/performance/equity-curve")
        points = resp.json()["data"]
        # The last point should be the total P&L
        if len(points) >= 1:
            # With seeded data: 500 + (-200) = 300
            assert points[-1]["cumulative_pnl"] == 300.0

    async def test_empty_data(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/performance/equity-curve")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestDailyPnl:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/performance/daily-pnl")
        assert resp.status_code == 200

    async def test_data_points_structure(self, seeded_client):
        resp = await seeded_client.get("/api/performance/daily-pnl")
        points = resp.json()["data"]
        if points:
            assert "date" in points[0]
            assert "pnl" in points[0]
            assert "trades_count" in points[0]

    async def test_daily_pnl_calculation(self, seeded_client):
        resp = await seeded_client.get("/api/performance/daily-pnl")
        points = resp.json()["data"]
        if points:
            # 500 + (-200) = 300 total for the day
            assert points[0]["pnl"] == 300.0

    async def test_days_param(self, seeded_client):
        resp = await seeded_client.get("/api/performance/daily-pnl?days=7")
        assert resp.status_code == 200


class TestWinRate:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/performance/win-rate")
        assert resp.status_code == 200

    async def test_data_points_structure(self, seeded_client):
        resp = await seeded_client.get("/api/performance/win-rate")
        points = resp.json()["data"]
        if points:
            assert "date" in points[0]
            assert "win_rate" in points[0]
            assert "trades_count" in points[0]

    async def test_win_rate_calculation(self, seeded_client):
        resp = await seeded_client.get("/api/performance/win-rate")
        points = resp.json()["data"]
        if points:
            # 1 win out of 2 closed trades = 50%
            assert points[0]["win_rate"] == 50.0


class TestMonthlySummary:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/performance/monthly")
        assert resp.status_code == 200

    async def test_monthly_structure(self, seeded_client):
        resp = await seeded_client.get("/api/performance/monthly")
        data = resp.json()["data"]
        if data:
            row = data[0]
            assert "month" in row
            assert "total_pnl" in row
            assert "trades_count" in row
            assert "wins" in row
            assert "losses" in row
            assert "win_rate" in row

    async def test_empty_monthly(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/performance/monthly")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
