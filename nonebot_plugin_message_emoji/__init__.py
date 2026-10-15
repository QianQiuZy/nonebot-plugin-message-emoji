from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final, NoReturn

import anyio
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    ActionFailed,
    ApiNotAvailable,
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    NetworkError,
)
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="消息表情回应",
    description="通过引用消息，为其添加 QQ 表情回应。",
    usage="引用消息后发送 /贴 表情ID1 表情ID2，单次最多 5 个表情。",
)

MAX_EMOJI_COUNT: Final = 5
EMOJI_INTERVAL: Final = 0.4
SESSION_TIMEOUT: Final = 10.0
USAGE: Final = "用法：引用消息后发送 /贴 表情ID1 表情ID2（单次最多 5 个表情）"
INVALID_EMOJI_ID: Final = "表情参数无效，请填写 NapCat 支持的 emoji_id，或直接发送 QQ 表情。"
SESSION_USAGE: Final = "单表情会话仅支持群聊，请在群内引用消息后发送 /贴。"

paste_emoji = on_command("贴", force_whitespace=True)
followup_emoji = on_message(priority=0, block=False)


@dataclass(frozen=True, slots=True)
class EmojiSession:
    """记录一个群成员正在操作的目标消息与会话状态。"""

    message_id: int
    expires_at: float
    emoji_count: int


@dataclass(frozen=True, slots=True)
class ReactionResult:
    """记录一批表情回应的成功与失败 ID。"""

    succeeded: tuple[str, ...]
    failed: tuple[str, ...]


_sessions: Final[dict[tuple[int, int], EmojiSession]] = {}
_sessions_lock: Final = anyio.Lock()


async def _finish(bot: Bot, event: MessageEvent, message: str) -> NoReturn:
    """向当前会话发送提示并结束本次匹配。"""
    await bot.send(event, message)
    raise FinishedException


def _reply_message_id(event: MessageEvent) -> int | None:
    """从消息事件中读取被引用消息的 ID。"""
    if event.reply is not None:
        return event.reply.message_id

    for segment in event.original_message:
        if segment.type != "reply":
            continue

        raw_message_id = segment.data.get("id")
        if not isinstance(raw_message_id, str):
            return None
        try:
            return int(raw_message_id)
        except ValueError:
            return None

    return None


def _emoji_ids(arguments: Message) -> tuple[str, ...] | None:
    """从命令参数中提取表情 ID，也支持 QQ face 消息段。"""
    ids: list[str] = []
    for segment in arguments:
        if segment.is_text():
            text = segment.data.get("text")
            if not isinstance(text, str):
                return None
            ids.extend(text.split())
            continue

        if segment.type != "face":
            return None
        face_id = segment.data.get("id")
        if not isinstance(face_id, str):
            return None
        ids.append(face_id)

    return tuple(ids)


async def _start_session(event: GroupMessageEvent, message_id: int) -> None:
    """为群成员记录一个十秒无操作过期的表情回应会话。"""
    key = (event.group_id, event.user_id)
    async with _sessions_lock:
        _sessions[key] = EmojiSession(
            message_id=message_id,
            expires_at=time.monotonic() + SESSION_TIMEOUT,
            emoji_count=0,
        )


async def _consume_session(event: GroupMessageEvent) -> int | None:
    """读取并推进群成员会话，过期或达到上限时将其删除。"""
    key = (event.group_id, event.user_id)
    now = time.monotonic()
    async with _sessions_lock:
        session = _sessions.get(key)
        if session is None:
            return None
        if session.expires_at <= now:
            del _sessions[key]
            return None

        emoji_count = session.emoji_count + 1
        if emoji_count >= MAX_EMOJI_COUNT:
            del _sessions[key]
        else:
            _sessions[key] = EmojiSession(
                message_id=session.message_id,
                expires_at=now + SESSION_TIMEOUT,
                emoji_count=emoji_count,
            )
        return session.message_id


def _single_emoji_id(event: GroupMessageEvent) -> str | None:
    """只接受内容为单个 QQ face 消息段的群消息。"""
    if len(event.original_message) != 1:
        return None

    segment = event.original_message[0]
    if segment.type != "face":
        return None
    emoji_id = segment.data.get("id")
    if isinstance(emoji_id, str):
        return emoji_id
    if isinstance(emoji_id, int):
        return str(emoji_id)
    return None


async def _apply_emoji_ids(
    bot: Bot,
    message_id: int,
    emoji_ids: tuple[str, ...],
) -> ReactionResult:
    """按顺序回应表情，并在同一批次的请求之间等待 0.4 秒。"""
    succeeded: list[str] = []
    failed: list[str] = []
    for index, emoji_id in enumerate(emoji_ids):
        try:
            await bot.call_api(
                "set_msg_emoji_like",
                message_id=message_id,
                emoji_id=emoji_id,
                set=True,
            )
        except (ActionFailed, ApiNotAvailable, NetworkError):
            failed.append(emoji_id)
        else:
            succeeded.append(emoji_id)

        if index + 1 < len(emoji_ids):
            await anyio.sleep(EMOJI_INTERVAL)

    return ReactionResult(tuple(succeeded), tuple(failed))


@paste_emoji.handle()
async def handle_paste_emoji(
    bot: Bot,
    event: MessageEvent,
    arguments: Message = CommandArg(),
) -> None:
    """为被引用的消息逐个添加表情回应。"""
    message_id = _reply_message_id(event)
    if message_id is None:
        await _finish(bot, event, "请先引用一条消息，再发送 /贴 表情 ID。")

    emoji_ids = _emoji_ids(arguments)
    if emoji_ids is None:
        await _finish(bot, event, INVALID_EMOJI_ID)
    if not emoji_ids:
        if not isinstance(event, GroupMessageEvent):
            await _finish(bot, event, SESSION_USAGE)
        await _start_session(event, message_id)
        return
    if len(emoji_ids) > MAX_EMOJI_COUNT:
        await _finish(bot, event, "一次最多贴 5 个表情，请减少表情数量后重试。")
    result = await _apply_emoji_ids(bot, message_id, emoji_ids)
    if not result.failed:
        return
    if result.succeeded:
        await _finish(
            bot,
            event,
            f"已成功贴 {len(result.succeeded)} 个表情；失败 {len(result.failed)} 个：{', '.join(result.failed)}。",
        )
    await _finish(
        bot,
        event,
        "表情回应失败，请确认 NapCat 已启用 set_msg_emoji_like 且表情 ID 有效。",
    )


@followup_emoji.handle()
async def handle_followup_emoji(bot: Bot, event: GroupMessageEvent) -> None:
    """处理会话期间同一群成员单独发送的 QQ 表情。"""
    emoji_id = _single_emoji_id(event)
    if emoji_id is None:
        return

    message_id = await _consume_session(event)
    if message_id is None:
        return

    result = await _apply_emoji_ids(bot, message_id, (emoji_id,))
    if result.failed:
        await bot.send(
            event,
            f"表情 {emoji_id} 贴失败，请确认 NapCat 已启用 set_msg_emoji_like 且表情 ID 有效。",
        )
