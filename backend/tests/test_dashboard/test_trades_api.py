"""Tests for trades API."""



class TestGetTrades:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/trades")
        assert resp.status_code == 200

    async def test_has_trades_and_summary(self, seeded_client):
        resp = await seeded_client.get("/api/trades")
        data = resp.json()
        assert "trades" in data
        assert "summary" in data
        assert "pagination" in data

    async def test_summary_fields(self, seeded_client):
        resp = await seeded_client.get("/api/trades")
        summary = resp.json()["summary"]
        assert "total_trades" in summary
        assert "open_trades" in summary
        assert "closed_trades" in summary
        assert "total_pnl" in summary
        assert "wins" in summary
        assert "losses" in summary
        assert "win_rate" in summary

    async def test_summary_counts(self, seeded_client):
        resp = await seeded_client.get("/api/trades")
        summary = resp.json()["summary"]
        assert summary["total_trades"] == 3
        assert summary["open_trades"] == 1
        assert summary["closed_trades"] == 2

    async def test_open_filter(self, seeded_client):
        resp = await seeded_client.get("/api/trades?status=open")
        data = resp.json()
        for trade in data["trades"]:
            assert trade["exited_at"] is None

    async def test_closed_filter(self, seeded_client):
        resp = await seeded_client.get("/api/trades?status=closed")
        data = resp.json()
        for trade in data["trades"]:
            assert trade["exited_at"] is not None

    async def test_strategy_filter(self, seeded_client):
        resp = await seeded_client.get("/api/trades?strategy=gap_go")
        data = resp.json()
        for trade in data["trades"]:
            assert trade["strategy"] == "gap_go"

    async def test_pagination(self, seeded_client):
        resp = await seeded_client.get("/api/trades?page=1&page_size=2")
        data = resp.json()
        assert len(data["trades"]) <= 2
        assert data["pagination"]["page"] == 1

    async def test_trade_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/trades")
        trades = resp.json()["trades"]
        assert len(trades) > 0
        trade = trades[0]
        for field in ("id", "symbol", "strategy", "entry_price", "quantity",
                       "date", "taken_at"):
            assert field in trade

    async def test_empty_trades(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trades"] == []
        assert data["summary"]["total_trades"] == 0


class TestExportTrades:
    async def test_csv_export_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/trades/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    async def test_csv_has_header_row(self, seeded_client):
        resp = await seeded_client.get("/api/trades/export")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1
        header = lines[0]
        assert "symbol" in header
        assert "strategy" in header

    async def test_csv_has_data_rows(self, seeded_client):
        resp = await seeded_client.get("/api/trades/export")
        lines = resp.text.strip().split("\n")
        # header + at least one data row
        assert len(lines) >= 2

    async def test_csv_strategy_filter(self, seeded_client):
        resp = await seeded_client.get("/api/trades/export?strategy=gap_go")
        lines = resp.text.strip().split("\n")
        # header + filtered data
        for line in lines[1:]:
            assert "gap_go" in line
