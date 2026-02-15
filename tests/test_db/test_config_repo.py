"""Tests for ConfigRepository."""

import pytest


class TestConfigRepository:
    async def test_get_returns_none_when_empty(self, config_repo):
        result = await config_repo.get_user_config()
        assert result is None

    async def test_initialize_default_creates_config(self, config_repo):
        config = await config_repo.initialize_default("12345")
        assert config is not None
        assert config.telegram_chat_id == "12345"
        assert config.total_capital == 50000.0
        assert config.max_positions == 5
        assert config.created_at is not None

    async def test_initialize_default_with_custom_values(self, config_repo):
        config = await config_repo.initialize_default(
            telegram_chat_id="99999",
            total_capital=100000.0,
            max_positions=3,
        )
        assert config.telegram_chat_id == "99999"
        assert config.total_capital == 100000.0
        assert config.max_positions == 3

    async def test_initialize_default_upserts_existing(self, config_repo):
        await config_repo.initialize_default("12345", total_capital=50000.0)
        updated = await config_repo.initialize_default("67890", total_capital=75000.0)
        assert updated.telegram_chat_id == "67890"
        assert updated.total_capital == 75000.0

    async def test_update_capital(self, config_repo):
        await config_repo.initialize_default("12345")
        await config_repo.update_capital(100000.0)

        config = await config_repo.get_user_config()
        assert config.total_capital == 100000.0

    async def test_update_max_positions(self, config_repo):
        await config_repo.initialize_default("12345")
        await config_repo.update_max_positions(3)

        config = await config_repo.get_user_config()
        assert config.max_positions == 3

    async def test_retrieval_returns_updated_values(self, config_repo):
        await config_repo.initialize_default("12345")
        await config_repo.update_capital(200000.0)
        await config_repo.update_max_positions(10)

        config = await config_repo.get_user_config()
        assert config.total_capital == 200000.0
        assert config.max_positions == 10

    async def test_updated_at_changes_on_update(self, config_repo):
        config1 = await config_repo.initialize_default("12345")
        original_updated_at = config1.updated_at

        await config_repo.update_capital(999999.0)
        config2 = await config_repo.get_user_config()
        assert config2.updated_at >= original_updated_at

    async def test_update_capital_without_config_raises(self, config_repo):
        with pytest.raises(RuntimeError, match="No user config exists"):
            await config_repo.update_capital(100000.0)

    async def test_update_max_positions_without_config_raises(self, config_repo):
        with pytest.raises(RuntimeError, match="No user config exists"):
            await config_repo.update_max_positions(3)
