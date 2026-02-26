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


class TestConfigRepositoryPhase3:
    async def test_config_round_trips_phase3_fields(self, config_repo):
        """Phase 3 config fields round-trip through write and read."""
        await config_repo.initialize_default("12345")

        # Update Phase 3 fields
        await config_repo.update_user_config(
            circuit_breaker_limit=5,
            confidence_boost_enabled=False,
            adaptive_learning_enabled=False,
            auto_rebalance_enabled=False,
            adaptation_mode="conservative",
        )

        config = await config_repo.get_user_config()
        assert config is not None
        assert config.circuit_breaker_limit == 5
        assert config.confidence_boost_enabled is False
        assert config.adaptive_learning_enabled is False
        assert config.auto_rebalance_enabled is False
        assert config.adaptation_mode == "conservative"

    async def test_config_phase3_defaults(self, config_repo):
        """Phase 3 fields have correct defaults when not explicitly set."""
        await config_repo.initialize_default("12345")

        config = await config_repo.get_user_config()
        assert config is not None
        assert config.circuit_breaker_limit == 3
        assert config.confidence_boost_enabled is True
        assert config.adaptive_learning_enabled is True
        assert config.auto_rebalance_enabled is True
        assert config.adaptation_mode == "aggressive"

    async def test_set_strategy_enabled(self, config_repo):
        """set_strategy_enabled works for all allowed fields."""
        await config_repo.initialize_default("12345")

        # Disable gap_go
        await config_repo.set_strategy_enabled("gap_go_enabled", False)
        config = await config_repo.get_user_config()
        assert config.gap_go_enabled is False

        # Re-enable gap_go
        await config_repo.set_strategy_enabled("gap_go_enabled", True)
        config = await config_repo.get_user_config()
        assert config.gap_go_enabled is True

        # Disable orb
        await config_repo.set_strategy_enabled("orb_enabled", False)
        config = await config_repo.get_user_config()
        assert config.orb_enabled is False

        # Disable vwap
        await config_repo.set_strategy_enabled("vwap_enabled", False)
        config = await config_repo.get_user_config()
        assert config.vwap_enabled is False

    async def test_set_strategy_enabled_rejects_invalid_field(self, config_repo):
        """set_strategy_enabled raises for invalid field names."""
        await config_repo.initialize_default("12345")

        with pytest.raises(ValueError, match="Invalid strategy field"):
            await config_repo.set_strategy_enabled("invalid_field", True)

    async def test_update_user_config_rejects_invalid_fields(self, config_repo):
        """update_user_config raises for unknown field names."""
        await config_repo.initialize_default("12345")

        with pytest.raises(ValueError, match="Invalid config field"):
            await config_repo.update_user_config(nonexistent_field="value")

    async def test_update_user_config_partial_update(self, config_repo):
        """update_user_config can update a single field without affecting others."""
        await config_repo.initialize_default("12345")

        # Update only circuit_breaker_limit
        await config_repo.update_user_config(circuit_breaker_limit=7)

        config = await config_repo.get_user_config()
        assert config.circuit_breaker_limit == 7
        # Other Phase 3 fields should retain defaults
        assert config.confidence_boost_enabled is True
        assert config.adaptation_mode == "aggressive"
