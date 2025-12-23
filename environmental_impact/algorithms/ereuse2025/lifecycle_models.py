"""
Data models for device lifecycle calculations.

Contains the core data structures used across lifecycle calculations.
"""


class DiskMetadata:
    """Represents disk metadata for comparison."""
    def __init__(self, serial: str, model: str, manufacturer: str):
        self.serial = serial or ""
        self.model = model or ""
        self.manufacturer = manufacturer or ""

    def __eq__(self, other):
        """Compare disk metadata to detect changes."""
        if not isinstance(other, DiskMetadata):
            return False
        return (
            self.serial == other.serial and
            self.model == other.model and
            self.manufacturer == other.manufacturer
        )

    def __hash__(self):
        return hash((self.serial, self.model, self.manufacturer))

    def is_empty(self) -> bool:
        """Check if disk metadata is empty/missing."""
        return not (self.serial or self.model or self.manufacturer)


class EvidenceData:
    """Represents evidence data for lifecycle calculations."""
    def __init__(
        self,
        uuid: str,
        index: int,
        poh: int,
        disk_metadata: DiskMetadata
    ):
        self.uuid = uuid
        self.index = index
        self.poh = poh
        self.disk_metadata = disk_metadata
