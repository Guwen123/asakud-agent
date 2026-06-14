# Project Memory

Durable project facts, environment notes, and recurring fixes.

## Project Facts

- sakuro-agent is a local long-running memory agent connected to workflow nodes, tools, Markdown memory, RAG memory, and NapCat message I/O.

## Environment

- Runtime timezone: Asia/Shanghai.

## Long Term Notes

- Meme images from NapCat CQ messages should be handled by the meme node and local meme storage, not by giving QQ manual setup instructions.

## Known Fixes

- ATRI roleplay is default-enabled when the atri-roleplay skill is loaded.
- Old assistant replies that mention activation commands, model branding, or manual QQ meme setup should not be imported as useful short-term context.
