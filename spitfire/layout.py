"""Presentation-only overrides for the original Timing panel.

The vendor UIR bytes, control values and callbacks remain unchanged.  Native
loads the UIR then applies these attributes before binding any callbacks.
"""
from __future__ import annotations


TIMING_PANEL_ID = 5
HV_SWITCH_CONTROL_ID = 34
HV_SWITCH_LABEL = "HV ON/OFF"

# Coordinates are CVI panel pixels. Bounding rectangles include visible labels.
TIMING_HV_LAYOUT = {
    7: {"top": 410, "label_top": 363, "bounding_rect": (361, 18, 77, 146)},
    43: {"left": 170, "top": 410, "label_left": 182, "label_top": 382,
         "bounding_rect": (382, 170, 49, 75)},
    34: {
        "left": 198, "top": 320, "visible": 1, "hidden_when_loaded": 0,
        "label_text": HV_SWITCH_LABEL, "label_left": 170, "label_top": 299,
        "label_width": 90, "label_height": 17, "label_visible": 1,
        "label_size_to_text": 0, "bounding_rect": (299, 170, 71, 90),
    },
}

# GetCtrlBoundingRect determines the actual Native bounds in the Windows check.
# The private UIR hidden-when-loaded bit is retained; runtime visibility is set
# explicitly after loading instead of rewriting the resource.
TIMING_HV_NATIVE_ATTRIBUTES = (
    (7, 532, 410), (7, 671, 363),
    (43, 531, 170), (43, 532, 410), (43, 670, 182), (43, 671, 382),
    (34, 531, 198), (34, 532, 320),
    (34, 641, HV_SWITCH_LABEL), (34, 649, 0),
    (34, 672, 90), (34, 673, 17),
    (34, 670, 170), (34, 671, 299),
    (34, 660, 1), (34, 530, 1),
)
