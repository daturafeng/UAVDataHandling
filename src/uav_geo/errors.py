class MetadataError(ValueError):
    """Raised when required metadata cannot be resolved."""


class GeometryError(ValueError):
    """Raised when the camera ray cannot be intersected with the ground plane."""
