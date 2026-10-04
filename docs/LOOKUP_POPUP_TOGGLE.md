# Small dictionary popup toggle — 2026-10-04

## Behavior

For the configured **small-window dictionary lookup** action on translation text:

1. A first left click queries the word. The popup header retains the actual query and displays `已查词` when a dictionary result is shown. This labels a performed lookup, not a guarantee that the dictionary returned a correct definition
2. Another left or right click on the same source word in the same source sentence closes the popup instead of querying, appending that word again, or repeating auto-TTS. The same rule cancels a still-pending lookup
3. A following fresh click can open the lookup again. A different word or a different sentence is a new lookup. Right-click append for a different word retains its existing behavior
4. Clicking a dictionary link or explicitly searching selected text **inside** the popup remains a lookup. Dictionary tabs, context menus, audio, settings, full-window lookup and Anki controls retain their functions

Only the configured small-window lookup action uses this toggle. The main dictionary window, copy actions, open-link actions and modifier selection keep their existing dispatch rules. No configuration migration or provider option changes are introduced.

## Implementation boundaries

- The lookup identity is the stripped incoming source word plus the source sentence, recorded before right-click append changes the displayed query
- A source press/release token follows Qt label clicks, selectable Qt text, the WebView bridge, and transparent-WebView polling. This prevents focus-loss on press from converting a closing click into a new query on release. A later press expires a canceled gesture; an older or duplicated threaded click cannot overwrite newer navigation
- Genuine source leave, disabled transparent polling and stale poll generations are handled separately. Transparent polling does not reuse a press after a canceled drag outside the renderer
- Closing invalidates only this `WordViewer` request identity. Late engine callbacks cannot populate or reopen the dismissed popup. Already collected data remains available for transfer to the main dictionary/Anki window
- Explicit dictionary-content navigation bypasses the source-click toggle. A queued content lookup from an already dismissed popup is ignored
- Popup-owned child focus is recognized correctly instead of being treated as outside focus

No model, dictionary backend, external service, user corpus, saved credential or user setting is changed by this patch.

## Cloud verification

Run from the repository root:

```sh
python -m unittest discover -s src/tests -p 'test_lookup*.py' -v
node src/tests/test_lookup_popup_bridge.js
python -m compileall -q src/LunaTranslator/LunaTranslator.py src/LunaTranslator/gui/flowsearchword.py src/LunaTranslator/gui/showword.py src/LunaTranslator/gui/rendertext
git diff --check
```

The Python tests use actual extracted production methods with fake Qt widgets/signals and delayed synthetic dictionary engines. The JavaScript test uses actual extracted browser callbacks with a fake bridge. This is method/bridge regression coverage, not a native application or visual pass.

Verified in the source-only cloud workspace: **39 Python tests and 6 JavaScript bridge scenarios passed**. All nine inline HTML script blocks passed Node syntax checks; the changed application Python files compiled and parsed with Python 3.7 grammar. Independent review found no remaining blocker in the requested paths. The publication diff passed whitespace and sensitive-content checks. These results do not represent the entire application test suite.

Coverage includes same-word left/right/third-click behavior, pending cancellation, old/new result ordering, focus loss on either side of press dispatch, canceled selection/modifier gestures, outside/keyboard focus loss, popup-child focus, dictionary-content navigation back to a prior word, duplicate/late clicks, different-word append, source context changes, ignored engines, original-word options, full-window/copy routing, hover timers, transparent polling, and source-leave cancellation.

## Remaining native acceptance

Use a disposable Windows portable copy with backed-up synthetic configuration. Do not overwrite the daily-use installation or private dictionary data.

- Exercise both Qt text modes and WebView, including transparent/click-through polling where enabled
- With the default focus-loss option enabled, verify first left click opens, repeated left/right closes, and a third click opens again. Repeat slow holds and fast double clicks
- Delay a fake/test dictionary response, close before it completes, and verify that it cannot reopen the popup. Switch words rapidly and confirm the header/results belong to the newest request
- Select/drag text, release outside, use right click with selected text, and repeat modifier-gated lookup. The next intentional click must work
- Test word-origin versus displayed-word configuration, same word in a new sentence, and right-click append on a different word
- Navigate dictionary links back to a previous word; use dictionary tabs, copy, audio, settings, main-window transfer and Anki controls. Dismiss the popup using its close control and focus/leave settings
- Check the plain-text status header, resizing and placement under light/dark themes and 100%/150%/200% scaling

Native acceptance is pending. Passing the cloud checks is not a binary-release gate pass, a translation-quality result, or evidence that an installed user copy has changed.
