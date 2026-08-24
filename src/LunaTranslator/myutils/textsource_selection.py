"""Resolve the application's single active text source.

Older Learning UI builds could persist more than one ``use`` flag.  The UI
then reported Hook while ``starttextsource`` instantiated OCR because the two
call sites used different priority orders.  Keep the invariant in one small,
testable place: exactly one enabled source maps to exactly one runtime object.
"""

TEXT_SOURCE_PRIORITY = ("texthook", "ocr", "copy", "filetrans", "mssr")


def select_exclusive_text_source(statuses, preferred=None):
    """Return the selected source and normalize all ``use`` flags.

    ``preferred`` is used for an explicit UI selection.  Without one, Hook is
    deliberately first so stale Hook+OCR configurations migrate back to the
    project's documented Hook-primary behavior.  Unknown future source keys
    remain selectable after the known priority list.
    """

    if preferred is not None:
        selected = preferred if preferred in statuses else None
    else:
        selected = next(
            (
                key
                for key in TEXT_SOURCE_PRIORITY
                if statuses.get(key, {}).get("use", False)
            ),
            None,
        )
        if selected is None:
            selected = next(
                (
                    key
                    for key, state in statuses.items()
                    if isinstance(state, dict) and state.get("use", False)
                ),
                None,
            )

    if selected is None:
        return None

    for key, state in statuses.items():
        if isinstance(state, dict) and "use" in state:
            state["use"] = key == selected
    return selected
