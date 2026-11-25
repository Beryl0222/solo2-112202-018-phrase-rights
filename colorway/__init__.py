"""把业务资料包整理成可按渠道、来源和用词生效时间追溯的工作底稿。

本包只读取资料并获得结论，不修改 materials/ 下的来件。
"""
from __future__ import annotations

from .compile import build_workspace, describe_sources, write_workspace
from .render import render_briefs

__all__ = ["build_workspace", "describe_sources", "render_briefs", "write_workspace"]
