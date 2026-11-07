"""Protocol segments → what a platform sends.

OneBot v11 instances (QQ, WeChat) get OneBot message arrays built here and are
called with ``self_id`` every time, so one instance can carry several accounts.
Other adapters get an AstrBot message chain and their own ``send_by_session``.

Segments a platform cannot send are degraded (turned into text) or dropped,
and every such case is reported back in ``degraded``.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.core.message import components as C

from . import protocol as P
from .media import MediaStore, is_remote


class OutboundError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


# What each network's protocol side can send, beyond text/at/at_all/reply.
# WeChat's gateway (wechat-selkies wechat-api) sends text, @ and quotes only.
_ONEBOT_RICH = {
    "image",
    "sticker",
    "voice",
    "video",
    "file",
    "forward",
    "poke",
    "json",
}
CAPABILITIES: dict[str, set[str]] = {
    "qq": _ONEBOT_RICH,
    "onebot": _ONEBOT_RICH,
    "wechat": set(),
}
# Segments that must go out as a message of their own on QQ.
_STANDALONE = {"file", "voice", "video", "forward", "poke"}


@dataclass
class Plan:
    """What to send: OneBot batches (or one AstrBot chain), in order."""

    batches: list[tuple[str, Any]] = field(default_factory=list)
    degraded: list[P.Degradation] = field(default_factory=list)


def _degrade(plan: Plan, index: int, seg: P.Segment, to: str, reason: str) -> None:
    plan.degraded.append(
        P.Degradation(index=index, from_=seg.type, to=to, reason=reason)
    )


def _as_text(seg: P.Segment) -> str | None:
    """Text stand-in for a segment the platform cannot send, or ``None`` to drop."""
    if isinstance(seg, P.ShareSegment):
        return f"{seg.title}\n{seg.url}"
    if isinstance(seg, P.LocationSegment):
        return f"[位置] {seg.title or ''} ({seg.lat}, {seg.lon})".replace("  ", " ")
    if isinstance(seg, P.ForwardSegment) and seg.nodes:
        lines = []
        for node in seg.nodes:
            text = "".join(
                s.text for s in node.segments if isinstance(s, P.TextSegment)
            )
            lines.append(f"{node.sender_name}: {text}")
        return "\n".join(lines)
    if isinstance(seg, P.StickerSegment) and seg.name:
        return seg.name
    return None


def media_ref(media: P.Media | None, store: MediaStore) -> str:
    """A ``file`` value the protocol side can read: remote URLs as they are,
    anything local as ``base64://`` (the protocol side runs in another
    container and cannot see AstrBot's files)."""
    if media is None or not media.url:
        raise OutboundError("media_unavailable", "media without url")
    if is_remote(media.url):
        return media.url
    got = store.read_ref(media.url)
    if got is None:
        raise OutboundError("media_unavailable", f"cannot read media {media.url[:80]}")
    return "base64://" + base64.b64encode(got[0]).decode()


def _onebot_segment(seg: P.Segment, store: MediaStore) -> dict:
    if isinstance(seg, P.TextSegment):
        return {"type": "text", "data": {"text": seg.text}}
    if isinstance(seg, P.AtSegment):
        return {"type": "at", "data": {"qq": seg.user_id}}
    if isinstance(seg, P.AtAllSegment):
        return {"type": "at", "data": {"qq": "all"}}
    if isinstance(seg, P.ReplySegment):
        return {"type": "reply", "data": {"id": seg.message_id}}
    if isinstance(seg, P.ImageSegment):
        data = {"file": media_ref(seg.media, store)}
        if seg.summary:
            data["summary"] = seg.summary
        return {"type": "image", "data": data}
    if isinstance(seg, P.StickerSegment):
        if seg.face_id:
            return {"type": "face", "data": {"id": seg.face_id}}
        return {
            "type": "image",
            "data": {"file": media_ref(seg.media, store), "sub_type": 1},
        }
    if isinstance(seg, P.VoiceSegment):
        return {"type": "record", "data": {"file": media_ref(seg.media, store)}}
    if isinstance(seg, P.VideoSegment):
        return {"type": "video", "data": {"file": media_ref(seg.media, store)}}
    if isinstance(seg, P.FileSegment):
        data = {"file": media_ref(seg.media, store)}
        if seg.media.name:
            data["name"] = seg.media.name
        return {"type": "file", "data": data}
    if isinstance(seg, P.JsonSegment):
        payload = (
            seg.data
            if isinstance(seg.data, str)
            else json.dumps(seg.data, ensure_ascii=False)
        )
        return {"type": "json", "data": {"data": payload}}
    raise OutboundError("unsupported_segment", f"no OneBot form for {seg.type}")


def _forward_nodes(seg: P.ForwardSegment, store: MediaStore) -> list[dict]:
    nodes = []
    for node in seg.nodes:
        content = [
            _onebot_segment(s, store)
            for s in node.segments
            if not isinstance(s, (P.ForwardSegment, P.PokeSegment))
        ]
        nodes.append(
            {
                "type": "node",
                "data": {
                    "user_id": node.sender_id,
                    "nickname": node.sender_name,
                    "content": content,
                },
            }
        )
    return nodes


def plan_onebot(platform: str, segments: list[P.Segment], store: MediaStore) -> Plan:
    """Split and convert segments for a OneBot v11 protocol side.

    Batches are ``("msg", [segments])``, ``("forward", [nodes])`` or
    ``("poke", user_id)``. A ``reply`` is moved to the front of the first
    message.
    """
    caps = CAPABILITIES.get(platform, _ONEBOT_RICH)
    plan = Plan()
    reply: dict | None = None
    current: list[dict] = []

    def flush() -> None:
        nonlocal current
        if current:
            plan.batches.append(("msg", current))
            current = []

    for index, seg in enumerate(segments):
        kind = seg.type
        if kind == "reply":
            if reply is None:
                reply = _onebot_segment(seg, store)
            continue
        if kind == "unknown":
            _degrade(plan, index, seg, "dropped", "unknown segments are not sent")
            continue
        basic = kind in ("text", "at", "at_all")
        if not basic and kind not in caps:
            text = _as_text(seg)
            if text is not None:
                current.append({"type": "text", "data": {"text": text}})
                _degrade(
                    plan, index, seg, "text", f"{platform} 不能发 {kind}，改成文字"
                )
            else:
                _degrade(plan, index, seg, "dropped", f"{platform} 不能发 {kind}")
            continue
        if kind == "forward":
            if not seg.nodes:
                _degrade(
                    plan, index, seg, "dropped", "forward without nodes cannot be sent"
                )
                continue
            flush()
            plan.batches.append(("forward", _forward_nodes(seg, store)))
            continue
        if kind == "poke":
            flush()
            plan.batches.append(("poke", seg.target_id))
            continue
        if kind == "sticker" and not seg.face_id and seg.media is None:
            _degrade(plan, index, seg, "dropped", "sticker without face or media")
            continue
        converted = _onebot_segment(seg, store)
        if kind in _STANDALONE:
            flush()
            plan.batches.append(("msg", [converted]))
        else:
            current.append(converted)
    flush()

    if reply is not None:
        first = next((b for b in plan.batches if b[0] == "msg"), None)
        if first is not None:
            first[1].insert(0, reply)
    return plan


def chain_from_segments(
    segments: list[P.Segment], store: MediaStore
) -> tuple[list[C.BaseMessageComponent], list[P.Degradation]]:
    """An AstrBot message chain for adapters other than OneBot."""
    chain: list[C.BaseMessageComponent] = []
    degraded: list[P.Degradation] = []
    for index, seg in enumerate(segments):
        if isinstance(seg, P.TextSegment):
            chain.append(C.Plain(seg.text))
        elif isinstance(seg, P.AtSegment):
            chain.append(C.At(qq=seg.user_id, name=seg.name or ""))
        elif isinstance(seg, P.AtAllSegment):
            chain.append(C.AtAll())
        elif isinstance(seg, P.ReplySegment):
            chain.insert(0, C.Reply(id=seg.message_id))
        elif isinstance(seg, P.ImageSegment):
            chain.append(C.Image(file=media_ref(seg.media, store)))
        elif isinstance(seg, P.StickerSegment) and seg.face_id:
            chain.append(
                C.Face(id=int(seg.face_id))
                if seg.face_id.isdigit()
                else C.Plain(seg.name or "")
            )
        elif isinstance(seg, P.StickerSegment) and seg.media is not None:
            chain.append(C.Image(file=media_ref(seg.media, store)))
        elif isinstance(seg, P.VoiceSegment):
            chain.append(C.Record(file=media_ref(seg.media, store)))
        elif isinstance(seg, P.VideoSegment):
            chain.append(C.Video(file=media_ref(seg.media, store)))
        elif isinstance(seg, P.FileSegment):
            ref = media_ref(seg.media, store)
            name = seg.media.name or "file"
            chain.append(
                C.File(name=name, url=ref)
                if is_remote(ref)
                else C.File(name=name, file=ref)
            )
        else:
            text = _as_text(seg)
            if text is not None:
                chain.append(C.Plain(text))
                degraded.append(
                    P.Degradation(
                        index=index, from_=seg.type, to="text", reason="sent as text"
                    )
                )
            else:
                degraded.append(
                    P.Degradation(
                        index=index,
                        from_=seg.type,
                        to="dropped",
                        reason="not supported here",
                    )
                )
    return chain, degraded
