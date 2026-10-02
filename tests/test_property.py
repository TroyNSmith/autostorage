"""Property module tests."""

import pytest

from autostorage.property import PropertyKindRegistry, energy_property_kind


class TestPropertyKindRegistry:
    """Tests for PropertyKindRegistry."""

    def test_get(self) -> None:
        """A registered property kind is returned by name."""
        assert PropertyKindRegistry.get("energy") is energy_property_kind

    def test_get_unknown(self) -> None:
        """Looking up an unregistered name raises a KeyError listing the options."""
        with pytest.raises(KeyError, match=r"Unknown property kind 'nope'.*energy"):
            PropertyKindRegistry.get("nope")

    def test_register_duplicate(self) -> None:
        """Registering an existing name raises a ValueError."""
        with pytest.raises(ValueError, match="already registered"):
            PropertyKindRegistry.register(
                "energy", validation_fn=energy_property_kind.validation_fn
            )
