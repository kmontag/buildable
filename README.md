# buildable

[![PyPI - Version](https://img.shields.io/pypi/v/buildable.svg)](https://pypi.org/project/buildable)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/buildable.svg)](https://pypi.org/project/buildable)
![Test & Release](https://github.com/kmontag/buildable/actions/workflows/test_and_release.yml/badge.svg?branch=main)
[![codecov](https://codecov.io/github/kmontag/alpax/graph/badge.svg?token=5C1JO6YTDL)](https://codecov.io/github/kmontag/buildable)

---

`buildable` allows you to edit and extend Ableton Live sets programmatically. For example, you could
have a single set that stores your common return tracks, and use `buildable` to add them to various
template sets.

Currently you can:

- copy tracks/returns from other sets.
- delete and re-order tracks/returns.
- edit key and MIDI mappings for many set elements.
- set some high-level view properties, like the session/arrangement state.

## Installation

```console
pip install buildable
```

## Usage

For example, you could create a project containing set components that you want to mix together, and
generate templates from them with something like:

```python
from buildable import LiveSet

# Template bases containing MIDI/audio tracks.
jam_session = LiveSet.from_file('jam-session-tracks.als')
composition = LiveSet.from_file('composition-tracks.als')

# Shared main track and return tracks to be copied to the templates.
shared_structure = LiveSet.from_file('shared-structure.als')

for template_set in (jam_session, composition):
    # Copy returns and main track from the shared set.
    template_set.insert_return_tracks(shared_returns.return_tracks)
    template_set.main_track = shared_main.main_track

    # Assign tap tempo to key "p".
    template_set.transport.tap_tempo_key_midi.persistent_key_string = "p"

# Assign crossfader to the mod wheel on MIDI channel 1.
jam_session.main_track.key_midi_crossfade_equal.channel = 0
jam_session.main_track.key_midi.crossfade_equal.note_or_controller = 1

# Switch to arrangment view.
composition.chooser_bar = LiveSet.CHOOSER_BAR_ARRANGEMENT

jam_session.write_to_file("/path/to/user-library/Templates/JamSession.als")
composition.write_to_file("/path/to/user-library/Templates/Composition.als")
```

## Design

Live sets are represented natively as XML documents, and `buildable` objects mirror a subset of the
native document structure as closely as possible, with helpers for more complex operations like
copying tracks. XML elements are also exposed directly if you want to go off-piste. This helps with
flexibility and maintainability, but comes with some caveats:

- spelling mistakes and naming inconsistencies are carried over from the native format.
- some simple operations require using relatively complex accessors - for example, key/MIDI mappings
  for sends are accessed using
  e.g. `live_set.primary_tracks[0].device_chain.mixer.sends.track_send_holders[0].send.key_midi`.
- `buildable` won't stop you from setting values that are semantically valid, but invalid at
  runtime.

The best way to familiarize yourself with the native document structure is to examine existing Live
sets (using e.g. `gunzip -c my-set.als`) and/or look through the `buildable` source code.
