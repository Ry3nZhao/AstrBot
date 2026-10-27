import asyncio
from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
)


@pytest.mark.asyncio
async def test_attachment_part_uses_display_filename_with_stored_filename(tmp_path):
    """Attachment parts should show the display name while keeping the stored name."""
    stored_file = tmp_path / "uuid.txt"
    stored_file.write_text("payload", encoding="utf-8")

    async def insert_attachment(path, type, mime_type):
        return SimpleNamespace(
            attachment_id="attachment-1",
            path=path,
            type=type,
            mime_type=mime_type,
        )

    part = await create_attachment_part_from_existing_file(
        stored_file.name,
        attach_type="file",
        insert_attachment=insert_attachment,
        attachments_dir=tmp_path,
        display_name="../nested/report.txt",
    )

    assert part == {
        "type": "file",
        "attachment_id": "attachment-1",
        "filename": "report.txt",
        "stored_filename": "uuid.txt",
    }


@pytest.mark.asyncio
async def test_build_webchat_message_parts_preserves_payload_filename(tmp_path):
    """Attachment lookup should not overwrite the payload filename with disk name."""
    stored_file = tmp_path / "uuid.txt"
    stored_file.write_text("payload", encoding="utf-8")
    attachment = SimpleNamespace(
        attachment_id="attachment-1",
        path=str(stored_file),
        type="file",
    )

    async def get_attachment_by_id(attachment_id):
        assert attachment_id == "attachment-1"
        return attachment

    parts = await build_webchat_message_parts(
        [
            {
                "type": "file",
                "attachment_id": "attachment-1",
                "filename": r"C:\fakepath\report.txt",
            }
        ],
        get_attachment_by_id=get_attachment_by_id,
        strict=True,
    )

    assert parts == [
        {
            "type": "file",
            "attachment_id": "attachment-1",
            "filename": "report.txt",
            "path": str(stored_file),
            "stored_filename": "uuid.txt",
        }
    ]
