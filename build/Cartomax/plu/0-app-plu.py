from __future__ import annotations

import sys

from common import module_carte


def main() -> None:
    carte = module_carte()
    carte.main()


if __name__ == "__main__":
    sys.exit(main())
