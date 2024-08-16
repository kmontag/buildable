from __future__ import annotations

import copy
import json
import re
from functools import cached_property, partial
from typing import TYPE_CHECKING, Callable, Collection, TypeVar

from lxml.etree import fromstring

from .base import AbletonDocumentObject, ElementObject, GenericProperty, child_element_object_property, xml_property
from .util import override

if TYPE_CHECKING:
    from typing import BinaryIO, Final, Sequence

    from lxml.etree import _Element

    # Introduced in 3.11.
    from typing_extensions import Self


_U = TypeVar("_U")


class DuplicatePointeeIdError(ValueError):
    pass


class KeyMidiMapping:
    """Describes a key and/or MIDI mapping for a particular target.

    When accessing or modifying the mapping, the appropriate XML element will be created inside the parent element if it
    doesn't already exist.

    """

    def __init__(
        self,
        # The containing element.
        parent: _Element,
        # The tag name, which determines the target of this mapping. In places where the target is non-ambiguous
        # (e.g. inside the global mixer's Tempo object), this is generally simply "KeyMidi". Otherwise, this will be a
        # more descriptive tag name, like "KeyMidiSceneUp".
        tag: str,
    ):
        self._parent = parent
        self._tag = tag

    # Get or create the underlying key/MIDI element.
    #
    # For now this has the side effect that XML elements will be created within the parent even when simply getting (not
    # setting) mapping properties, but in practice this doesn't appear to affect anything.
    def _get_element(self) -> _Element:
        element = self._parent.find(self._tag)

        # Create the element if it doesn't already exist.
        if element is None:
            element = fromstring(f"""
                <{self._tag}>
                    <PersistentKeyString Value="" />
                    <IsNote Value="false" />
                    <Channel Value="-1" />
                    <NoteOrController Value="-1" />
                    <LowerRangeNote Value="-1" />
                    <UpperRangeNote Value="-1" />
                    <ControllerMapMode Value="0" />
                </{self._tag}>
            """)  # noqa: S320

            self._parent.append(element)
        return element

    @xml_property(attrib="Value", property_type=str)
    def persistent_key_string(self) -> _Element:
        return _presence(self._get_element().find("PersistentKeyString"))

    @xml_property(attrib="Value", property_type=bool)
    def is_note(self) -> _Element:
        return _presence(self._get_element().find("IsNote"))

    @xml_property(attrib="Value", property_type=int)
    def channel(self) -> _Element:
        return _presence(self._get_element().find("Channel"))

    @xml_property(attrib="Value", property_type=int)
    def note_or_controller(self) -> _Element:
        return _presence(self._get_element().find("NoteOrController"))

    @xml_property(attrib="Value", property_type=int)
    def lower_range_note(self) -> _Element:
        return _presence(self._get_element().find("LowerRangeNote"))

    @xml_property(attrib="Value", property_type=int)
    def upper_range_note(self) -> _Element:
        return _presence(self._get_element().find("UpperRangeNote"))

    # TODO: add constants for possible values here.
    @xml_property(attrib="Value", property_type=int)
    def controller_map_mode(self) -> _Element:
        return _presence(self._get_element().find("ControllerMapMode"))


def key_midi_mapping(
    # If None, the upper-camelcased property name will be used as the tag name.
    tag: str | None = None,
) -> Callable[[Callable[[_U], _Element]], GenericProperty[KeyMidiMapping]]:
    """Get a decorator which exposes a key/MIDI mapping, creating it if it doesn't already exist.

    The decorated function should return the element which (possibly) contains the key/MIDI mapping.
    """

    def inner(fn: Callable[[_U], _Element]) -> GenericProperty[KeyMidiMapping]:
        inferred_tag: str
        if tag is None:
            property_name = fn.__name__
            if property_name is None:
                msg = "Tag name could not be inferred from callable."
                raise ValueError(msg)
            # Convert underscored name to upper camelcase.
            inferred_tag = "".join(w.capitalize() for w in property_name.split("_"))
        else:
            inferred_tag = tag

        # Use this to cache the result per-instance. Adapted from
        # https://stackoverflow.com/questions/59929626/cache-results-of-properties-in-python-through-a-decorator.
        cache_key = f"__key_midi_mapping_{fn.__name__}"

        def getter(instance: _U) -> KeyMidiMapping:
            parent = fn(instance)
            if cache_key not in instance.__dict__:
                instance.__dict__[cache_key] = KeyMidiMapping(parent, inferred_tag)
            return instance.__dict__[cache_key]

        return property(fget=getter)

    return inner


class AutomationOrModulationTarget(ElementObject):
    @xml_property(attrib="Id", property_type=int)
    def id(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=bool)
    def lock_envelope(self) -> _Element:
        return _presence(self.element.find("LockEnvelope"))


class AutomationTarget(AutomationOrModulationTarget):
    TAG = "AutomationTarget"


class ModulationTarget(AutomationOrModulationTarget):
    TAG = "ModulationTarget"


class MidiControllerRange(ElementObject):
    TAG = "MidiControllerRange"

    @xml_property(attrib="Value", property_type=float)
    def min(self) -> _Element:
        return _presence(self.element.find("Min"))

    @xml_property(attrib="Value", property_type=float)
    def max(self) -> _Element:
        return _presence(self.element.find("Max"))


class AutomatableElementObject(ElementObject):
    """Common structure for an element that can be automated.

    Most of these objects are also `ModulableElementObject`s, but there are a handful of properties (e.g. the time
    signature) which can be automated but not assigned to a modulator.

    """

    @xml_property(attrib="Value", property_type=int)
    def lom_id(self) -> _Element:
        return _presence(self.element.find("LomId"))

    @xml_property(attrib="Value", property_type=float)
    def manual(self) -> _Element:
        return _presence(self.element.find("Manual"))

    @child_element_object_property(property_type=AutomationTarget)
    def automation_target(self) -> _Element:
        return self.element


class ModulableElementObject(AutomatableElementObject):
    """Common structure for an element that can be modulated over a range of possible values.

    Objects of this type can be key/MIDI mapped (though not all mappable parameters can be described by such an object). For example, objects describing the set tempo and track send values inherit from this type.
    """

    @key_midi_mapping()
    def key_midi(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=MidiControllerRange)
    def midi_controller_range(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=ModulationTarget)
    def modulation_target(self) -> _Element:
        return self.element


class SendsPre(ElementObject):
    TAG = "SendsPre"

    @property
    def send_pre_bools(self) -> Sequence[SendPreBool]:
        # All children should be of this type.
        return [SendPreBool(child) for child in self.element]

    def insert_send_pre_bool(self, index: int, value: bool) -> None:  # noqa: FBT001
        xml_str = f'<{SendPreBool.TAG} Id="{index}" Value="{json.dumps(value)}" />'

        # Our element looks like:
        #
        # <SendsPre>
        #   <SendPreBool Id="0" Value="true">
        #   <SendPreBool Id="1" Value="false">
        #   <SendPreBool Id="2" Value="true">
        #   <!-- ... -->
        # </SendsPre>

        # Insert the new child element at the appropriate index.
        new_element = fromstring(xml_str)  # noqa: S320
        self.element.insert(index, new_element)

        # Update the ID attributes of elements that come after the inserted element.
        for i, send_pre_bool in list(enumerate(self.send_pre_bools))[index + 1 :]:
            # Sanity check.
            if send_pre_bool.id != i - 1:
                msg = f"Unexpected SendPreBool ID at position {i}: {send_pre_bool.id}"
                raise AssertionError(msg)
            send_pre_bool.id = i

    def delete_send_pre_bool(self, index: int) -> None:
        send_pre_bools = self.send_pre_bools

        # Ensure the index is within bounds.
        if index < 0 or index >= len(send_pre_bools):
            msg = f"SendPreBool index out of bounds: {index}"
            raise IndexError(msg)

        # Remove the element at the given index.
        del self.element[index]

        # Decrement the ID attributes of the remaining elements.
        for i, send_pre_bool in list(enumerate(self.send_pre_bools))[index:]:
            send_pre_bool.id = i

    def move_send_pre_bool(self, from_index: int, to_index: int) -> None:
        # Ensure indices are within bounds.
        send_pre_bools = self.send_pre_bools
        if from_index < 0 or from_index >= len(send_pre_bools) or to_index < 0 or to_index >= len(send_pre_bools):
            msg = f"SendPreBool index out of bounds: from {from_index} to {to_index}"
            raise IndexError(msg)

        # Move the element.
        element = self.element[from_index]
        del self.element[from_index]

        self.element.insert(to_index, element)

        # Update the ID attributes.
        for i, send_pre_bool in enumerate(self.send_pre_bools):
            send_pre_bool.id = i


class SendPreBool(ElementObject):
    TAG = "SendPreBool"

    @xml_property(attrib="Id", property_type=int)
    def id(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=bool)
    def value(self) -> _Element:
        return self.element


class Routing(ElementObject):
    """Common format for audio and MIDI I/O configurations."""

    @xml_property(attrib="Value", property_type=str)
    def target(self) -> _Element:
        return _presence(self.element.find("Target"))

    @xml_property(attrib="Value", property_type=str)
    def upper_display_string(self) -> _Element:
        return _presence(self.element.find("UpperDisplayString"))

    @xml_property(attrib="Value", property_type=str)
    def lower_display_string(self) -> _Element:
        return _presence(self.element.find("LowerDisplayString"))


class AudioInputRouting(Routing):
    TAG = "AudioInputRouting"


class AudioOutputRouting(Routing):
    TAG = "AudioOutputRouting"


class MidiInputRouting(Routing):
    TAG = "MidiInputRouting"


class MidiOutputRouting(Routing):
    TAG = "MidiOutputRouting"


class Send(ModulableElementObject):
    """Represents the value of a send on a particular track.

    This is generally contained within a TrackSendHolder.

    """

    TAG = "Send"

    # Live saves "zero-valued" sends with this slightly-nonzero value - we use this when creating new sends to match the
    # default behavior, but it's also fine to set e.g. `send.value = 0`.
    _MIN_VALUE_STR: Final[str] = "0.0003162277571"

    @classmethod
    def create(cls, *, automation_target_id: int, modulation_target_id: int) -> Self:
        """Create a new Send element.

        The element's value will be set to the minimum allowed (though this can be adjusted later by setting the
        instance's 'value' property).
        """

        xml_str = f"""
            <{cls.TAG}>
                <LomId Value="0" />
                <Manual Value="{cls._MIN_VALUE_STR}" />
                <MidiControllerRange>
                    <Min Value="{cls._MIN_VALUE_STR}" />
                    <Max Value="1" />
                </MidiControllerRange>
                <AutomationTarget Id="{automation_target_id}">
                    <LockEnvelope Value="0" />
                </AutomationTarget>
                <ModulationTarget Id="{modulation_target_id}">
                    <LockEnvelope Value="0" />
                </ModulationTarget>
            </{cls.TAG}>
        """

        return cls(fromstring(xml_str))  # noqa: S320


class TrackSendHolder(ElementObject):
    TAG = "TrackSendHolder"

    @xml_property(attrib="Id", property_type=int)
    def id(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=bool)
    def enabled_by_user(self) -> _Element:
        return _presence(self.element.find("EnabledByUser"))

    @child_element_object_property(property_type=Send)
    def send(self) -> _Element:
        return self.element


class Sends(ElementObject):
    """Contains all Send objects (wrapped in TrackSendHolder objects) for a particular track."""

    TAG = "Sends"

    @property
    def track_send_holders(self) -> Sequence[TrackSendHolder]:
        # This should be the only child element type.
        return [TrackSendHolder(child) for child in self.element]

    def insert_send(self, index: int, send: Send, *, enabled_by_user: bool = False) -> None:
        track_send_holder_element = fromstring(  # noqa: S320
            f"""
            <{TrackSendHolder.TAG} Id="{index}">
                <EnabledByUser Value="{json.dumps(enabled_by_user)}" />
            </{TrackSendHolder.TAG}>
            """
        )
        # Prepend the <Send> element to the send holder.
        track_send_holder_element.insert(0, copy.deepcopy(send.element))

        # Add the send holder at the appropriate position.
        self.element.insert(index, track_send_holder_element)

        # Update IDs of existing track send holders.
        for i, existing_track_send_holder in enumerate(list(self.track_send_holders)[index + 1 :], start=index + 1):
            if existing_track_send_holder.id != i - 1:
                msg = f"Unexpected ID ({existing_track_send_holder.id}) for track send holder at index {i}"
                raise AssertionError(msg)
            existing_track_send_holder.id = i

    def delete_send(self, index: int) -> None:
        if self.element[index].tag != TrackSendHolder.TAG:
            msg = f"Unexpected child element: {self.element[index].tag}"
            raise AssertionError(msg)
        del self.element[index]

        # Update IDs of remaining track send holders.
        for i, existing_track_send_holder in enumerate(self.track_send_holders):
            existing_track_send_holder.id = i

    def move_send(self, from_index: int, to_index: int) -> None:
        # Ensure indices are within bounds.
        track_send_holders = self.track_send_holders
        if (
            from_index < 0
            or from_index >= len(track_send_holders)
            or to_index < 0
            or to_index >= len(track_send_holders)
        ):
            msg = f"TrackSendHolder index out of bounds: from {from_index} to {to_index}"
            raise IndexError(msg)

        # Move the element.
        element = self.element[from_index]
        del self.element[from_index]

        self.element.insert(to_index, element)

        # Update the ID attributes.
        for i, track_send_holder in enumerate(self.track_send_holders):
            track_send_holder.id = i


class Transport(ElementObject):
    TAG = "Transport"

    # Key/MIDI mappings. Tag names are inferred from the property names.

    @key_midi_mapping()
    def arrangement_overdub_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def automation_arm_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def back_to_arrangement_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def draw_button_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def follow_action_enabled_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def follow_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def is_tempo_follower_in_control_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def loop_on_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def metronom_on_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def phase_nudge_down_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def phase_nudge_up_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def prepare_scene_for_new_recording_key_midi(self) -> _Element:
        return self.element

    # [sic]
    @key_midi_mapping()
    def punsh_in_key_midi(self) -> _Element:
        return self.element

    # [sic]
    @key_midi_mapping()
    def punsh_out_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def re_enable_automation_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def record_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def session_record_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def start_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def stop_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def tap_tempo_key_midi(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def trigger_capture_key_midi(self) -> _Element:
        return self.element


class CrossFade(ModulableElementObject):
    TAG = "CrossFade"


class GlobalGrooveAmount(ModulableElementObject):
    TAG = "GlobalGrooveAmount"


class TimeSignature(AutomatableElementObject):
    TAG = "TimeSignature"


class Tempo(ModulableElementObject):
    TAG = "Tempo"


class Volume(ModulableElementObject):
    TAG = "Volume"


class Mixer(ElementObject):
    TAG = "Mixer"

    # Properties that only appear on primary/return tracks.

    @child_element_object_property(property_type=Sends)
    def sends(self) -> _Element:
        return self.element

    # Properties that only appear on the main track.

    @child_element_object_property(property_type=GlobalGrooveAmount)
    def global_groove_amount(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def stop_key_midi(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=Tempo)
    def tempo(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=int)
    def view_state_sesstion_track_width(self) -> _Element:
        # [sic]
        return _presence(self.element.find("ViewStateSesstionTrackWidth"))

    @child_element_object_property(property_type=Volume)
    def volume(self) -> _Element:
        return self.element


class DeviceChain(ElementObject):
    TAG = "DeviceChain"

    @child_element_object_property(property_type=AudioInputRouting)
    def audio_input_routing(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=AudioOutputRouting)
    def audio_output_routing(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=MidiInputRouting)
    def midi_input_routing(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=MidiOutputRouting)
    def midi_output_routing(self) -> _Element:
        return self.element

    @child_element_object_property(property_type=Mixer)
    def mixer(self) -> _Element:
        return self.element


class Track(ElementObject):
    @xml_property(attrib="Value", property_type=bool)
    def is_content_selected_in_document(self) -> _Element:
        return _presence(self.element.find("IsContentSelectedInDocument"))

    @xml_property(attrib="Value", property_type=str)
    def effective_name(self) -> _Element:
        return _presence(_presence(self.element.find("Name")).find("EffectiveName"))

    @xml_property(attrib="Value", property_type=str)
    def user_name(self) -> _Element:
        return _presence(_presence(self.element.find("Name")).find("UserName"))

    @xml_property(attrib="Value", property_type=int)
    def linked_track_group_id(self) -> _Element:
        return _presence(self.element.find("LinkedTrackGroupId"))

    @property
    def device_chain(self) -> DeviceChain:
        return DeviceChain(_presence(self.element.find(DeviceChain.TAG)))

    def __repr__(self) -> str:
        return f"{self.element.tag}({self.effective_name})"


class MixerTrack(Track):
    @xml_property(attrib="Id", property_type=int)
    def id(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=int)
    def track_group_id(self) -> _Element:
        return _presence(self.element.find("TrackGroupId"))


class PrimaryTrack(MixerTrack):
    @staticmethod
    def types() -> Collection[type[PrimaryTrack]]:
        return {AudioTrack, GroupTrack, MidiTrack}

    @staticmethod
    def from_element(element: _Element) -> PrimaryTrack:
        for primary_track_type in PrimaryTrack.types():
            if element.tag == primary_track_type.TAG:
                return primary_track_type(element)
        msg = f"Unrecognized primary track tag: {element.tag}"
        raise ValueError(msg)


class AudioTrack(PrimaryTrack):
    TAG = "AudioTrack"


class GroupTrack(PrimaryTrack):
    TAG = "GroupTrack"


class MidiTrack(PrimaryTrack):
    TAG = "MidiTrack"


class ReturnTrack(MixerTrack):
    TAG = "ReturnTrack"

    # In addition to the XML element, return tracks need some additional context to preserve their relationships to
    # other elements in the set.
    def __init__(self, element: _Element, *, send_index: int, send_pre: bool) -> None:
        super().__init__(element)
        self._send_index = send_index
        self._send_pre = send_pre

    @property
    def send_index(self) -> int:
        return self._send_index

    @property
    def send_pre(self) -> bool:
        return self._send_pre


class MainTrack(Track):
    TAG = "MainTrack"

    @key_midi_mapping()
    def key_midi_fire_selected_scene(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_cancel_launch(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_scene_up(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_scene_down(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_scroll_selected_scene(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_crossfade_equal(self) -> _Element:
        return self.element

    @key_midi_mapping()
    def key_midi_tempo_fine(self) -> _Element:
        return self.element


class PreHearTrack(Track):
    TAG = "PreHearTrack"


class LiveSet(AbletonDocumentObject):
    ELEMENT_TAG: Final[str] = "LiveSet"

    @override
    def __init__(self, data: BinaryIO) -> None:
        super().__init__(data)

        if self._element.tag != self.ELEMENT_TAG:
            msg = f"Invalid element tag name: '{self._element.tag}' (expected '{self.ELEMENT_TAG}')"
            raise ValueError(msg)

        # Validate tracks element.
        did_find_return_track = False
        for track_element in self._tracks_element:
            if track_element.tag not in [ReturnTrack.TAG, *[t.TAG for t in PrimaryTrack.types()]]:
                msg = f"Unrecognized track tag: {track_element.tag}"
                raise ValueError(msg)

            if track_element.tag == ReturnTrack.TAG:
                did_find_return_track = True

            if did_find_return_track and track_element.tag != ReturnTrack.TAG:
                msg = f"Set tracks are out of order: {track_element.tag} found after {ReturnTrack.TAG}"
                raise ValueError(msg)

    @property
    def main_track(self) -> MainTrack:
        return MainTrack(_presence(self._element.find("MainTrack")))

    @main_track.setter
    def main_track(self, main_track: MainTrack):
        self.insert_tracks(main_track=main_track)

    @property
    def primary_tracks(self) -> Sequence[PrimaryTrack]:
        return [PrimaryTrack.from_element(track) for track in self._tracks_element if track.tag != ReturnTrack.TAG]

    @property
    def return_tracks(self) -> Sequence[ReturnTrack]:
        return [
            ReturnTrack(track, send_index=index, send_pre=self.sends_pre.send_pre_bools[index].value)
            for index, track in enumerate(t for t in self._tracks_element if t.tag == ReturnTrack.TAG)
        ]

    @child_element_object_property(property_type=PreHearTrack)
    def pre_hear_track(self) -> _Element:
        return self._element

    @child_element_object_property(property_type=SendsPre)
    def sends_pre(self) -> _Element:
        return self._element

    @child_element_object_property(property_type=Transport)
    def transport(self) -> _Element:
        return self._element

    @key_midi_mapping()
    def global_quantisation_key_midi(self) -> _Element:
        return self._element

    @xml_property(attrib="Value", property_type=int)
    def _next_pointee_id(self) -> _Element:
        return _presence(self._element.find("NextPointeeId"))

    @cached_property
    def _tracks_element(self) -> _Element:
        return _presence(self._element.find("Tracks"))

    def delete_primary_track(self, index: int) -> None:
        """Delete the primary track at the given index."""
        element_to_delete = self.primary_tracks[index].element
        self._tracks_element.remove(element_to_delete)

    def delete_return_track(self, index: int) -> None:
        """Delete the return track at the given index, and the associated sends on all tracks."""
        element_to_delete = self.return_tracks[index].element

        # Remove the element itself.
        self._tracks_element.remove(element_to_delete)

        # Delete the associated SendPreBool.
        self.sends_pre.delete_send_pre_bool(index)

        # Delete the relevant TrackSendHolder for all other tracks.
        for mixer_track in [*self.primary_tracks, *self.return_tracks]:
            mixer_track.device_chain.mixer.sends.delete_send(index)

    def move_primary_track(self, from_index: int, to_index: int) -> None:
        """Move a primary track from one index to another.

        This is roughly equivalent to deleting the track and re-inserting it at the new index, except that when using
        this method, all relationships with other tracks will be preserved. Behavior is undefined if this moves a
        grouped track outside of its containing group.

        """
        if any(i < 0 or i >= len(self.primary_tracks) for i in (from_index, to_index)):
            msg = f"Primary track index out of range: from {from_index} to {to_index}"
            raise IndexError(msg)

        # Retrieve the track element to move.
        track_element = self.primary_tracks[from_index].element

        # Remove the track element from its current position.
        self._tracks_element.remove(track_element)

        # Insert the track element at its new position.
        self._tracks_element.insert(to_index, track_element)

    def move_return_track(self, from_index: int, to_index: int) -> None:
        """Move a return track from one index to another, and re-order the sends on all tracks accordingly.

        This is roughly equivalent to deleting the track and re-inserting it at the new index, except that when using
        this method, all relationships with other tracks will be preserved.

        """
        if any(i < 0 or i >= len(self.return_tracks) for i in (from_index, to_index)):
            msg = f"Primary track index out of range: from {from_index} to {to_index}"
            raise IndexError(msg)

        # Retrieve the return track element to move.
        return_track_element = self.return_tracks[from_index].element

        # Remove the element from its current position.
        self._tracks_element.remove(return_track_element)

        # Insert the element at its new position.
        self._tracks_element.insert(len(self.primary_tracks) + to_index, return_track_element)

        # Move the associated SendPreBool.
        self.sends_pre.move_send_pre_bool(from_index, to_index)

        # Move the associated sends in all tracks.
        for mixer_track in (*self.primary_tracks, *self.return_tracks):
            mixer_track.device_chain.mixer.sends.move_send(from_index, to_index)

    def insert_primary_tracks(self, primary_tracks: Sequence[PrimaryTrack], index: int = 0) -> None:
        """Insert primary tracks (i.e. a standard audio, MIDI, or group tracks) at the given index.

        All tracks must come from the same Live set. Logical relationships between them (e.g. control mappings, routing)
        will be preserved.

        Grouped tracks should always be copied along with their containing group (though it's not necessary to copy all
        tracks within a given group).

        """
        self.insert_tracks(primary_tracks=primary_tracks, primary_tracks_index=index)

    def insert_return_tracks(self, return_tracks: Sequence[ReturnTrack], index: int = 0) -> None:
        """Insert return tracks at the given index (with 0 meaning the first return track in the set).

        All tracks must come from the same Live set. Logical relationships between them (e.g. control mappings, routing)
        will be preserved.

        """
        self.insert_tracks(return_tracks=return_tracks, return_tracks_index=index)

    def insert_tracks(
        self,
        primary_tracks: Sequence[PrimaryTrack] | None = None,
        primary_tracks_index: int = 0,
        return_tracks: Sequence[ReturnTrack] | None = None,
        return_tracks_index: int = 0,
        main_track: MainTrack | None = None,
    ) -> None:
        """Insert primary and/or return tracks at the given indices, and optionally overwrite the main track.

        All tracks must come from the same Live set. Logical relationships between them (e.g. control mappings, routing)
        will be preserved.
        """

        # Validate indices.
        for index, sequence, name in (
            (primary_tracks_index, self.primary_tracks, "Primary tracks"),
            (return_tracks_index, self.return_tracks, "Return tracks"),
        ):
            if index < 0:
                msg = f"{name} index is negative: {index}"
                raise ValueError(msg)
            max_index = len(sequence)
            if index > max_index:
                msg = f"{name} index out of range: got {index}, but there are only {max_index} tracks"
                raise ValueError(msg)

        # Make deep copies of the tracks to be inserted.
        primary_tracks = [copy.deepcopy(t) for t in (primary_tracks or [])]
        return_tracks = [copy.deepcopy(t) for t in (return_tracks or [])]
        main_track = None if main_track is None else copy.deepcopy(main_track)

        # Build lists for many-track operations.
        mixer_tracks: list[MixerTrack] = [*primary_tracks, *return_tracks]
        tracks: list[Track] = mixer_tracks + ([] if main_track is None else [main_track])

        self._update_pointee_ids([t.element for t in tracks])
        self._update_track_ids(mixer_tracks)
        self._update_linked_track_group_ids(tracks)

        def add_blank_send(index: int, sends: Sends) -> None:
            automation_target_id = self._next_pointee_id
            self._next_pointee_id += 1
            modulation_target_id = self._next_pointee_id
            self._next_pointee_id += 1
            send = Send.create(automation_target_id=automation_target_id, modulation_target_id=modulation_target_id)

            sends.insert_send(index, send)

        for return_track in reversed(return_tracks):
            # Add sends to existing tracks for any inserted return tracks.
            for mixer_track in [*self.primary_tracks, *self.return_tracks]:
                add_blank_send(return_tracks_index, mixer_track.device_chain.mixer.sends)

            # Add SendsPre configurations.
            self.sends_pre.insert_send_pre_bool(return_tracks_index, return_track.send_pre)

        # Add sends for existing return tracks to inserted tracks, and remove any external sends which aren't being
        # inserted.
        for track in mixer_tracks:
            sends = track.device_chain.mixer.sends
            external_track_send_holders: list[TrackSendHolder] = [
                track.device_chain.mixer.sends.track_send_holders[return_track.send_index]
                for return_track in return_tracks
            ]

            # Delete all existing send holders from the Sends element. We'll add some of these back (in the correct
            # order) if any return tracks are being inserted.
            while len(sends.track_send_holders) > 0:
                sends.delete_send(0)

            # Add blank sends for the return tracks in this set.
            for _ in range(len(self.return_tracks)):
                add_blank_send(0, sends)

            # Re-add the sends for any return tracks that are currently being added.
            for track_send_holder in reversed(external_track_send_holders):
                sends.insert_send(
                    return_tracks_index, track_send_holder.send, enabled_by_user=track_send_holder.enabled_by_user
                )

        # Insert the updated mixer tracks.
        for index, primary_or_return_tracks in (
            (primary_tracks_index, primary_tracks),
            (len(self.primary_tracks) + len(primary_tracks) + return_tracks_index, return_tracks),
        ):
            for track in reversed(primary_or_return_tracks):
                self._tracks_element.insert(index, track.element)

        # Overwrite the main track if provided.
        if main_track is not None:
            main_track_element = self._element.find("MainTrack")
            if main_track_element is None:
                msg = "Live set has no main track"
                raise ValueError(msg)
            index = list(self._element).index(main_track_element)
            if index < 0:
                msg = "Could not find main track element"
                raise AssertionError(msg)

            self._element[index] = main_track.element

    def _update_track_ids(self, tracks: Sequence[MixerTrack]) -> None:
        next_track_id = max([0, *(t.id for t in [*self.primary_tracks, *self.return_tracks])]) + 1
        track_id_replacements: dict[int, int] = {}

        # Update individual track IDs.
        for track in tracks:
            track_id_replacements[track.id] = next_track_id
            track.id = next_track_id
            next_track_id += 1

        for track in tracks:
            # Update group IDs.
            track_group_id = track.track_group_id
            if track_group_id >= 0:
                if track.TAG == ReturnTrack.TAG:
                    msg = f"Return track '{track.effective_name}' has a group ID"
                    raise ValueError(msg)
                if track_group_id not in track_id_replacements:
                    msg = f"Track '{track.effective_name}' is in an unrecognized group ({track_group_id})"
                    raise ValueError(msg)
                track.track_group_id = track_id_replacements[track_group_id]

            # Update routings.
            device_chain = track.device_chain
            routings: Collection[Routing] = (
                device_chain.audio_input_routing,
                device_chain.audio_output_routing,
                device_chain.midi_input_routing,
                device_chain.midi_output_routing,
            )
            for routing in routings:
                target: str = str(routing.target)

                # The target looks like e.g.  "AudioIn/Track.14/TrackOut" or "MidiIn/Externall.All/-1". If it contains a
                # string like "Track.[track_id]", replace the ID based on `track_id_replacements`.
                track_pattern = re.compile(r"(Track\.)(\d+)")

                def replace_track_id(target: str, match: re.Match) -> str:
                    prefix, track_num = match.groups()
                    track_num = int(track_num)

                    # The Main track is represented by -1, but this will
                    # be skipped by the regexp, so we don't have to worry
                    # about this case.
                    if track_num < 0:
                        msg = f"Invalid routing target: {target}"
                        raise AssertionError(msg)

                    return f"{prefix}{track_id_replacements.get(track_num, track_num)}"

                routing.target = track_pattern.sub(partial(replace_track_id, target), target)

    def _update_linked_track_group_ids(self, tracks: Sequence[Track]) -> None:
        for track in tracks:
            if int(track.linked_track_group_id) != -1:
                msg = "Linked track groups are not yet supported"
                raise NotImplementedError(msg)

    # When adding tracks from other sets, use this to update their
    # pointee IDs (i.e. mappings from controls to parameters or other
    # controllable elements) based on the next-pointee-ID value from
    # this set.
    def _update_pointee_ids(self, elements: Collection[_Element]) -> None:
        next_pointee_id: int = self._next_pointee_id
        pointee_id_replacements: dict[int, int] = {}
        id_attribute: Final[str] = "Id"

        for element in elements:
            for subelement in element.iter():
                if (
                    subelement.tag in {"AutomationTarget", "Pointee"}
                    or subelement.tag.startswith("ControllerTargets.")
                    or subelement.tag.endswith("ModulationTarget")
                ):
                    subelement_id_str: str | None = subelement.attrib.get(id_attribute, None)
                    if subelement_id_str is None:
                        msg = f"Pointee tag '{subelement.tag}' has no ID"
                        raise RuntimeError(msg)

                    next_id_str = str(next_pointee_id)
                    subelement.attrib[id_attribute] = next_id_str
                    subelement_id = int(subelement_id_str)
                    if subelement_id in pointee_id_replacements:
                        msg = f"Duplicate pointee ID on {subelement.tag}: {subelement_id}"
                        raise DuplicatePointeeIdError(msg)
                    pointee_id_replacements[subelement_id] = next_pointee_id
                    next_pointee_id += 1

        for element in elements:
            for pointee_id_element in element.findall(".//PointeeId"):
                old_id: int = int(pointee_id_element.attrib["Value"])
                if old_id not in pointee_id_replacements:
                    msg = f"Unknown mapping to pointee ID: {old_id}"
                    raise ValueError(msg)
                pointee_id_element.attrib["Value"] = str(pointee_id_replacements[old_id])

        self._next_pointee_id = next_pointee_id


def _presence(value: _U | None, msg: str = "Expected value to be non-null") -> _U:
    if value is None:
        raise ValueError(msg)
    return value
    return value
