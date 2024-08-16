from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # typing_extensions should automatically be available during type checking.
    from typing_extensions import override
else:
    # The override decorator is needed at runtime but is only available since python 3.12. To avoid a runtime dependency
    # on typing_extensions, just export a no-op to replace it if we're not type-checking.
    def override(fn):
        return fn
