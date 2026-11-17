### Added

- `/stats` counts the chat demo's calls as `chat-demo`. Its default backend is Anthropic's
  MCP connector, which announces its own client name and takes no custom headers, so the demo
  adds `?client=maplestats-chat` to the endpoint URL. The server accepts a `?client=` value
  only when it matches a label in its fixed list (anything else is ignored and the announced
  name decides), and stores nothing but that label. The privacy page mentions it.
