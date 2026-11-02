"""Make Textual look right on the Linux text console (TERM=linux).

Console fonts hold at most 512 glyphs. The Terminus fonts we load have box drawing and full blocks, but
none of the partial blocks Textual draws for 'tall'/'wide'/'outer' borders, scrollbar ends and the
checkbox brackets. On a console those cells come out blank or as a replacement glyph, so when we run there
we switch those few glyphs to ones every console font has.
"""
from __future__ import annotations

import os

from textual.scrollbar import ScrollBar, ScrollBarRender
from textual.widgets._toggle_button import ToggleButton

CSS = """
Input, RadioSet, OptionList, SelectCurrent, SelectOverlay, Button, #log {
    border: round $primary-darken-2 !important;
}
Input:focus, RadioSet:focus, OptionList:focus, Select:focus > SelectCurrent, Button:focus, Button:hover {
    border: round $primary !important;
}
Toast { border-left: heavy $primary !important; }
HeaderIcon { display: none; }
"""


class ConsoleScrollBarRender(ScrollBarRender):
    """Full-cell thumb only: no partial block glyphs at the ends."""
    VERTICAL_BARS = [" "] * 8
    HORIZONTAL_BARS = [" "] * 8


def is_console() -> bool:
    forced = os.environ.get("DIYLINUX_CONSOLE")
    if forced is not None:
        return forced == "1"
    return os.environ.get("TERM", "") == "linux"


def apply() -> str:
    """Patch Textual's glyphs for the console. Returns the CSS to append to the app stylesheet."""
    ScrollBar.renderer = ConsoleScrollBarRender
    ToggleButton.BUTTON_LEFT = "["
    ToggleButton.BUTTON_RIGHT = "]"
    return CSS
