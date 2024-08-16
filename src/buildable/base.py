from __future__ import annotations

import abc
import gzip
import json
from typing import TYPE_CHECKING, Protocol, TypeVar

from lxml.etree import ElementTree, tostring

if TYPE_CHECKING:
    import os
    from typing import Any, BinaryIO, Callable, Final

    from lxml.etree import _Element

    # Introduced in 3.11.
    from typing_extensions import Self

_E = TypeVar("_E", bound="ElementObject")
_T = TypeVar("_T")
_T2_co = TypeVar("_T2_co", covariant=True)
_V = TypeVar("_V", str, int, bool, float)


# Generic `property` protocol with the same get/set type. The type checker is able to infer the get/set type hints when
# this is returned from a decorator. See e.g. https://github.com/python/typing/issues/985.
class GenericProperty(Protocol[_T2_co]):
    def __get__(self, obj: Any, type: type | None = ...) -> _T2_co:  # noqa: A002
        ...


class GenericMutableProperty(Protocol[_T]):
    def __get__(self, obj: Any, type: type | None = ...) -> _T:  # noqa: A002
        ...

    def __set__(self, obj: Any, value: _T) -> None: ...

    def __delete__(self, obj: Any) -> None: ...


def xml_property(
    attrib: str,
    property_type: type[_V],
) -> Callable[[Callable[[_T], _Element]], GenericMutableProperty[_V]]:
    def inner(fn: Callable[[_T], _Element]) -> GenericMutableProperty[_V]:
        """Define a property which takes its value from an element in an Ableton XML document."""

        def getter(instance: _T) -> _V:
            element = fn(instance)
            value = element.attrib.get(attrib, None)
            if value is None:
                msg = f"Tag '{element.tag}' has no value"
                raise ValueError(msg)
            if not isinstance(value, str):
                msg = f"Unexpected property type in XML document: {type(value)} (expected str)"
                raise TypeError(msg)

            # Special handling for boolean values, which show up as "true"/"false" strings.
            if issubclass(property_type, bool):
                if value.lower() in ("true", "false"):
                    return property_type(value.lower() == "true")

                msg = f"Unexpected boolean value in XML document: {value}"
                raise ValueError(msg)

            return property_type(value)

        def setter(instance: _T, value: _V) -> None:
            element = fn(instance)
            # Non-string values should use their JSON string representation.
            element.attrib[attrib] = value if isinstance(value, str) else json.dumps(value)

        return property(fget=getter, fset=setter)

    return inner


def child_element_object_property(
    property_type: type[_E],
) -> Callable[[Callable[[_T], _Element]], GenericProperty[_E]]:
    def inner(fn: Callable[[_T], _Element]) -> GenericProperty[_E]:
        def getter(instance: _T) -> _E:
            element: _Element = fn(instance)
            child_elements = element.findall(property_type.TAG)
            if len(child_elements) == 0:
                msg = f"Child element of type '{property_type.TAG}' not found"
                raise ValueError(msg)

            if len(child_elements) > 1:
                msg = f"Found more than one child element of type '{property_type.TAG}'"
                raise ValueError(msg)

            return property_type(child_elements[0])

        return property(fget=getter)

    return inner


class AbletonDocumentObject:
    """Base class for Ableton files which are encoded as gzipped XML documents."""

    ROOT_TAG: Final[str] = "Ableton"

    def __init__(self, data: BinaryIO) -> None:
        with gzip.GzipFile(fileobj=data) as gzipped_file:
            self._element_tree = ElementTree()
            # The type checker doesn't realize this is a valid call.
            self._element_tree.parse(gzipped_file)  # type: ignore

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
        self._element: _Element = root[0]

    @property
    def element(self) -> _Element:
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

            # Pretty-print the main tree.
            pretty_xml_str = tostring(self._element_tree, pretty_print=True, xml_declaration=False, encoding="utf-8")

            # Live documents add an extra space to self-closing tags.
            pretty_xml_str = pretty_xml_str.replace(b"/>\n", b" />\n")

            # Write the pretty-printed content.
            gzipped_output.write(pretty_xml_str)

    def write_to_file(self, filename: str | os.PathLike) -> None:
        with open(filename, "wb") as f:
            self.write(f)


class ElementObject(abc.ABC):  # noqa: B024
    TAG: str = NotImplemented

    def __init__(self, element: _Element):
        if element.tag != self.TAG:
            msg = f"Expected element of type '{self.TAG}', but got '{element.tag}'"
            raise ValueError(msg)
        self._element = element

    @property
    def element(self) -> _Element:
        return self._element
