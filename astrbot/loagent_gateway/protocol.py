"""The LoAgent gateway protocol, version 1 (see ``LOAGENT.md``).

These pydantic models mirror the Rust crate ``loagent-bots-protocol`` in the
LoAgent repository (``apps/bots/protocol``). Both sides run the same JSON
samples (``tests/fixtures/loagent_gateway``) through their models and must get
the same JSON back.

Wire rules: an absent optional field is omitted (never ``null``); lists and
booleans are always present; times are Unix milliseconds (``*_ms``); ids are
strings.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer

PROTOCOL_VERSION = 1
EVENTS_PATH = "/v1/events"
API_PREFIX = "/api/v1/loagent"
GATEWAY_MEDIA_SCHEME = "gateway://"


class _Model(BaseModel):
    """Base: unknown input fields are ignored; ``None`` fields are omitted."""

    model_config = ConfigDict(extra="ignore")

    @model_serializer(mode="wrap")
    def _omit_none(self, handler):
        # Only this model's own keys: nested free-form JSON (json / unknown /
        # other notices) keeps its nulls.
        data = handler(self)
        return {k: v for k, v in data.items() if v is not None}

    def to_json(self) -> dict:
        return self.model_dump(mode="json")


# --- accounts, conversations, senders, media ---------------------------------

ConversationKind = Literal["group", "private"]
Role = Literal["owner", "admin", "member"]


class AccountRef(_Model):
    platform: str
    instance: str
    self_id: str

    def key(self) -> str:
        return f"{self.platform}:{self.self_id}"


class Conversation(_Model):
    """``id`` is what the platform sends to (group, chat, channel; for a private
    chat the other person, or Discord's DM channel). ``thread_id``: Telegram
    forum topic, part of identity. ``guild_id``: Discord server, informational."""

    kind: ConversationKind
    id: str
    thread_id: str | None = None
    guild_id: str | None = None
    name: str | None = None

    def key(self) -> str:
        base = f"{self.kind}:{self.id}"
        return f"{base}#{self.thread_id}" if self.thread_id else base


class Sender(_Model):
    user_id: str
    nickname: str
    card: str | None = None
    role: Role | None = None
    is_self: bool


class Media(_Model):
    url: str | None = None
    mime: str | None = None
    name: str | None = None
    size: int | None = None
    sha256: str | None = None


# --- segments ----------------------------------------------------------------


class TextSegment(_Model):
    type: Literal["text"] = "text"
    text: str


class AtSegment(_Model):
    type: Literal["at"] = "at"
    user_id: str
    name: str | None = None


class AtAllSegment(_Model):
    type: Literal["at_all"] = "at_all"


class ReplySegment(_Model):
    type: Literal["reply"] = "reply"
    message_id: str
    sender_id: str | None = None
    sender_name: str | None = None
    text: str | None = None
    segments: list[Segment] = Field(default_factory=list)


class ImageSegment(_Model):
    type: Literal["image"] = "image"
    media: Media
    summary: str | None = None


class StickerSegment(_Model):
    type: Literal["sticker"] = "sticker"
    media: Media | None = None
    face_id: str | None = None
    name: str | None = None


class VoiceSegment(_Model):
    type: Literal["voice"] = "voice"
    media: Media
    duration_ms: int | None = None
    text: str | None = None


class VideoSegment(_Model):
    type: Literal["video"] = "video"
    media: Media
    cover: Media | None = None
    duration_ms: int | None = None


class FileSegment(_Model):
    type: Literal["file"] = "file"
    media: Media


class ForwardNode(_Model):
    sender_id: str
    sender_name: str
    time_ms: int | None = None
    segments: list[Segment]


class ForwardSegment(_Model):
    type: Literal["forward"] = "forward"
    id: str | None = None
    nodes: list[ForwardNode] = Field(default_factory=list)


class PokeSegment(_Model):
    type: Literal["poke"] = "poke"
    target_id: str


class ShareSegment(_Model):
    type: Literal["share"] = "share"
    url: str
    title: str
    content: str | None = None
    image: str | None = None


class LocationSegment(_Model):
    type: Literal["location"] = "location"
    lat: float
    lon: float
    title: str | None = None
    content: str | None = None


class JsonSegment(_Model):
    type: Literal["json"] = "json"
    data: Any


class UnknownSegment(_Model):
    type: Literal["unknown"] = "unknown"
    raw_type: str
    data: Any


Segment = Annotated[
    TextSegment
    | AtSegment
    | AtAllSegment
    | ReplySegment
    | ImageSegment
    | StickerSegment
    | VoiceSegment
    | VideoSegment
    | FileSegment
    | ForwardSegment
    | PokeSegment
    | ShareSegment
    | LocationSegment
    | JsonSegment
    | UnknownSegment,
    Field(discriminator="type"),
]


class Message(_Model):
    id: str
    account: AccountRef
    conversation: Conversation
    sender: Sender
    segments: list[Segment]
    reply_to: str | None = None
    at: list[str] = Field(default_factory=list)
    sent_at_ms: int | None = None
    received_at_ms: int

    def derive_fields(self) -> Message:
        """Recompute ``reply_to`` and ``at`` from the segments."""
        self.reply_to = next(
            (s.message_id for s in self.segments if isinstance(s, ReplySegment)), None
        )
        at: list[str] = []
        for s in self.segments:
            if isinstance(s, AtSegment):
                target = s.user_id
            elif isinstance(s, AtAllSegment):
                target = "all"
            else:
                continue
            if target not in at:
                at.append(target)
        self.at = at
        return self

    def dedupe_key(self) -> str:
        return f"msg:{self.account.key()}:{self.conversation.key()}:{self.id}"


# --- inbound events ----------------------------------------------------------

AccountState = Literal["online", "connecting", "offline"]
RequestKind = Literal["friend", "group_join", "group_invite"]


class MemberJoined(_Model):
    type: Literal["member_joined"] = "member_joined"
    user_id: str
    operator_id: str | None = None


class MemberLeft(_Model):
    type: Literal["member_left"] = "member_left"
    user_id: str
    operator_id: str | None = None
    kicked: bool


class Recalled(_Model):
    type: Literal["recalled"] = "recalled"
    message_id: str
    user_id: str | None = None
    operator_id: str | None = None


class PokeNotice(_Model):
    type: Literal["poke"] = "poke"
    user_id: str
    target_id: str


class FriendAdded(_Model):
    type: Literal["friend_added"] = "friend_added"
    user_id: str


class RequestNotice(_Model):
    type: Literal["request"] = "request"
    request: RequestKind
    user_id: str
    comment: str
    flag: str


class OtherNotice(_Model):
    type: Literal["other"] = "other"
    adapter: str
    raw: Any


Notice = Annotated[
    MemberJoined
    | MemberLeft
    | Recalled
    | PokeNotice
    | FriendAdded
    | RequestNotice
    | OtherNotice,
    Field(discriminator="type"),
]


class AccountStatus(_Model):
    account: AccountRef
    state: AccountState
    reason: str | None = None
    detail: str | None = None
    nickname: str | None = None
    since_ms: int
    last_seen_ms: int | None = None


class _EventBase(_Model):
    v: int = PROTOCOL_VERSION
    id: str
    dedupe_key: str
    time_ms: int


class MessageEvent(_EventBase):
    kind: Literal["message"] = "message"
    message: Message


class NoticeEvent(_EventBase):
    kind: Literal["notice"] = "notice"
    account: AccountRef
    conversation: Conversation | None = None
    notice: Notice


class AccountEvent(_EventBase):
    kind: Literal["account"] = "account"
    status: AccountStatus


Event = Annotated[
    MessageEvent | NoticeEvent | AccountEvent, Field(discriminator="kind")
]


class EventBatch(_Model):
    events: list[Event]


# --- outbound ----------------------------------------------------------------


class SendRequest(_Model):
    v: int
    request_id: str
    account: AccountRef
    conversation: Conversation
    segments: list[Segment]


class Degradation(_Model):
    index: int
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    reason: str

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    def to_json(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


class SendResult(_Model):
    request_id: str
    message_ids: list[str] = Field(default_factory=list)
    degraded: list[Degradation] = Field(default_factory=list)
    duplicate: bool = False

    def to_json(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


ErrorCode = Literal[
    "unauthorized",
    "invalid_request",
    "unsupported_version",
    "account_not_found",
    "account_offline",
    "unsupported_segment",
    "media_unavailable",
    "unsupported",
    "platform_error",
    "not_configured",
]

HTTP_STATUS: dict[str, int] = {
    "unauthorized": 401,
    "invalid_request": 400,
    "unsupported_version": 400,
    "account_not_found": 404,
    "account_offline": 503,
    "unsupported_segment": 422,
    "media_unavailable": 422,
    "unsupported": 501,
    "platform_error": 502,
    "not_configured": 503,
}


class ErrorDetail(_Model):
    code: ErrorCode
    message: str
    retryable: bool


class ErrorResponse(_Model):
    error: ErrorDetail


# --- queries -----------------------------------------------------------------


class OutboxStatus(_Model):
    pending: int
    last_delivered_ms: int | None = None
    last_error: str | None = None


class Health(_Model):
    v: int
    astrbot_version: str
    enabled: bool
    outbox: OutboxStatus


class AccountsResponse(_Model):
    accounts: list[AccountStatus]


class ConversationInfo(_Model):
    kind: ConversationKind
    id: str
    name: str | None = None
    member_count: int | None = None


class ConversationsResponse(_Model):
    conversations: list[ConversationInfo]


class Member(_Model):
    user_id: str
    nickname: str
    card: str | None = None
    role: Role | None = None
    joined_at_ms: int | None = None
    last_sent_ms: int | None = None


class MembersResponse(_Model):
    members: list[Member]


class ProfileResponse(_Model):
    profile: Member


class HistoryResponse(_Model):
    messages: list[Message]


class MediaUploadResponse(_Model):
    media: Media


for _model in (ReplySegment, ForwardNode, ForwardSegment):
    _model.model_rebuild()
