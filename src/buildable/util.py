from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import override
else:
    # The override decorator is only available since python 3.12, so just export a no-op to replace it if we're not
    # type-checking.
    def override(fn):
        return fn
