"""单实例服务内的内容发布写入互斥。"""

from __future__ import annotations

import asyncio

publication_write_lock = asyncio.Lock()
