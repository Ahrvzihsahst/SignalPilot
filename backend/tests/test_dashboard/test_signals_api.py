"""Tests for signals API."""



class TestLiveSignals:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        assert resp.status_code == 200

    async def test_has_market_status(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        assert "market_status" in data
        assert data["market_status"] in ("open", "closed")

    async def test_has_active_and_expired(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        assert "active_signals" in data
        assert "expired_signals" in data

    async def test_signals_sorted_by_composite_score(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        active = data["active_signals"]
        if len(active) >= 2:
            scores = [s.get("composite_score") or 0 for s in active]
            assert scores == sorted(scores, reverse=True)

    async def test_expired_signals_separated(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        for sig in data["expired_signals"]:
            assert sig["status"] in ("expired", "position_full")

    async def test_capital_and_positions(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        assert data["capital"] == 100000.0
        assert data["positions_max"] == 8

    async def test_today_pnl_present(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        assert "today_pnl" in data
        assert "today_pnl_pct" in data

    async def test_circuit_breaker_present(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        assert "circuit_breaker" in data
        cb = data["circuit_breaker"]
        assert "sl_count" in cb
        assert "sl_limit" in cb

    async def test_empty_signals(self, api_client):
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
        resp = await client.get("/api/signals/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_signals"] == []

    async def test_signal_item_fields(self, seeded_client):
        resp = await seeded_client.get("/api/signals/live")
        data = resp.json()
        all_signals = data["active_signals"] + data["expired_signals"]
        assert len(all_signals) > 0
        sig = all_signals[0]
        for field in ("id", "rank", "symbol", "strategy", "entry_price",
                       "stop_loss", "target_1", "target_2", "status"):
            assert field in sig


class TestSignalHistory:
    async def test_returns_200(self, seeded_client):
        resp = await seeded_client.get("/api/signals/history")
        assert resp.status_code == 200

    async def test_pagination(self, seeded_client):
        resp = await seeded_client.get("/api/signals/history?page=1&page_size=2")
        data = resp.json()
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2

    async def test_strategy_filter(self, seeded_client):
        resp = await seeded_client.get("/api/signals/history?strategy=gap_go")
        data = resp.json()
        for sig in data["signals"]:
            assert sig["strategy"] == "gap_go"

    async def test_status_filter(self, seeded_client):
        resp = await seeded_client.get("/api/signals/history?status=expired")
        data = resp.json()
        for sig in data["signals"]:
            assert sig["status"] == "expired"

    async def test_empty_history(self, api_client):
        client, conn = api_client
        resp = await client.get("/api/signals/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["signals"] == []
        assert data["pagination"]["total_items"] == 0

    async def test_total_pages_calculation(self, seeded_client):
        resp = await seeded_client.get("/api/signals/history?page_size=1")
        data = resp.json()
        assert data["pagination"]["total_pages"] >= 3
