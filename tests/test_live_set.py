import difflib
import gzip
import io
import pathlib

import pytest
from typeguard import typechecked

from buildable.live_set import GroupTrack, LiveSet, PrimaryTrack, ReturnTrack


@pytest.fixture
@typechecked
def live_12_default_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "live-12-default.als"


@pytest.fixture
@typechecked
def groups_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "groups.als"


@pytest.fixture
@typechecked
def routing_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "routing.als"


@pytest.fixture
@typechecked
def sends_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "sends.als"


@typechecked
def test_formatting(live_12_default_set: pathlib.Path):
    with gzip.open(live_12_default_set, "rt", encoding="utf-8") as file:
        original_xml = file.read()

    live_set = LiveSet.from_file(live_12_default_set)

    output = io.BytesIO()

    live_set.write(output)
    output.seek(0)
    with gzip.GzipFile(fileobj=output) as gzipped_output:
        rendered_xml = gzipped_output.read().decode("utf-8")
        diff = difflib.unified_diff(
            original_xml.splitlines(),
            rendered_xml.splitlines(),
            fromfile="original",
            tofile="rendered",
            lineterm="",
        )
        assert rendered_xml == original_xml, f"Rendered XML differs from original:\n\n{"\n".join(diff)}"


@typechecked
def test_insert_primary_tracks(live_12_default_set: pathlib.Path):
    live_set = LiveSet.from_file(live_12_default_set)
    other_live_set = LiveSet.from_file(live_12_default_set)
    insert_index = 1

    assert len(live_set.primary_tracks) > 0
    assert len(other_live_set.primary_tracks) > 0
    total_num_tracks = len(live_set.primary_tracks) + len(other_live_set.primary_tracks)

    primary_track_ids, return_track_ids = (
        [track.id for track in tracks] for tracks in (live_set.primary_tracks, live_set.return_tracks)
    )

    live_set.insert_primary_tracks(other_live_set.primary_tracks, index=insert_index)
    assert len(live_set.primary_tracks) == total_num_tracks

    output = io.BytesIO()
    live_set.write(output)

    output.seek(0)
    modified_live_set = LiveSet(output)

    assert len(modified_live_set.primary_tracks) == total_num_tracks
    modified_track_ids = [track.id for track in modified_live_set.primary_tracks]
    expected_track_ids = [
        *primary_track_ids[:insert_index],
        *[i + max(primary_track_ids + return_track_ids) + 1 for i in range(len(primary_track_ids))],
        *primary_track_ids[insert_index:],
    ]
    assert (
        modified_track_ids == expected_track_ids
    ), f"Track IDs were not correctly updated: got {modified_track_ids}, expected {expected_track_ids}"

    modified_tracks_element = modified_live_set.element.find("Tracks")
    assert modified_tracks_element is not None

    # Make sure return tracks appear after primary tracks.
    did_find_return_track = False
    for track_element in modified_tracks_element:
        assert track_element.tag in [ReturnTrack.TAG, *[t.TAG for t in PrimaryTrack.types()]]

        if track_element.tag == ReturnTrack.TAG:
            did_find_return_track = True

        if did_find_return_track:
            assert track_element.tag == ReturnTrack.TAG


@typechecked
def test_insert_return_tracks(live_12_default_set: pathlib.Path):
    live_set = LiveSet.from_file(live_12_default_set)
    other_live_set = LiveSet.from_file(live_12_default_set)
    insert_index = 1

    assert len(live_set.return_tracks) > 0
    assert len(other_live_set.return_tracks) > 0
    total_num_tracks = len(live_set.return_tracks) + len(other_live_set.return_tracks)
    primary_track_ids, return_track_ids = (
        [track.id for track in tracks] for tracks in (live_set.primary_tracks, live_set.return_tracks)
    )

    live_set.insert_return_tracks(other_live_set.return_tracks, index=insert_index)

    assert len(live_set.return_tracks) == total_num_tracks

    output = io.BytesIO()
    live_set.write(output)
    output.seek(0)
    modified_live_set = LiveSet(output)
    assert len(modified_live_set.return_tracks) == total_num_tracks

    modified_track_ids = [track.id for track in modified_live_set.return_tracks]
    expected_track_ids = [
        *return_track_ids[:insert_index],
        *[i + max(primary_track_ids + return_track_ids) + 1 for i in range(len(return_track_ids))],
        *return_track_ids[insert_index:],
    ]
    assert (
        modified_track_ids == expected_track_ids
    ), f"Track IDs were not correctly updated: got {modified_track_ids}, expected {expected_track_ids}"

    modified_tracks_element = modified_live_set.element.find("Tracks")
    assert modified_tracks_element is not None

    did_find_return_track = False
    for track_element in modified_tracks_element:
        assert track_element.tag in [ReturnTrack.TAG, *[t.TAG for t in PrimaryTrack.types()]]

        if track_element.tag == ReturnTrack.TAG:
            did_find_return_track = True

        if did_find_return_track:
            assert track_element.tag == ReturnTrack.TAG


@typechecked
def test_track_group_ids_updated(groups_set: pathlib.Path):
    live_set = LiveSet.from_file(groups_set)

    primary_track_ids, return_track_ids = (
        [track.id for track in tracks] for tracks in (live_set.primary_tracks, live_set.return_tracks)
    )
    next_track_id = max(primary_track_ids + return_track_ids) + 1
    live_set.insert_primary_tracks(live_set.primary_tracks)

    output = io.BytesIO()
    live_set.write(output)
    output.seek(0)
    modified_live_set = LiveSet(output)
    assert len(modified_live_set.primary_tracks) == 2 * len(primary_track_ids)

    modified_track_ids = [track.id for track in modified_live_set.primary_tracks]
    expected_track_ids = [
        *[i + next_track_id for i in range(len(primary_track_ids))],
        *primary_track_ids,
    ]
    assert (
        modified_track_ids == expected_track_ids
    ), f"Track IDs were not correctly updated: got {modified_track_ids}, expected {expected_track_ids}"

    # The original set contains two groups, one containing 2 midi
    # tracks and one containing 2 audio tracks.
    midi_group_index = 0
    audio_group_index = 3

    # Sanity check the names and types of the tracks at these indices in the modified set.
    for index, name in ((midi_group_index, "Midi Group"), (audio_group_index, "Audio Group")):
        # The group should appear in both the inserted tracks and the original tracks.
        for group_track in (
            modified_live_set.primary_tracks[index],
            modified_live_set.primary_tracks[len(primary_track_ids) + index],
        ):
            assert isinstance(group_track, GroupTrack)
            assert group_track.user_name == name

    # Check that the tracks' associated group IDs match the expected ones.
    for base_index in (0, len(primary_track_ids)):
        midi_group_id = expected_track_ids[base_index + midi_group_index]
        audio_group_id = expected_track_ids[base_index + audio_group_index]

        for track in modified_live_set.primary_tracks[base_index + 1 :][: audio_group_index - 1]:
            assert track.track_group_id == midi_group_id
        for track in modified_live_set.primary_tracks[base_index + audio_group_index + 1 : len(primary_track_ids)]:
            assert track.track_group_id == audio_group_id


@typechecked
def test_routings_updated(routing_set: pathlib.Path):
    live_set = LiveSet.from_file(routing_set)

    # Sanity check the track structure.
    assert [t.user_name for t in live_set.primary_tracks] == [
        "MIDI to target",
        "MIDI from target",
        "MIDI target",
        "Audio to target",
        "Audio from target",
        "Audio target",
    ]

    primary_track_ids, return_track_ids = (
        [track.id for track in tracks] for tracks in (live_set.primary_tracks, live_set.return_tracks)
    )
    next_track_id = max(primary_track_ids + return_track_ids) + 1

    expected_routing_targets: dict[str, list[str]] = {
        routing_attr: [getattr(t.device_chain, routing_attr).target for t in live_set.primary_tracks] * 2
        for routing_attr in ("audio_input_routing", "audio_output_routing", "midi_input_routing", "midi_output_routing")
    }

    # Overwrite default targets where appropriate.
    for routing_attr, source_track_index, target_track_index, default_target in (
        ("audio_input_routing", 4, 5, None),
        ("audio_output_routing", 3, 5, "AudioOut/Main"),
        ("midi_input_routing", 1, 2, "MidiIn/External.All/-1"),
        ("midi_output_routing", 0, 2, "MidiOut/None"),
    ):
        targets: list[str] = expected_routing_targets[routing_attr]
        original_source_track_index = source_track_index + len(live_set.primary_tracks)

        # Ensure that the default routing shows up on everything other
        # than the tracks with a custom routing.
        if default_target is not None:
            for track_index, target in enumerate(targets):
                if track_index in (source_track_index, original_source_track_index):
                    assert target != default_target
                else:
                    assert (
                        target == default_target
                    ), f"Expected track {track_index} to have {routing_attr} '{default_target}', but got '{target}'"

        original_track_str = f"Track.{primary_track_ids[target_track_index]}"
        assert original_track_str in targets[original_source_track_index]
        targets[source_track_index] = targets[original_source_track_index].replace(
            original_track_str, f"Track.{next_track_id + target_track_index}"
        )

    live_set.insert_primary_tracks(live_set.primary_tracks)

    output = io.BytesIO()
    live_set.write(output)
    output.seek(0)
    modified_live_set = LiveSet(output)

    for routing_attr, expected_targets in expected_routing_targets.items():
        targets = [getattr(t.device_chain, routing_attr).target for t in modified_live_set.primary_tracks]
        assert (
            targets == expected_targets
        ), f"Incorrect {routing_attr} targets - got {targets}, expected {expected_targets}"


@typechecked
def test_sends_inserted(sends_set: pathlib.Path):
    live_set = LiveSet.from_file(sends_set)

    # All sends should have the same min value.
    example_send = live_set.primary_tracks[0].device_chain.mixer.sends.track_send_holders[0].send
    min_send_value = example_send.midi_controller_range.min
    max_send_value = example_send.midi_controller_range.max
    assert max_send_value == 1.0  # Sanity check.

    # Get all send values for primary and return tracks (in that order) in the given set.
    def get_send_values(live_set: LiveSet) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(
                track_send_holder.send.value for track_send_holder in track.device_chain.mixer.sends.track_send_holders
            )
            for track in [*live_set.primary_tracks, *live_set.return_tracks]
        )

    # Sanity check the set structure.
    assert len(live_set.primary_tracks) == 2
    assert len(live_set.return_tracks) == 2
    expected_send_values = tuple(
        # For simplicity, sends in the set are either set to the full min or full max value.
        tuple(max_send_value if is_max else min_send_value for is_max in is_maxes)
        for is_maxes in (
            (True, False),
            (False, False),
            (False, True),
            (False, False),
        )
    )
    assert [t.send_pre for t in live_set.return_tracks] == [True, False]

    actual_send_values = get_send_values(live_set)
    assert (
        actual_send_values == expected_send_values
    ), f"Unexpected send values in unmodified set: {actual_send_values} (expected {expected_send_values})"

    live_set.insert_tracks(
        # Copy the main track.
        main_track=live_set.main_track,
        # Include a primary track with the duplicated return active.
        primary_tracks=[live_set.primary_tracks[0]],
        primary_tracks_index=0,
        # Include a duplicated return track.
        return_tracks=[*live_set.return_tracks, live_set.return_tracks[0]],
        return_tracks_index=1,
    )

    output = io.BytesIO()
    live_set.write(output)
    output.seek(0)
    modified_live_set = LiveSet(output)

    expected_send_values = tuple(
        # For simplicity, sends in the set are either set to the full min or full max value.
        tuple(max_send_value if is_max else min_send_value for is_max in is_maxes)
        for is_maxes in (
            # Inserted primary track. This should have the send for both inserted instances of return track A (at index
            # 1 and 3) turned on, and all others turned off.
            (False, True, False, True, False),
            # Original primary track 0. This should have the send for the first return track still turned on, and all
            # others turned off.
            (True, False, False, False, False),
            # Original primary track 1. All sends should be off.
            (False, False, False, False, False),
            # Original return track A. This should have the send for original return track B (now at the end of the
            # return track list) turned on.
            (False, False, False, False, True),
            # First inserted return track A. This should have the send for the inserted return track B turned on.
            (False, False, True, False, False),
            # Inserted return track B. All sends should be off.
            (False, False, False, False, False),
            # Second inserted return track A. Should be the same as the first.
            (False, False, True, False, False),
            # Original return track B. All sends should be off.
            (False, False, False, False, False),
        )
    )
    actual_send_values = get_send_values(modified_live_set)
    assert (
        actual_send_values == expected_send_values
    ), f"Unexpected send values in modified set: {actual_send_values} (expected {expected_send_values})"

    # Ensure there are no sends on the main track.
    assert len(modified_live_set.main_track.device_chain.mixer.sends.track_send_holders) == 0

    # Ensure TrackSendHolder IDs increase from 0.
    for track in [*modified_live_set.primary_tracks, *modified_live_set.return_tracks]:
        assert tuple(
            track_send_holder.id for track_send_holder in track.device_chain.mixer.sends.track_send_holders
        ) == (0, 1, 2, 3, 4)

    # Ensure that SendsPre states get carried over.
    assert [t.send_pre for t in live_set.return_tracks] == [True, True, False, True, False]
