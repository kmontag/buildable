from __future__ import annotations

import gzip
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, ElementTree

if TYPE_CHECKING:
    import os
    from typing import BinaryIO, Final, Self


class AbletonDocumentObject:
    """Base class for Ableton files which are encoded as gzipped XML documents."""

    ROOT_TAG: Final[str] = "Ableton"

    def __init__(self, data: BinaryIO) -> None:
        with gzip.GzipFile(fileobj=data) as gzipped_file:
            self._element_tree = ElementTree()
            self._element_tree.parse(gzipped_file)

        root = self._element_tree.getroot()

        # There should be an <Ableton> tag at the root.
        if root.tag != self.ROOT_TAG:
            msg = "The data does not contain an Ableton document"
            raise ValueError(msg)

        # There should be exactly one element inside the Ableton tag,
        # which represents the main object.
        if len(root) != 1:
            msg = "The data must contain exactly one nested element"
            raise ValueError(msg)
        self._element: Element = root[0]

    @property
    def element(self) -> Element:
        """The XML element representing the document's primary object."""
        return self._element

    @classmethod
    def from_file(cls, file: str | os.PathLike) -> Self:
        with open(file, "rb") as f:
            return cls(f)

    def write(self, output: BinaryIO) -> None:
        with gzip.GzipFile(fileobj=output, mode="wb") as gzipped_output:
            # Output the XML prolog manually, so we can match the exact formatting for native Ableton files.
            gzipped_output.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')

            self._element_tree.write(gzipped_output, xml_declaration=False, encoding="utf-8", method="xml")

            # Output a trailing newline to match native files.
            gzipped_output.write(b"\n")
