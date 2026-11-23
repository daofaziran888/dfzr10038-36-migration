"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。

可追证报告引用路由先注册，避免 `/api/{module}/{entry_id}` 的动态段吃掉
`/api/trace/...` 的固定路径。
"""
from __future__ import annotations

from app.routers import resource, traceability

ROUTERS = [traceability, resource]
