# Meme 目录

这个目录用于存放表情包文件和表情包元数据。

- `memes.json`：表情包配置，包含名字、路径、描述和触发关键词。
- `__init__.py`：导出 `get_meme_for_text` 函数。

你可以把实际的表情包图片放在 `meme/` 目录下，例如：

- `meme/happy.png`
- `meme/sad.png`
- `meme/ok.png`
- `meme/warning.png`

如果要扩展更多表情包，直接在 `memes.json` 中添加新项。