from typing import TYPE_CHECKING, override

from .base import AbletonDocumentObject

if TYPE_CHECKING:
    from typing import BinaryIO, Final


class LiveSet(AbletonDocumentObject):
    ELEMENT_TAG: "Final[str]" = "LiveSet"

    @override
    def __init__(self, data: "BinaryIO") -> None:
        super().__init__(data)

        if self._element.tag != self.ELEMENT_TAG:
            msg = f"Invalid element tag name: '{self._element.tag}' (expected '{self.ELEMENT_TAG}')"
            raise ValueError(msg)
