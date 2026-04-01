"""Allow running as `python -m mcp_observability`."""

import asyncio

from mcp_observability.server import main

if __name__ == "__main__":
    asyncio.run(main())
