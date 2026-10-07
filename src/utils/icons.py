"""
icons.py — Universal PLC Monitor
Single-color SVG icon library for the industrial SCADA/HMI theme.

Icons are rendered with a __COLOR__ placeholder so the caller can tint them
to the active theme (slate idle / cyan active).
"""
from __future__ import annotations

_VIEWBOX = 'viewBox="0 0 24 24" fill="none" stroke="__COLOR__" '
_STROKE = 'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'

# Each icon is a 24x24 line SVG at the given color.
_ICONS: dict[str, str] = {
    # Model Selection — factory facade / machine
    "model": (
        '<path d="M3 21h18"/>'
        '<path d="M5 21V8l7-5 7 5v13"/>'
        '<path d="M9 21v-6h6v6"/>'
        '<path d="M9 12h.01M15 12h.01"/>'
    ),
    # Live Testing — gauge / pulse
    "test": (
        '<circle cx="12" cy="13" r="8"/>'
        '<path d="M12 13V9"/>'
        '<path d="M8.5 13h7"/>'
        '<path d="M12 21v1.5"/>'
        '<path d="M5 3l1.5 1.5M19 4l-1.5 1.5"/>'
    ),
    # Manual Control — toggle switch / joystick
    "manual": (
        '<rect x="3" y="6" width="18" height="12" rx="6"/>'
        '<circle cx="16.5" cy="12" r="2"/>'
        '<path d="M9 10h.01M9 14h.01"/>'
    ),
    # Config — industrial gear sliders
    "config": (
        '<path d="M14 7l3-3 3 3-3 3"/>'
        '<path d="M17 4V2"/>'
        '<rect x="2" y="4" width="8" height="2" rx="1"/>'
        '<rect x="2" y="11" width="6" height="2" rx="1"/>'
        '<rect x="2" y="18" width="10" height="2" rx="1"/>'
        '<path d="M14 17v3a2 2 0 0 0 2 2h2"/>'
    ),
    # I/O — terminal strip / circuit
    "io": (
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<path d="M7 8v8M12 8v8M17 8v8"/>'
        '<path d="M7 12h10"/>'
    ),
    # Reports — bar chart / document
    "reports": (
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<path d="M8 9l-3-2M13 7l-3-2M18 5l-3-2" opacity="0"/>'
        '<path d="M8 16h8"/>'
        '<path d="M8 12h5"/>'
        '<path d="M8 16v0M8 12v0"/>'
    ),
    # Settings — preferences slider
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'
        '<path d="M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>'
    ),
    # Theme — half moon / sun
    "theme": (
        '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>'
    ),
    # Logout — secure exit
    "logout": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<path d="M16 17l5-5-5-5"/>'
        '<path d="M21 12H9"/>'
    ),
}


def get_icon(name: str, color: str) -> str:
    """Return the raw SVG markup for the given icon name tinted with color."""
    body = _ICONS.get(name)
    if body is None:
        return ""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" ' \
          f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" ' \
          f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    return svg