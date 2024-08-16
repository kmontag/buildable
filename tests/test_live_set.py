from __future__ import annotations

import difflib
import gzip
import io
import os
import subprocess
import tempfile

# We need to support python back to 3.8, so use pre-PEP-585 imports.
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Sequence, Set, Tuple

import pytest
from typeguard import typechecked

from buildable import LiveSet
from buildable.live_set import DuplicatePointeeIdError, GroupTrack, KeyMidiMapping, PrimaryTrack, ReturnTrack

if TYPE_CHECKING:
    import pathlib
    from typing import Final, Iterable


@pytest.fixture
@typechecked
def live_12_default_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "live-12-default.als"


# A set with grouped tracks.
@pytest.fixture
@typechecked
def groups_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "groups.als"


# A set with mapped examples of all supported key/MIDI mappings.
@pytest.fixture
@typechecked
def key_midi_mappings_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "key-midi-mappings.als"


# A set with track-to-track routing (audio and MIDI).
@pytest.fixture
@typechecked
def routing_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "routing.als"


@pytest.fixture
@typechecked
def sends_set(datadir: pathlib.Path) -> pathlib.Path:
    return datadir / "sends.als"


# Get a version of the set which has been written to an IO stream, as well as the set as-is. This allows testing that
# changes are visible both before and after a set has been written to disk.
#
# If the OPEN_SETS_WITH environment variable is set to a Live executable path
# (e.g. OPEN_SETS_WITH="/Applications/Ableton Live 12 Suite.app/Contents/MacOS/Live"), the set will also be opened in
# Live from a temporary location on disk. Test execution will be paused until the Live window is closed manually. This
# allows debugging and validating test cases manually in the actual Live environment.
def saved_and_unsaved_sets(live_set: LiveSet) -> Iterable[LiveSet]:
    output = io.BytesIO()
    live_set.write(output)

    output.seek(0)
    saved_live_set = LiveSet(output)

    # Open the set for debugging/validation if appropriate.
    open_sets_with = os.getenv("OPEN_SETS_WITH")
    if open_sets_with:
        # Adapted from
        # https://stackoverflow.com/questions/17726954/py-test-how-to-get-the-current-tests-name-from-the-setup-method.
        pytest_current_test = os.getenv("PYTEST_CURRENT_TEST")
        assert pytest_current_test is not None
        test_name = pytest_current_test.split(":")[-1].split(" ")[0]

        # Create a temporary file.
        with tempfile.NamedTemporaryFile(prefix=test_name, suffix=".als") as temp_file:
            output.seek(0)
            temp_file.write(output.read())

            # Open the file with the specified Live executable.
            subprocess.run([open_sets_with, temp_file.name], check=False)
    yield saved_live_set
    yield live_set


# Check for some known issues that cause Live to crash or fail to load the set.
def assert_live_set_valid(live_set: LiveSet) -> None:
    # No duplicate pointee IDs.
    pointee_ids: Set[str] = set()
    for element in live_set.element.iter():
        if (
            element.tag in {"AutomationTarget", "Pointee"}
            or element.tag.startswith("ControllerTargets.")
            or element.tag.endswith("ModulationTarget")
        ):
            element_pointee_id: str | None = element.attrib.get("Id", None)
            assert element_pointee_id is not None
            assert element_pointee_id not in pointee_ids, f"Duplicate pointee ID on {element.tag}: {element_pointee_id}"
            pointee_ids.add(element_pointee_id)

    # Next pointee ID should exceed the current max.
    max_pointee_id = max(int(p) for p in pointee_ids)
    next_pointee_id = live_set._next_pointee_id  # noqa: SLF001
    assert (
        next_pointee_id > max_pointee_id
    ), f"Next pointee ID ({next_pointee_id}) is less than current max pointee ID ({max_pointee_id})"

    # SendPreBool and TrackSendHolder IDs should be increasing from 0. There are no known issues if the IDs are out of
    # order, but Live's native behavior is to keep them in order.
    expected_length = len(live_set.return_tracks)
    expected_ids = list(range(expected_length))

    send_pre_bool_ids = [s.id for s in live_set.sends_pre.send_pre_bools]
    assert (
        send_pre_bool_ids == expected_ids
    ), f"Expected SendPreBool IDs to increase from 0 to {expected_length - 1}, but got: {send_pre_bool_ids}"

    for track in (*live_set.primary_tracks, *live_set.return_tracks):
        track_send_holder_ids = [t.id for t in track.device_chain.mixer.sends.track_send_holders]
        assert (
            track_send_holder_ids == expected_ids
        ), f"Expected TrackSendHolder IDs for track {track} to increase from 0 to {expected_length - 1}, but got {track_send_holder_ids}"


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
        diff_str = "\n".join(diff)
        assert rendered_xml == original_xml, f"Rendered XML differs from original:\n\n{diff_str}"


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

    for modified_live_set in saved_and_unsaved_sets(live_set):
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

        assert_live_set_valid(modified_live_set)


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

    for modified_live_set in saved_and_unsaved_sets(live_set):
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
        assert_live_set_valid(modified_live_set)


@typechecked
def test_delete_tracks(sends_set: pathlib.Path):
    live_set = LiveSet.from_file(sends_set)
    assert len(live_set.primary_tracks) == 2
    assert len(live_set.return_tracks) == 2

    # Sanity check structure...

    # The first track should have the first send turned on, and the second turned off.
    first_track = live_set.primary_tracks[0]
    assert first_track.device_chain.mixer.sends.track_send_holders[0].send.manual > 0.9
    assert first_track.device_chain.mixer.sends.track_send_holders[1].send.manual < 0.1

    # The second track should have both sends turned off.
    assert all(s.send.manual < 0.1 for s in live_set.primary_tracks[1].device_chain.mixer.sends.track_send_holders)

    # The first send should have its SendPreBool turned on.
    assert live_set.sends_pre.send_pre_bools[0].value is True
    assert live_set.sends_pre.send_pre_bools[1].value is False

    live_set.delete_primary_track(1)
    live_set.delete_return_track(1)

    for modified_live_set in saved_and_unsaved_sets(live_set):
        # Make sure the track deletions were propagated.
        assert len(modified_live_set.primary_tracks) == 1
        assert len(modified_live_set.return_tracks) == 1

        # Make sure an element was deleted from the SendsPre config.
        assert len(live_set.sends_pre.send_pre_bools) == 1

        # Make sure a send was deleted for all tracks.
        for track in (*modified_live_set.primary_tracks, *modified_live_set.return_tracks):
            assert len(track.device_chain.mixer.sends.track_send_holders) == 1

        # Make sure the correct send was deleted.
        assert modified_live_set.primary_tracks[0].device_chain.mixer.sends.track_send_holders[0].send.manual > 0.9

        assert live_set.sends_pre.send_pre_bools[0].value is True
        assert live_set.sends_pre.send_pre_bools[0].id == 0

        assert_live_set_valid(modified_live_set)


@typechecked
def test_move_tracks(sends_set: pathlib.Path):
    live_set = LiveSet.from_file(sends_set)
    assert len(live_set.primary_tracks) == 2
    assert len(live_set.return_tracks) == 2

    # Sanity check structure...

    # The first track should have the first send turned on, and the second turned off.
    first_track = live_set.primary_tracks[0]
    assert first_track.device_chain.mixer.sends.track_send_holders[0].send.manual > 0.9
    assert first_track.device_chain.mixer.sends.track_send_holders[1].send.manual < 0.1

    # The second track should have both sends turned off.
    assert all(s.send.manual < 0.1 for s in live_set.primary_tracks[1].device_chain.mixer.sends.track_send_holders)

    # The first send should have its SendPreBool turned on.
    assert live_set.sends_pre.send_pre_bools[0].value is True
    assert live_set.sends_pre.send_pre_bools[1].value is False

    # Get return track names so we can verify they were moved.
    return_track_names = [track.effective_name for track in live_set.return_tracks]

    live_set.move_primary_track(0, 1)
    live_set.move_return_track(0, 1)

    for modified_live_set in saved_and_unsaved_sets(live_set):
        # Make sure the primary track and associated send were moved.
        assert all(
            s.send.manual < 0.1 for s in modified_live_set.primary_tracks[0].device_chain.mixer.sends.track_send_holders
        )
        second_track = modified_live_set.primary_tracks[1]
        assert second_track.device_chain.mixer.sends.track_send_holders[1].send.manual > 0.9
        assert second_track.device_chain.mixer.sends.track_send_holders[0].send.manual < 0.1

        # The first send should have its SendPreBool turned on.
        assert live_set.sends_pre.send_pre_bools[1].value is True
        assert live_set.sends_pre.send_pre_bools[0].value is False

        assert [track.effective_name for track in modified_live_set.return_tracks] == list(reversed(return_track_names))

        assert_live_set_valid(modified_live_set)


@typechecked
def test_track_group_ids_updated(groups_set: pathlib.Path):
    live_set = LiveSet.from_file(groups_set)

    primary_track_ids, return_track_ids = (
        [track.id for track in tracks] for tracks in (live_set.primary_tracks, live_set.return_tracks)
    )
    next_track_id = max(primary_track_ids + return_track_ids) + 1
    live_set.insert_primary_tracks(live_set.primary_tracks)

    for modified_live_set in saved_and_unsaved_sets(live_set):
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

        assert_live_set_valid(modified_live_set)


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

    expected_routing_targets: Dict[str, List[str]] = {
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
        targets: List[str] = expected_routing_targets[routing_attr]
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

    for modified_live_set in saved_and_unsaved_sets(live_set):
        for routing_attr, expected_targets in expected_routing_targets.items():
            targets = [getattr(t.device_chain, routing_attr).target for t in modified_live_set.primary_tracks]
            assert (
                targets == expected_targets
            ), f"Incorrect {routing_attr} targets - got {targets}, expected {expected_targets}"

        assert_live_set_valid(modified_live_set)


@typechecked
def test_sends_inserted(sends_set: pathlib.Path):
    live_set = LiveSet.from_file(sends_set)

    # All sends should have the same min value.
    example_send = live_set.primary_tracks[0].device_chain.mixer.sends.track_send_holders[0].send
    min_send_value = example_send.midi_controller_range.min
    max_send_value = example_send.midi_controller_range.max
    assert max_send_value == 1.0  # Sanity check.

    # Get all send values for primary and return tracks (in that order) in the given set.
    def get_send_manual_values(live_set: LiveSet) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple(
                track_send_holder.send.manual for track_send_holder in track.device_chain.mixer.sends.track_send_holders
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

    actual_send_values = get_send_manual_values(live_set)
    assert (
        actual_send_values == expected_send_values
    ), f"Unexpected send values in unmodified set: {actual_send_values} (expected {expected_send_values})"

    original_num_return_tracks = len(live_set.return_tracks)
    live_set.insert_tracks(
        # Copy the main track.
        main_track=live_set.main_track,
        # Include a primary track with the duplicated return active.
        primary_tracks=[live_set.primary_tracks[0]],
        primary_tracks_index=0,
        # Include a duplicated return track.
        return_tracks=live_set.return_tracks,
        return_tracks_index=1,
    )

    # Add a duplicate of one of the return tracks, this time disconnected from the rest of the group, directly after the
    # return tracks that were previously inserted.
    live_set.insert_return_tracks([live_set.return_tracks[0]], 1 + original_num_return_tracks)

    for modified_live_set in saved_and_unsaved_sets(live_set):
        # Make sure the high/low send values were preserved during each track insertion.
        expected_send_values = tuple(
            # For simplicity, sends in the set are either set to the full min or full max value.
            tuple(max_send_value if is_max else min_send_value for is_max in is_maxes)
            for is_maxes in (
                # Inserted primary track. This should have the send for the first inserted instance of return track A
                # (at index 1) turned on, and all others turned off.
                (False, True, False, False, False),
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
                # Second inserted return track A. Disconnected from the rest of the tracks, so it should be all off.
                (False, False, False, False, False),
                # Original return track B. All sends should be off.
                (False, False, False, False, False),
            )
        )
        actual_send_values = get_send_manual_values(modified_live_set)
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
        assert [t.send_pre for t in modified_live_set.return_tracks] == [True, True, False, True, False]

        assert len(modified_live_set.return_tracks) == 5

        assert_live_set_valid(modified_live_set)


@typechecked
def test_simultaneous_duplicate_track_inserts_disallowed(live_12_default_set: pathlib.Path):
    live_set = LiveSet.from_file(live_12_default_set)
    assert len(live_set.primary_tracks) == 4

    with pytest.raises(DuplicatePointeeIdError):
        # Adding two items with duplicated pointee IDs makes pointee mappings ambiguous, so it's disallowed.
        live_set.insert_primary_tracks([live_set.primary_tracks[0], live_set.primary_tracks[0]])

    # Check that duplicate tracks can, however, be inserted in sequence, in different pointee ID translation contexts.
    live_set = LiveSet.from_file(live_12_default_set)

    live_set.insert_primary_tracks([live_set.primary_tracks[0]])
    live_set.insert_primary_tracks([live_set.primary_tracks[0]])

    for modified_live_set in saved_and_unsaved_sets(live_set):
        assert len(modified_live_set.primary_tracks) == 6
        assert_live_set_valid(modified_live_set)


@typechecked
def test_key_midi_mappings(key_midi_mappings_set: pathlib.Path):
    live_set = LiveSet.from_file(key_midi_mappings_set)

    # Mapping names for various targets which are mapped to keys in the test set. For simplicity, we use keys rather
    # than MIDI for almost every mapping; MIDI is tested with a more limited set of mappings below.
    key_mapping_names_by_target_getter: Mapping[Callable[[LiveSet], Any], Sequence[str]] = {
        # Mapping names are listed in the order they appear in the "Key Mappings" pane whne sorting by path.
        lambda s: s: (
            # This shows up under "Transport" in the UI.
            "global_quantisation_key_midi",
        ),
        lambda s: s.main_track: (
            "key_midi_crossfade_equal",
            "key_midi_tempo_fine",
            "key_midi_fire_selected_scene",
            "key_midi_cancel_launch",
            "key_midi_scene_up",
            "key_midi_scene_down",
            "key_midi_scroll_selected_scene",
        ),
        lambda s: s.main_track.device_chain.mixer: (
            "stop_key_midi",  # Stop clips.
        ),
        lambda s: s.main_track.device_chain.mixer.global_groove_amount: ("key_midi",),
        lambda s: s.return_tracks[0].device_chain.mixer.sends.track_send_holders[0].send: ("key_midi",),
        lambda s: s.transport: (
            "phase_nudge_up_key_midi",
            "phase_nudge_down_key_midi",
            "tap_tempo_key_midi",
            "start_key_midi",
            "stop_key_midi",
            "record_key_midi",
            "session_record_key_midi",
            "prepare_scene_for_new_recording_key_midi",
            "arrangement_overdub_key_midi",
            "automation_arm_key_midi",
            "back_to_arrangement_key_midi",
            "re_enable_automation_key_midi",
            "loop_on_key_midi",
            "punsh_in_key_midi",
            "punsh_out_key_midi",
            "draw_button_key_midi",
            "follow_key_midi",
            "metronom_on_key_midi",
            "trigger_capture_key_midi",
            "follow_action_enabled_key_midi",
            "is_tempo_follower_in_control_key_midi",
            # Note: quantization is also listed under the "Transport" path in the UI, but it actually lives on the root
            # set object.
        ),
    }

    midi_mapping_names_by_target_getter: Mapping[Callable[[LiveSet], Any], Sequence[str]] = {
        lambda s: s.main_track.device_chain.mixer.tempo: ("key_midi",),
        lambda s: s.pre_hear_track.device_chain.mixer.volume: ("key_midi",),
    }

    # In the test set, all main/transport elements are mapped to either "a", "b", or "c" (we need 3 keys to avoid conflicts
    # that are disallowed by Live). Make sure we can read these mappings, then update them and check that the updates
    # get applied.
    original_to_updated_keys: Final = {"a": "x", "b": "y", "c": "z"}

    # List of targets, mapping names, and a dictionary of mapping name -> updated key string.
    key_targets_to_process: Sequence[Tuple[Any, Sequence[str], Dict[str, str]]] = [
        (target, mapping_names, {}) for target, mapping_names in key_mapping_names_by_target_getter.items()
    ]

    for get_target, mapping_names, updated_key_strings in key_targets_to_process:
        target = get_target(live_set)
        for mapping_name in mapping_names:
            mapping = getattr(target, mapping_name)
            assert isinstance(mapping, KeyMidiMapping)

            # Check that we correctly read the mapping as being set.
            assert (
                mapping.persistent_key_string in original_to_updated_keys
            ), f'Unrecognized key mapping for {mapping_name} on {target}: "{mapping.persistent_key_string}"'

            # Update the mapping and store the updated value.
            updated_key_string = original_to_updated_keys[mapping.persistent_key_string]
            mapping.persistent_key_string = updated_key_string
            updated_key_strings[mapping_name] = updated_key_string

    # Simpler test for MIDI mappings, of which there are only a handful, and which are all bound to the same
    # parameter. Aside from the properties being set on the `KeyMidiMapping` object, there isn't any known difference
    # that needs to be taken into account when handling MIDI vs key mappings, so there's no need to test more of these.
    for get_target, mapping_names in midi_mapping_names_by_target_getter.items():
        target = get_target(live_set)
        for mapping_name in mapping_names:
            mapping = getattr(target, mapping_name)
            assert isinstance(mapping, KeyMidiMapping)

            assert mapping.channel == 0  # MIDI channel 1.
            assert mapping.note_or_controller == 1  # Mod wheel.
            mapping.channel = 1
            mapping.note_or_controller = 2

    for modified_live_set in saved_and_unsaved_sets(live_set):
        for get_target, mapping_names, updated_key_strings in key_targets_to_process:
            target = get_target(modified_live_set)
            for mapping_name in mapping_names:
                mapping = getattr(target, mapping_name)
                assert isinstance(mapping, KeyMidiMapping)

                # Check that the updated mapping was correctly saved.
                assert (
                    mapping.persistent_key_string == updated_key_strings[mapping_name]
                ), f'Incorrect updated key mapping for {mapping_name}: "{mapping.persistent_key_string}" (expected "{updated_key_strings[mapping_name]}")'

        # Check that the updated MIDI mappings were correctly saved.
        for get_target, mapping_names in midi_mapping_names_by_target_getter.items():
            target = get_target(live_set)
            for mapping_name in mapping_names:
                mapping = getattr(target, mapping_name)
                assert isinstance(mapping, KeyMidiMapping)
                assert mapping.channel == 1
                assert mapping.note_or_controller == 2
        assert_live_set_valid(modified_live_set)
