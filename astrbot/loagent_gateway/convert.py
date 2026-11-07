"""AstrBot events and message components → protocol events and segments.

Everything AstrBot's adapters put on the event queue comes through here:
messages become ``message`` events whether or not they mention the bot (wake
rules live in the backend now), OneBot notices and requests become ``notice``
events. ``bot_offline`` is not a notice: it is reported to the account tracker.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from astrbot.core.message import components as C
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType

from . import protocol as P
from .media import MediaStore

ONEBOT = "aiocqhttp"


def new_event_id() -> str:
    return uuid.uuid4().hex


def platform_kind(adapter: str, instance_config: Mapping | None) -> str:
    """The network an instance talks to. OneBot v11 carries QQ (NapCat) and
    WeChat (the wechat-selkies gateway) alike, so the instance says which in
    ``loagent_platform``; otherwise OneBot is ``onebot`` and the rest are
    named after their adapter."""
    explicit = str((instance_config or {}).get("loagent_platform") or "").strip()
    if explicit:
        return explicit
    return "onebot" if adapter == ONEBOT else adapter


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text and text != "0" else None


def raw_onebot(event: AstrMessageEvent) -> Mapping | None:
    """The OneBot v11 payload behind an aiocqhttp event, if any."""
    raw = getattr(event.message_obj, "raw_message", None)
    return raw if isinstance(raw, Mapping) and "post_type" in raw else None


# --- components → segments -----------------------------------------------------


def segment_from_component(
    comp: C.BaseMessageComponent, media: MediaStore, *, nested: bool = False
) -> P.Segment | None:
    """One AstrBot component as a protocol segment; ``None`` to leave it out."""
    if isinstance(comp, C.Plain):
        return P.TextSegment(text=comp.text) if comp.text else None
    if isinstance(comp, C.At):  # AtAll is an At
        if str(comp.qq) == "all":
            return P.AtAllSegment()
        return P.AtSegment(user_id=str(comp.qq), name=comp.name or None)
    if isinstance(comp, C.Reply):
        inner: list[P.Segment] = []
        if not nested:
            for c in comp.chain or []:
                seg = segment_from_component(c, media, nested=True)
                if seg is not None and not isinstance(seg, P.ReplySegment):
                    inner.append(seg)
        return P.ReplySegment(
            message_id=str(comp.id),
            sender_id=_str_or_none(comp.sender_id),
            sender_name=comp.sender_nickname or None,
            text=comp.message_str or comp.text or None,
            segments=inner,
        )
    if isinstance(comp, C.Image):
        return P.ImageSegment(media=media.ingest([comp.url, comp.file, comp.path]))
    if isinstance(comp, C.Face):
        return P.StickerSegment(face_id=str(comp.id))
    if isinstance(comp, C.Record):
        return P.VoiceSegment(
            media=media.ingest([comp.url, comp.file, comp.path]),
            text=comp.text or None,
        )
    if isinstance(comp, C.Video):
        cover = media.ingest([comp.cover]) if comp.cover else None
        return P.VideoSegment(
            media=media.ingest([comp.url, comp.file, comp.path]),
            cover=cover if cover and cover.url else None,
        )
    if isinstance(comp, C.File):
        return P.FileSegment(
            media=media.ingest([comp.url, comp.file_], name=comp.name or None)
        )
    if isinstance(comp, C.Forward):
        return P.ForwardSegment(id=str(comp.id))
    if isinstance(comp, C.Nodes):
        return P.ForwardSegment(nodes=[_node(n, media) for n in comp.nodes])
    if isinstance(comp, C.Node):
        return P.ForwardSegment(nodes=[_node(comp, media)])
    if isinstance(comp, C.Poke):
        target = _str_or_none(comp.id) or _str_or_none(comp.qq) or ""
        return P.PokeSegment(target_id=target)
    if isinstance(comp, C.Share):
        return P.ShareSegment(
            url=comp.url,
            title=comp.title,
            content=comp.content or None,
            image=comp.image or None,
        )
    if isinstance(comp, C.Location):
        return P.LocationSegment(
            lat=comp.lat,
            lon=comp.lon,
            title=comp.title or None,
            content=comp.content or None,
        )
    if isinstance(comp, C.Json):
        return P.JsonSegment(data=_json_safe(comp.data))
    if isinstance(comp, C.Unknown):
        return P.UnknownSegment(raw_type="unknown", data={"text": comp.text})
    try:
        data = comp.toDict().get("data", {})
    except Exception:
        data = {}
    return P.UnknownSegment(
        raw_type=str(comp.type.value).lower(), data=_json_safe(data)
    )


def _node(node: C.Node, media: MediaStore) -> P.ForwardNode:
    segs = [segment_from_component(c, media) for c in node.content or []]
    return P.ForwardNode(
        sender_id=str(node.uin or ""),
        sender_name=node.name or "",
        time_ms=int(node.time) * 1000 if node.time else None,
        segments=[s for s in segs if s is not None],
    )


def segments_from_chain(
    chain: list[C.BaseMessageComponent], media: MediaStore
) -> list[P.Segment]:
    out = []
    for comp in chain or []:
        seg = segment_from_component(comp, media)
        if seg is not None:
            out.append(seg)
    return out


# --- events --------------------------------------------------------------------


def conversation_of(event: AstrMessageEvent) -> P.Conversation:
    obj = event.message_obj
    group_id = obj.group_id if hasattr(obj, "group_id") else ""
    if obj.type == MessageType.GROUP_MESSAGE and group_id:
        name = obj.group.group_name if obj.group else None
        return P.Conversation(kind="group", id=str(group_id), name=name or None)
    sender = getattr(obj, "sender", None)
    peer = str(getattr(sender, "user_id", "") or obj.session_id or "")
    return P.Conversation(kind="private", id=peer)


def sender_of(event: AstrMessageEvent, self_id: str) -> P.Sender:
    obj = event.message_obj
    raw = raw_onebot(event)
    raw_sender = raw.get("sender") if raw else None
    user_id = str(getattr(obj.sender, "user_id", "") or "")
    if isinstance(raw_sender, Mapping):
        nickname = str(raw_sender.get("nickname") or "")
        card = str(raw_sender.get("card") or "") or None
        role = raw_sender.get("role")
        role = role if role in ("owner", "admin", "member") else None
    else:
        nickname, card, role = str(obj.sender.nickname or ""), None, None
    return P.Sender(
        user_id=user_id,
        nickname=nickname,
        card=card,
        role=role,
        is_self=bool(user_id) and user_id == self_id,
    )


def message_from_event(
    event: AstrMessageEvent,
    account: P.AccountRef,
    media: MediaStore,
    received_ms: int,
) -> P.Message:
    obj = event.message_obj
    raw = raw_onebot(event)
    if raw and raw.get("time"):
        sent_ms = int(raw["time"]) * 1000
    elif getattr(obj, "timestamp", None):
        sent_ms = int(obj.timestamp) * 1000
    else:
        sent_ms = None
    segments = segments_from_chain(obj.message, media)
    message_id = str(getattr(obj, "message_id", "") or "")
    conversation = conversation_of(event)
    sender = sender_of(event, account.self_id)
    if not message_id:
        basis = json.dumps(
            [conversation.id, sender.user_id, sent_ms, event.message_str],
            ensure_ascii=False,
        )
        message_id = "h" + hashlib.sha1(basis.encode()).hexdigest()[:20]
    return P.Message(
        id=message_id,
        account=account,
        conversation=conversation,
        sender=sender,
        segments=segments,
        sent_at_ms=sent_ms,
        received_at_ms=received_ms,
    ).derive_fields()


def message_event(message: P.Message, now_ms: int) -> P.MessageEvent:
    return P.MessageEvent(
        id=new_event_id(),
        dedupe_key=message.dedupe_key(),
        time_ms=now_ms,
        message=message,
    )


def onebot_notice(
    raw: Mapping, account: P.AccountRef
) -> tuple[P.Conversation | None, P.Notice, str] | None:
    """A OneBot v11 notice or request as ``(conversation, notice, dedupe key)``.

    ``None`` for ``bot_offline`` (an account state, not a notice).
    """
    post_type = raw.get("post_type")
    kind = str(raw.get("notice_type") or raw.get("request_type") or "")
    sub = str(raw.get("sub_type") or "")
    group = _str_or_none(raw.get("group_id"))
    user = str(raw.get("user_id") or "")
    operator = _str_or_none(raw.get("operator_id"))
    when = str(raw.get("time") or "")
    prefix = f"notice:{account.key()}"
    conv = P.Conversation(kind="group", id=group) if group else None

    if post_type == "notice":
        if kind == "bot_offline":
            return None
        if kind == "group_increase":
            return (
                conv,
                P.MemberJoined(user_id=user, operator_id=operator),
                (f"{prefix}:member_joined:{group}:{user}:{when}"),
            )
        if kind == "group_decrease":
            notice = P.MemberLeft(
                user_id=user, operator_id=operator, kicked=sub in ("kick", "kick_me")
            )
            return conv, notice, f"{prefix}:member_left:{group}:{user}:{when}"
        if kind in ("group_recall", "friend_recall"):
            message_id = str(raw.get("message_id") or "")
            if conv is None:
                conv = P.Conversation(kind="private", id=user)
            return (
                conv,
                P.Recalled(
                    message_id=message_id, user_id=user or None, operator_id=operator
                ),
                f"{prefix}:recalled:{message_id}",
            )
        if kind == "notify" and sub == "poke":
            target = str(raw.get("target_id") or "")
            if conv is None:
                conv = P.Conversation(kind="private", id=user)
            return (
                conv,
                P.PokeNotice(user_id=user, target_id=target),
                (f"{prefix}:poke:{conv.id}:{user}:{target}:{when}"),
            )
        if kind == "friend_add":
            return (
                P.Conversation(kind="private", id=user),
                P.FriendAdded(user_id=user),
                (f"{prefix}:friend_added:{user}:{when}"),
            )
    elif post_type == "request":
        request = None
        if kind == "friend":
            request = "friend"
        elif kind == "group":
            request = "group_invite" if sub == "invite" else "group_join"
        if request is not None:
            flag = str(raw.get("flag") or "")
            notice = P.RequestNotice(
                request=request,
                user_id=user,
                comment=str(raw.get("comment") or ""),
                flag=flag,
            )
            return conv, notice, f"{prefix}:request:{request}:{flag}"

    payload = _json_safe(dict(raw))
    digest = hashlib.md5(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return conv, P.OtherNotice(adapter=ONEBOT, raw=payload), f"{prefix}:other:{digest}"


def notice_event(
    account: P.AccountRef,
    conversation: P.Conversation | None,
    notice: P.Notice,
    dedupe_key: str,
    now_ms: int,
) -> P.NoticeEvent:
    return P.NoticeEvent(
        id=new_event_id(),
        dedupe_key=dedupe_key,
        time_ms=now_ms,
        account=account,
        conversation=conversation,
        notice=notice,
    )


def account_event(status: P.AccountStatus, now_ms: int) -> P.AccountEvent:
    return P.AccountEvent(
        id=new_event_id(),
        dedupe_key=f"account:{status.account.key()}:{status.state}:{status.since_ms}",
        time_ms=now_ms,
        status=status,
    )
