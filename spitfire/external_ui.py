"""Presentation constraints for the Empower-independent application.

Original UIR assets remain available for provenance; these constraints are
applied by both renderers and cannot be undone by legacy decoder callbacks.
They are presentation rules, not a replacement for the outbound policy.
"""

HIDDEN_PANELS = frozenset({8, 9})
HIDDEN_CONTROLS = {
    2: frozenset({10, 11, 12, 13}),  # protection bypasses are unavailable
    3: frozenset({2, 3, 6, 7, 9, 11, 12, 13, 15, 16, 17, 18, 24,
                  25, 30, 32, 34, 35, 37, 40, 41, 45, 46, 47,
                  49, 50, 51, 52}),
    4: frozenset({7, 11}),  # Empower firmware/version
    5: frozenset({37, 39}),  # old raw BWD configuration
    6: frozenset({8, 9, 19, 22, 24, 25, 29, 31, 32, 58, 59, 60, 65}),
}
READ_ONLY_CONTROLS = frozenset({(2, 9)})
LABELS = {
    (2, 9): "EXTERNAL PUMP OPT-OUT",
    (6, 6): "TDG SET RATE\n/ DIV (Hz)",
    (6, 7): "TDG SET RATE\n/ DIV (Hz)",
    (6, 10): "PC\nRUN",
    (6, 11): "PC\nSTOP",
    (6, 5): "RESET BWD",
    (5, 34): "HV ON/OFF",
}
TITLE = "Spitfire — External Pump (Empower-independent)"
INITIAL_STATUS = "PC RUN/STOP controls PC1 + PC2 only. HV and external pump are separate."


def hidden_control(panel, control):
    return panel in HIDDEN_PANELS or control in HIDDEN_CONTROLS.get(panel, ())


def constrain_attribute(panel, control, attribute, value):
    """Apply to every mutation, including later access-level changes."""
    if attribute in (530, "visible") and hidden_control(panel, control):
        return 0
    if attribute in (500, "dimmed") and (panel, control) in READ_ONLY_CONTROLS:
        return 1
    if attribute in (641, "label_text") and (panel, control) in LABELS:
        return LABELS[panel, control]
    return value


def apply_presentation(view):
    for panel in HIDDEN_PANELS:
        view.show_panel(panel, False)
    for panel, controls in HIDDEN_CONTROLS.items():
        for control in controls:
            view.set_attribute(panel, control, 530, 0)
    for (panel, control), label in LABELS.items():
        view.set_attribute(panel, control, 641, label)
    for panel, control in READ_ONLY_CONTROLS:
        view.set_attribute(panel, control, 500, 1)
    for control in (26, 27, 30):
        view.set_value(6, control, 0)
    view.set_value(4, 16, "Empower-independent")
    view.set_external_status(INITIAL_STATUS)
