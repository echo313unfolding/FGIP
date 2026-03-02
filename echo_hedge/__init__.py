"""Echo Hedge - FGIP-Integrated Allocation Router.

Uses FGIP graph evidence for position sizing, NOT expected returns.

Key principle: confidence scales sizing, expected returns are assumptions.
"""

from .fgip_allocator import allocate_portfolio, Allocation
from .mcp_client import mcp_call

__all__ = ['allocate_portfolio', 'Allocation', 'mcp_call']
