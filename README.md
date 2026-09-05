# 4d-plugin-apple-speech-recognizer

Drives Apple's `NSSpeechRecognizer` — the older, lightweight command-and-control speech API (not dictation, and not the newer `SFSpeechRecognizer`/Speech framework) — from 4D. You give it a fixed vocabulary of short command phrases; when the user says one of them, the plugin calls back into a 4D method of your choosing with the recognized phrase as a `TEXT` parameter. It does not transcribe arbitrary speech and does not return a `Picture`, `Blob`, or any other data type — every command below either configures the recognizer or returns nothing.

| Command | Returns | Purpose |
|---|---|---|
| [`START SPEECH RECOGNIZER`](#start-speech-recognizer) | — | Start (or reconfigure) listening, naming the callback method and options |
| [`SET SPEECH COMMANDS`](#set-speech-commands) | — | Replace the active vocabulary while listening |
| [`GET SPEECH COMMANDS`](#get-speech-commands) | Array of `TEXT` | Retrieve the vocabulary last set via `SET SPEECH COMMANDS` |
| [`STOP SPEECH RECOGNIZER`](#stop-speech-recognizer) | — | Stop listening without tearing down the recognizer |
| [`QUIT SPEECH RECOGNIZER`](#quit-speech-recognizer) | — | Stop listening and fully release the recognizer |

**Platforms:** macOS only (Carbon-hosted and Cocoa-hosted 4D). `NSSpeechRecognizer` is an AppKit API with no Windows equivalent; there is no Windows implementation of these commands.

---

## Requirements & platform notes

- **Legacy Apple API.** `NSSpeechRecognizer` is Apple's older, narrow-vocabulary command-recognition class — distinct from the modern `SFSpeechRecognizer`/Speech framework used for general dictation. Apple has flagged it as legacy for several macOS releases; it's still functional, but check Apple's current documentation for your target macOS version before depending on it long-term.
- **Microphone access.** The process needs microphone access permitted by the user/system. Exact privacy-prompt behavior around microphone access has changed across macOS releases — verify on your minimum supported OS.
- **Language follows System Preferences.** There's no language parameter. The recognized language is whatever the Mac's own Voice Recognition/Dictation preference is set to; you can't override it per-call.
- **One recognizer at a time.** All state (the active vocabulary, the callback method name, the title, the two boolean options) is global to the plugin — there's exactly one recognizer session per 4D application, not one per process or per window.
- **The callback method is called with a single `TEXT` parameter** — the recognized command phrase, exactly as it appears in whatever array you last passed to `SET SPEECH COMMANDS` (or as it was set at `START SPEECH RECOGNIZER` time). The method itself declares just `C_TEXT($1)`.
- **`STOP SPEECH RECOGNIZER` and `QUIT SPEECH RECOGNIZER` are not interchangeable.** `STOP` pauses listening but keeps the recognizer alive — a later `START SPEECH RECOGNIZER` resumes without a fresh setup. `QUIT` fully tears the recognizer down; a later `START SPEECH RECOGNIZER` builds an entirely new one. See each command's Description below.
- **The commands array is 1-indexed with element 0 always present and always filtered out.** You never need to worry about a stray empty entry showing up in the recognized vocabulary — see `SET SPEECH COMMANDS` below.

---

## START SPEECH RECOGNIZER

### Syntax

```
START SPEECH RECOGNIZER ( method ; options )
```

| Parameter | Type | Description |
|---|---|---|
| `method` | TEXT | Name of the 4D method to call when a command is recognized. Called as `method($1)`, where `$1` is the recognized command (`TEXT`). Required — an empty or non-existent method name means recognized commands have nowhere to go. |
| `options` | TEXT | A JSON object controlling recognizer behavior (see Description). Pass `"{}"` (via `JSON Stringify` on an empty object, or a literal `"{}"`) if you don't need to change any of the defaults. |
| Result | — | No return value. |

### Description

`options` is parsed as a JSON object and can carry any of these three keys — all optional, and any key you omit keeps its default:

| Key | Type | Default | Effect |
|---|---|---|---|
| `displayedCommandsTitle` | string | app name (e.g. `"4D"`) | Title shown above the commands in the system's floating speech-command palette. Only takes effect if the vocabulary is non-empty — see the note below. |
| `listensInForegroundOnly` | boolean | `true` | Whether the recognizer only reacts while your app is frontmost. |
| `blocksOtherRecognizers` | boolean | `false` | Whether this recognizer exclusively claims speech input, blocking other apps'/system recognizers while active. |

Any key with an unrecognized name is silently ignored.

**The custom title only shows if both a title was given *and* the vocabulary is non-empty at that moment.** If you call `START SPEECH RECOGNIZER` before ever calling `SET SPEECH COMMANDS`, or with an empty title, the palette falls back to showing the app's own name — this matches the plugin's own stated behavior ("by default the commands title is the app name... also when the list is empty").

**Calling `START SPEECH RECOGNIZER` again while already listening reconfigures the existing session** rather than starting a second one — it updates the callback method name, the title, and the two booleans, and restarts listening with the new settings. It does not spawn a second recognizer.

### Example

From the plugin's own README:

```4d
C_OBJECT($params)

  //by default the commands title is the app name i.e. 4D
  //also when the list is empty
  //empty strings (e.g. element 0) are filtered
  //the language respects System Preferences/Voice Recognition and Dictation

OB SET($params;\
"listensInForegroundOnly";False;\
"blocksOtherRecognizers";True;\
"displayedCommandsTitle";"List of Commands")

START SPEECH RECOGNIZER ("CB";JSON Stringify($params))
```

The callback method named here (`CB`, from the plugin's own test method `CB.4dm`) is as simple as it can be:

```4d
//%attributes = {}
C_TEXT($1)

TRACE
```

A minimal call using every default (no title override, foreground-only listening, non-exclusive):

```4d
START SPEECH RECOGNIZER ("CB";"{}")
```

---

## SET SPEECH COMMANDS

### Syntax

```
SET SPEECH COMMANDS ( commands )
```

| Parameter | Type | Description |
|---|---|---|
| `commands` | Array of TEXT | The vocabulary to listen for. Can be called at any time — including while already listening — to swap the active vocabulary. |
| Result | — | No return value. |

### Description

Replaces the recognizer's vocabulary. Any array element that's an empty string is filtered out before being handed to the recognizer — in practice this means array element `0` (which 4D arrays always have, and which is typically left empty) never shows up as a spurious recognizable phrase, so you don't need to special-case it yourself.

Calling this before `START SPEECH RECOGNIZER` has been called at all is harmless — it just updates the vocabulary that will be used whenever the recognizer is (re)started, but has no listening recognizer to apply to yet.

### Example

From the plugin's own test method (`Method1.4dm`), which swaps the vocabulary twice in a row while already listening:

```4d
ARRAY TEXT($commands;3)
$commands{1}:="こんにちは"
$commands{2}:="さようなら"
$commands{3}:="おっとっと"

  //you can change the vocabulary while listening
SET SPEECH COMMANDS ($commands)

ARRAY TEXT($commands;3)
$commands{1}:="とんとんとん"
$commands{2}:="がんがんがん"
$commands{3}:="ぶんぶんぶん"

SET SPEECH COMMANDS ($commands)
```

A simple English vocabulary:

```4d
ARRAY TEXT($commands;2)
$commands{1}:="open file"
$commands{2}:="close file"
SET SPEECH COMMANDS ($commands)
```

---

## GET SPEECH COMMANDS

### Syntax

```
GET SPEECH COMMANDS ( commands )
```

| Parameter | Type | Description |
|---|---|---|
| `commands` | Array of TEXT | Filled with the vocabulary last passed to `SET SPEECH COMMANDS`. |
| Result | Array of TEXT (via `commands`) | Empty if `SET SPEECH COMMANDS` was never called. |

### Description

Returns exactly what was last passed to `SET SPEECH COMMANDS` — it reflects the plugin's own record of the vocabulary, not a live read of any operating-system state. If you've never called `SET SPEECH COMMANDS`, the array comes back empty.

### Example

```4d
ARRAY TEXT($currentCommands;0)
GET SPEECH COMMANDS ($currentCommands)

For ($i;1;Size of array($currentCommands))
    ALERT($currentCommands{$i})
End for
```

---

## STOP SPEECH RECOGNIZER

### Syntax

```
STOP SPEECH RECOGNIZER
```

| Parameter | Type | Description |
|---|---|---|
| Result | — | No return value. |

### Description

Stops listening but **does not** end the recognizer session — the plugin's own comment in the README is explicit about this ("stop does not end the palette"). The vocabulary, callback method, title, and booleans you last set all remain in effect; a later `START SPEECH RECOGNIZER` call resumes listening immediately with everything unchanged, rather than performing a full re-setup.

### Example

```4d
STOP SPEECH RECOGNIZER
  // ... later, resume with the same settings ...
START SPEECH RECOGNIZER ("CB";"{}")
```

---

## QUIT SPEECH RECOGNIZER

### Syntax

```
QUIT SPEECH RECOGNIZER
```

| Parameter | Type | Description |
|---|---|---|
| Result | — | No return value. |

### Description

Stops listening and fully releases the recognizer — the plugin's own comment calls this out directly ("quit ends the palette"). Any command phrases still queued for delivery to your callback method are discarded. After `QUIT SPEECH RECOGNIZER`, the next `START SPEECH RECOGNIZER` call builds an entirely new recognizer session from scratch (new callback method name, new options, new vocabulary — none of it carries over).

Call this when your database closes or when speech recognition genuinely isn't needed again soon; call `STOP SPEECH RECOGNIZER` instead if you expect to resume shortly with the same setup.

### Example

From the plugin's own test method (`Method1.4dm`), as the final step after setting up and exercising the recognizer:

```4d
  //quit ends the palette
QUIT SPEECH RECOGNIZER
```

---

## Error handling & troubleshooting

- **Nothing happens and no error is raised if `method` doesn't name a real 4D method.** `START SPEECH RECOGNIZER` doesn't validate the method name up front — if it's misspelled or the method doesn't exist, recognized commands simply have nowhere to be delivered. Double-check the method name (and that the method actually exists in your project) if your callback never fires.
- **A custom `displayedCommandsTitle` silently falls back to the app name if the vocabulary is empty at that moment.** Call `SET SPEECH COMMANDS` with a non-empty array before (or as part of) starting, if you need your own title to actually appear.
- **`options` must be valid JSON, but an invalid or unparsable `options` string doesn't raise a 4D error either** — it's silently treated as if no options were given, so the recognizer starts with every default (foreground-only, non-exclusive, no custom title). If your settings don't seem to be taking effect, check that `options` is well-formed JSON (`JSON Stringify` on an object is the reliable way to build it).
- **Recognized speech is delivered asynchronously**, not synchronously with any 4D command call — your callback method is invoked by the plugin's own background process whenever a command is recognized, independent of whatever else your 4D application is doing at that moment. Don't assume commands you set via `SET SPEECH COMMANDS` are "live" the instant that command returns; treat it as effective from that point onward rather than expecting synchronous confirmation.
- **`STOP` vs. `QUIT` matters for what state survives.** If your commands or title seem to have reset unexpectedly, check whether something in your code called `QUIT SPEECH RECOGNIZER` rather than `STOP SPEECH RECOGNIZER` — only `STOP` preserves the existing setup for a quick resume.
- **Only one recognizer session exists at a time**, plugin-wide. If different parts of your application call `START SPEECH RECOGNIZER` with different methods/vocabularies expecting independent sessions, the later call reconfigures the same underlying session rather than creating a second one — the earlier caller's method and vocabulary are overwritten.

---

## Quick reference

```4d
  // start listening, custom title, exclusive foreground-only
C_OBJECT($params)
OB SET($params;"listensInForegroundOnly";True;"blocksOtherRecognizers";True;"displayedCommandsTitle";"My Commands")
START SPEECH RECOGNIZER ("CB";JSON Stringify($params))

  // set/replace the vocabulary at any time
ARRAY TEXT($commands;2)
$commands{1}:="open file"
$commands{2}:="close file"
SET SPEECH COMMANDS ($commands)

  // read back the active vocabulary
ARRAY TEXT($current;0)
GET SPEECH COMMANDS ($current)

  // pause without losing setup, then resume
STOP SPEECH RECOGNIZER
START SPEECH RECOGNIZER ("CB";"{}")

  // fully end the session
QUIT SPEECH RECOGNIZER
```

```4d
  // the callback method (declare in your own "CB" method)
C_TEXT($1)
  // $1 is the recognized command text
```
