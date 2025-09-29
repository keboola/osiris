"""Mode mapping utilities for OML v0.1.0 compatibility."""


class ModeMapper:
    """Maps OML canonical modes to component-specific modes."""

    # OML canonical modes -> component modes
    MODE_ALIASES = {
        "read": "extract",  # read -> extract for extractors
        "write": "write",  # write stays write
        "transform": "transform",  # transform stays transform
    }

    # Reverse mapping for validation
    COMPONENT_TO_CANONICAL = {
        "extract": "read",
        "discover": None,  # discovery not supported in compiled runs
        "write": "write",
        "transform": "transform",
    }

    @classmethod
    def to_component_mode(cls, oml_mode: str) -> str:
        """Convert OML canonical mode to component mode.

        Args:
            oml_mode: Mode from OML (read, write, transform)

        Returns:
            Component-specific mode
        """
        return cls.MODE_ALIASES.get(oml_mode, oml_mode)

    @classmethod
    def to_canonical_mode(cls, component_mode: str) -> str | None:
        """Convert component mode to OML canonical mode.

        Args:
            component_mode: Mode from component spec

        Returns:
            OML canonical mode or None if not supported
        """
        return cls.COMPONENT_TO_CANONICAL.get(component_mode)

    @classmethod
    def is_mode_compatible(cls, oml_mode: str, component_modes: list) -> bool:
        """Check if OML mode is compatible with component's supported modes.

        Args:
            oml_mode: Mode specified in OML
            component_modes: List of modes supported by component

        Returns:
            True if compatible
        """
        # Map OML mode to component mode
        component_mode = cls.to_component_mode(oml_mode)

        # Check if component supports this mode
        return component_mode in component_modes

    @classmethod
    def get_canonical_modes(cls) -> list:
        """Get list of canonical OML modes."""
        return list(cls.MODE_ALIASES.keys())
