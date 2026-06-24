"""Global preset tools — import and register all preset tools here."""
from __future__ import annotations
from app.tools.preset import weather, text_processing, date_calc

_PRESET_TOOLS = {
    "query_weather": weather,
    "text_process": text_processing,
    "date_calc": date_calc,
}


def get_preset_tools() -> dict:
    """Return all registered preset tools with metadata."""
    return {
        name: mod.META
        for name, mod in _PRESET_TOOLS.items()
    }


async def execute_preset_tool(name: str, arguments: dict) -> str:
    """Execute a preset tool by name with given arguments."""
    mod = _PRESET_TOOLS.get(name)
    if not mod:
        raise ValueError(f"Preset tool '{name}' not found")
    return await mod.execute(**arguments)
