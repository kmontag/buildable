import difflib
import gzip
import io
import pathlib

import pytest
from typeguard import typechecked

from buildable import LiveSet


@pytest.fixture
@typechecked
def live_12_default_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "live-12-default-set.als"


@typechecked
def test_formatting(live_12_default_set: pathlib.Path):
    with gzip.open(live_12_default_set, "rt", encoding="utf-8") as file:
        original_xml = file.read()

    live_set = LiveSet.from_file(live_12_default_set)

    output = io.BytesIO()

    live_set.write(output)
    output.seek(0)
    with gzip.GzipFile(fileobj=output) as gzipped_output:
        rendered_xml = gzipped_output.read().decode("utf-8")
        diff = difflib.unified_diff(
            original_xml.splitlines(),
            rendered_xml.splitlines(),
            fromfile="original",
            tofile="rendered",
            lineterm="",
        )
        assert rendered_xml == original_xml, f"Rendered XML differs from original:\n\n{"\n".join(diff)}"
