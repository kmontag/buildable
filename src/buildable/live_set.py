from __future__ import annotations

import copy
import json
import re
from functools import cached_property, partial
from typing import TYPE_CHECKING, Collection, TypeVar

from lxml.etree import fromstring

from .base import AbletonDocumentObject, ElementObject, child_element_object_property, xml_property
from .util import override

if TYPE_CHECKING:
    from typing import BinaryIO, Final, Self, Sequence

    from lxml.etree import _Element


_U = TypeVar("_U")


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

    @xml_property(attrib="Value", property_type=int)
    def _next_pointee_id(self) -> _Element:
        return _presence(self._element.find("NextPointeeId"))

    @cached_property
    def sends_pre(self) -> SendsPre:
        return SendsPre(_presence(self._element.find(SendsPre.TAG)))

    @cached_property
    def _tracks_element(self) -> _Element:
        return _presence(self._element.find("Tracks"))

    def delete_primary_track(self, index: int) -> None:
        element_to_delete = self.primary_tracks[index].element
        self._tracks_element.remove(element_to_delete)

    def delete_return_track(self, index: int) -> None:
        element_to_delete = self.return_tracks[index].element
        self._tracks_element.remove(element_to_delete)

    def insert_primary_tracks(self, primary_tracks: Sequence[PrimaryTrack], index: int = 0) -> None:
        self.insert_tracks(primary_tracks=primary_tracks, primary_tracks_index=index)

    def insert_return_tracks(self, return_tracks: Sequence[ReturnTrack], index: int = 0) -> None:
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
                    pointee_id_replacements[int(subelement_id_str)] = next_pointee_id
                    next_pointee_id += 1

        for element in elements:
            for pointee_id_element in element.findall(".//PointeeId"):
                old_id: int = int(pointee_id_element.attrib["Value"])
                if old_id not in pointee_id_replacements:
                    msg = f"Unknown mapping to pointee ID: {old_id}"
                    raise ValueError(msg)
                pointee_id_element.attrib["Value"] = str(pointee_id_replacements[old_id])

        self._next_pointee_id = next_pointee_id


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
        #   <SendPreBool Id="0" value="true">
        #   <SendPreBool Id="1" value="false">
        #   <SendPreBool Id="2" value="true">
        #   <!-- ... -->
        # </SendsPre>

        # Insert the new child element at the appropriate index.
        new_element = fromstring(xml_str)
        self.element.insert(index, new_element)

        # Update the ID attributes of elements that come after the inserted element.
        send_pre_bools = self.send_pre_bools
        for i in range(index + 1, len(send_pre_bools)):
            if send_pre_bools[index].id != i - 1:
                msg = f"Unexpected SendPreBool ID at position {i}: {send_pre_bools[index].id}"
                raise AssertionError(msg)
            send_pre_bools[index].id = i


class SendPreBool(ElementObject):
    TAG = "SendPreBool"

    @xml_property(attrib="Id", property_type=int)
    def id(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=bool)
    def value(self) -> _Element:
        return self.element


class Routing(ElementObject):
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


class MidiControllerRange(ElementObject):
    TAG = "MidiControllerRange"

    @xml_property(attrib="Value", property_type=float)
    def min(self) -> _Element:
        return _presence(self.element.find("Min"))

    @xml_property(attrib="Value", property_type=float)
    def max(self) -> _Element:
        return _presence(self.element.find("Max"))


class Send(ElementObject):
    TAG = "Send"

    # Live saves "zero-valued" sends with this slightly-nonzero value - we use this when creating new sends to match the
    # default behavior, but it's also fine to set e.g. `send.value = 0`.
    _MIN_VALUE_STR: Final[str] = "0.0003162277571"

    @child_element_object_property(property_type=MidiControllerRange)
    def midi_controller_range(self) -> _Element:
        return self.element

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

        return cls(fromstring(xml_str))

    @xml_property(attrib="Value", property_type=float)
    def value(self) -> _Element:
        return _presence(self.element.find("Manual"))


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
    TAG = "Sends"

    @property
    def track_send_holders(self) -> Sequence[TrackSendHolder]:
        # This should be the only child element type.
        return [TrackSendHolder(child) for child in self.element]

    def insert_send(self, index: int, send: Send, *, enabled_by_user: bool = False) -> None:
        track_send_holder_element = fromstring(
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

    def delete_send(self, index) -> None:
        if self.element[index].tag != TrackSendHolder.TAG:
            msg = f"Unexpected child element: {self.element[index].tag}"
            raise AssertionError(msg)
        del self.element[index]

        # Update IDs of remaining track send holders.
        for i, existing_track_send_holder in enumerate(self.track_send_holders):
            existing_track_send_holder.id = i


class Mixer(ElementObject):
    TAG = "Mixer"

    @child_element_object_property(property_type=Sends)
    def sends(self) -> _Element:
        return self.element

    @xml_property(attrib="Value", property_type=int)
    def view_state_session_track_width(self) -> _Element:
        # [sic]
        return _presence(self.element.find("ViewStateSesstionTrackWidth"))


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


def _presence(value: _U | None, msg: str = "Expected value to be non-null") -> _U:
    if value is None:
        raise ValueError(msg)
    return value
