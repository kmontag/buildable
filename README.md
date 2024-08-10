# buildable

[![PyPI - Version](https://img.shields.io/pypi/v/buildable.svg)](https://pypi.org/project/buildable)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/buildable.svg)](https://pypi.org/project/buildable)

---

`buildable` allows you to edit and extend Ableton Live sets
programmatically. For example, you could have a single set that stores
your common return tracks, and use `buildable` to add them to various
template sets.

## Installation

```console
pip install buildable
```

## Usage

```python
from buildable import LiveSet

# Template bases containing e.g. MIDI/audio tracks.
jam_session = LiveSet.from_file('jam-session-tracks.als')
composition = LiveSet.from_file('composition-tracks.als')

# Shared main track and return tracks to be copied to the templates.
shared_structure = LiveSet.from_file('shared-structure.als')

for template_set in (jam_session, composition):
    template_set.insert_return_tracks(shared_returns.return_tracks)
    template_set.main_track = shared_main.main_track

jam_session.write_to_file("/path/to/user-library/Templates/JamSession.als")
composition.write_to_file("/path/to/user-library/Templates/Composition.als")
```
