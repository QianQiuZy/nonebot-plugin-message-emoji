# nonebot-plugin-message-emoji

一个适用于 QQ NapCat 的 NoneBot2 插件：引用一条消息后，让 Bot 为它添加多个 QQ 表情回应。

## 可行性

可行。NapCat 已实现 OneBot 11 扩展接口 `set_msg_emoji_like`，请求格式为：

```json
{
  "message_id": 12345,
  "emoji_id": "128",
  "set": true
}
```

`message_id` 和 `emoji_id` 必填，`set` 可选且默认为 `true`。它不是 OneBot 11 标准公开 API，因此需要使用 NapCat（或其他实现了该扩展的协议端）。插件通过 NoneBot 的通用 `bot.call_api()` 调用，不依赖适配器是否提供同名的类型化方法。

## 使用

1. 安装并加载插件：

   ```bash
   pip install nonebot-plugin-message-emoji
   ```

   在 NoneBot 项目的 `pyproject.toml` 中加入：

   ```toml
   [tool.nonebot]
   plugins = ["nonebot_plugin_message_emoji"]
   ```

2. 在 QQ 中引用目标消息，发送：

   ```text
   /贴 128 277 278
   ```

   单次最多 5 个表情。也可以在命令后直接发送 QQ `face` 表情消息段，插件会读取其 `id`。

如果手机端不能在同一条回复中带上目标表情，可以只发送 `/贴`：

1. 在群聊中引用目标消息，发送 `/贴`。
2. 接下来 10 秒内，由同一用户在同一群聊中逐条发送单独的 QQ 表情。
3. 插件会把这些表情贴到刚才引用的消息上；每收到一个表情，10 秒无操作计时会重新开始，最多处理 5 个。

该会话不会响应其他用户、其他群聊或包含文字/多个消息段的消息；超时或处理满 5 个表情后会自动弃用会话。所有表情都贴成功时不会发送额外提示消息。

`128`、`277` 等是 QQ 表情回应 ID，不是 Unicode 表情名称。NapCat 接口把 `emoji_id` 当作字符串/数字 ID 使用，不规定一个固定的小范围；但它不会把 `😀` 或“笑脸”自动转换成 ID。如需使用某个表情，应先取得对应的 QQ `emoji_id`，或在命令后直接发送 QQ `face` 消息段。

## 参考

- [NoneBot 使用平台接口](https://nonebot.dev/docs/appendices/api-calling)
- [NapCat OneBot 消息接口](https://napneko-napcatqq.mintlify.app/api/onebot/message-actions)
- [NapCat `set_msg_emoji_like` 源码](https://github.com/NapNeko/NapCatQQ/blob/main/packages/napcat-onebot/action/msg/SetMsgEmojiLike.ts)
- [NapCat 接口示例](https://napcat.apifox.cn/226659104e0)
