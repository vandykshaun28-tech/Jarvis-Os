# JARVIS — AI Command Centre

Personal AI assistant for Shaun Van Dyk. PySide6 desktop app with a
Claude-powered brain, voice control, persistent memory, autonomous
research, task management, PC control, and an Obsidian vault bridge.

## Run it

```
pip install -r requirements.txt
python main_v20.py
```

Requires the `ANTHROPIC_API_KEY` environment variable for the Claude brain.
Optional: set `JARVIS_VAULT` to your Obsidian vault path (defaults to
`~/OneDrive/Documents/JARVIS_CORE`).

`python create_shortcut.py` puts a JARVIS shortcut on the desktop.

## Layout

```
main_v20.py          entry point
config.py            ALL paths & settings — the only place to edit them
core/                controller (UI <-> brain glue) + worker thread
brain/               the brain: command router, Claude chat, researcher,
                     research agent, task manager, PC control, self-edit
agents/              system stats agent
memory/              MemoryStore, Obsidian bridge, JSON data files
voice/               TTS engine (persistent SAPI process) + wake-word listener
ui/                  the v20 interface (layouts, components, pages, widgets)
web_search.py        DuckDuckGo search
_archive/            old/duplicate code kept for reference (old HUD app,
                     ai_core2, unused components). Safe to delete.
```

## Notes from the July 2026 cleanup

- All paths now derive from the project folder via `config.py` — the app
  no longer cares where the folder lives or what it's called.
- The brain's PC commands are wired to `brain/pc_control.py` (`PCControl`),
  which has the full command set. The old 5-method `PCController` is archived.
- Command keywords are word-bounded so normal conversation ("my commute",
  "restart the research") can't accidentally trigger PC actions.
- Voice (TTS + wake word) now lives in the v20 app via `core/controller.py`,
  and the microphone mutes itself while JARVIS speaks.
- The brain loads in the worker thread after the window appears — no more
  frozen window on startup, and no more 3-second callback-injection race.
