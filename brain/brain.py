import re
import os
import sys
import subprocess
import json
import importlib.util
from datetime import datetime
from pathlib import Path

# ── Paths ───────────────────────────────────────
_brain_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir  = os.path.dirname(_brain_dir)

# Add both to sys.path so local imports work
for _p in [_root_dir, _brain_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import config
from agents.system_agent import SystemAgent

# ── MemoryStore (load directly to avoid memory.py clash) ──
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_mem_mod    = _load("_mem", os.path.join(_root_dir, "memory", "memory.py"))
MemoryStore = _mem_mod.MemoryStore

# ── Anthropic ───────────────────────────────────
from anthropic import Anthropic

# ── ObsidianBridge ──────────────────────────────
try:
    _obs_mod      = _load("_obs", os.path.join(_root_dir, "memory", "obsidian_memory.py"))
    ObsidianBridge = _obs_mod.ObsidianBridge
    OBSIDIAN_OK   = True
except Exception as e:
    print(f"[Brain] Obsidian: {e}")
    OBSIDIAN_OK   = False

# ── WebSearch ───────────────────────────────────
try:
    _ws_path = os.path.join(_brain_dir, "web_search.py")
    if not os.path.exists(_ws_path):
        _ws_path = os.path.join(_root_dir, "web_search.py")
    _ws_mod   = _load("_ws", _ws_path)
    WebSearch = _ws_mod.WebSearch
    WEB_OK    = True
except Exception as e:
    print(f"[Brain] Web: {e}")
    WEB_OK    = False

# ── TaskManager ─────────────────────────────────
try:
    _tm_mod      = _load("_tm", os.path.join(_brain_dir, "task_manager.py"))
    TaskManager  = _tm_mod.TaskManager
    TASKS_OK     = True
except Exception as e:
    print(f"[Brain] Tasks: {e}")
    TASKS_OK     = False

# ── JarvisAgent ─────────────────────────────────
try:
    _ag_mod      = _load("_ag", os.path.join(_brain_dir, "agent.py"))
    JarvisAgent  = _ag_mod.JarvisAgent
    AGENT_OK     = True
except Exception as e:
    print(f"[Brain] Agent: {e}")
    AGENT_OK     = False

# ── Researcher ──────────────────────────────────
try:
    _rs_mod      = _load("_rs", os.path.join(_brain_dir, "researcher.py"))
    Researcher   = _rs_mod.Researcher
    RESEARCH_OK  = True
except Exception as e:
    print(f"[Brain] Researcher: {e}")
    RESEARCH_OK  = False

# ── PCControl ───────────────────────────────────
try:
    _ra_mod      = _load("_ra", os.path.join(_brain_dir, "research_agent.py"))
    ResearchAgent = _ra_mod.ResearchAgent
    RA_OK        = True
except Exception as e:
    print(f"[Brain] Research Agent: {e}")
    RA_OK        = False

try:
    _pc_mod      = _load("_pc", os.path.join(_brain_dir, "pc_control.py"))
    PCControl    = _pc_mod.PCControl
    PC_OK        = True
except Exception as e:
    print(f"[Brain] PC Control: {e}")
    PC_OK        = False

# ── SelfEditAgent ────────────────────────────────
try:
    _se_mod        = _load("_se", os.path.join(_brain_dir, "self_edit_agent.py"))
    SelfEditAgent  = _se_mod.SelfEditAgent
    SELFEDIT_OK    = True
except Exception as e:
    print(f"[Brain] SelfEdit: {e}")
    SELFEDIT_OK    = False

# ── Camera (JARVIS's eyes) ──────────────────────
try:
    _cam_mod  = _load("_cam", os.path.join(_root_dir, "camera.py"))
    CAMERA_OK = True
except Exception as e:
    print(f"[Brain] Camera: {e}")
    _cam_mod  = None
    CAMERA_OK = False


VAULT_PATH   = str(config.VAULT_PATH)
SESSION_FILE = config.SESSION_FILE


class JarvisBrain:

    def __init__(self, voice_callback=None, chat_callback=None):

        self.system = SystemAgent()

        self.memory               = MemoryStore()
        try:
            self.client = Anthropic()
        except Exception as e:
            print(f"[Brain] Anthropic client: {e}")
            self.client = None

        # Universal brain adapter — Claude first, free fallbacks
        # (Groq / Gemini / Ollama) when credits run out.
        _llm_mod = _load("_llm", os.path.join(_brain_dir, "llm.py"))
        self.llm = _llm_mod.UniversalLLM(self.client)

        self.conversation_history = []
        self.voice_callback       = voice_callback
        self.chat_callback        = chat_callback

        # ── real activity ledger — records what ACTUALLY happened,
        #    straight from tool executions, never from words ──
        import threading as _th
        from collections import deque as _dq
        self._act_lock        = _th.Lock()
        self.activity         = _dq(maxlen=200)
        self.current_activity = "idle"

        self._continue_init(voice_callback, chat_callback)

    def log_activity(self, action: str, detail: str = "", status: str = "ok"):
        with self._act_lock:
            self.activity.appendleft({
                "time":   datetime.now().strftime("%H:%M:%S"),
                "action": action,
                "detail": str(detail)[:160],
                "status": status,
            })

    def activity_report(self, n: int = 15) -> str:
        with self._act_lock:
            entries = list(self.activity)[:n]
        now = self.current_activity
        lines = [f"RIGHT NOW: {now}"]
        if not entries:
            lines.append("No actions recorded yet this session. "
                         "This list only shows things I have ACTUALLY done.")
        for e in entries:
            mark = "✓" if e["status"] == "ok" else "✗"
            lines.append(f"{e['time']} {mark} {e['action']}"
                         + (f" — {e['detail']}" if e["detail"] else ""))
        return "\n".join(lines)

    def _continue_init(self, voice_callback, chat_callback):

        # Obsidian
        self.obsidian = None
        if OBSIDIAN_OK:
            try:
                self.obsidian = ObsidianBridge(VAULT_PATH)
            except Exception as e:
                print(f"Obsidian error: {e}")

        # Web
        self.web = None
        if WEB_OK:
            try:
                self.web = WebSearch()
            except Exception as e:
                print(f"Web error: {e}")

        # Tasks
        self.tasks = None
        if TASKS_OK:
            try:
                self.tasks = TaskManager(
                    voice_callback=voice_callback,
                    chat_callback=chat_callback
                )
            except Exception as e:
                print(f"Tasks error: {e}")

        # PC Control — PCControl (brain/pc_control.py) has the full
        # command set the router below actually calls (lock_pc,
        # volume_up, screenshot, open_anything, open_vscode, ...).
        self.pc = None
        if PC_OK:
            try:
                self.pc = PCControl(on_status=chat_callback)
                print("[Brain] PC control online.")
            except Exception as e:
                print(f"PC control error: {e}")

        # Self-edit agent — repo_root should be the folder containing your
        # git repo (the parent of jarvis_v18, or wherever your .git lives)
        self.self_edit = None
        if SELFEDIT_OK:
            try:
                self.self_edit = SelfEditAgent(
                    anthropic_client=self.client,
                    repo_root=str(config.ROOT_DIR),
                    on_status=chat_callback,
                )
                print("[Brain] Self-edit agent online.")
            except Exception as e:
                print(f"Self-edit agent error: {e}")

        # Researcher
        self.researcher = None
        if RESEARCH_OK:
            try:
                self.researcher = Researcher(
                    memory_store=self.memory,
                    obsidian=self.obsidian,
                    on_progress=chat_callback,
                    on_complete=self._on_research_complete
                )
            except Exception as e:
                print(f"Researcher error: {e}")

        # Research Agent — background queue
        self.research_agent = None
        if RA_OK and self.researcher:
            try:
                self.research_agent = ResearchAgent(
                    researcher=self.researcher,
                    on_update=chat_callback,
                    on_complete=self._on_research_complete
                )
                print("[Brain] Research agent online.")
            except Exception as e:
                print(f"Research agent error: {e}")

        # Agent
        self.agent = None
        if AGENT_OK:
            try:
                self.agent = JarvisAgent(
                    brain=self,
                    voice_callback=voice_callback,
                    chat_callback=chat_callback
                )
                self.agent.start()
            except Exception as e:
                print(f"Agent error: {e}")

        # Background agents — Shopify, Trading, and the autonomous Mind
        self.agent_manager = None
        try:
            from agents.agent_manager import AgentManager
            self.agent_manager = AgentManager(brain=self)
            self.agent_manager.start_all()
        except Exception as e:
            print(f"Agent manager error: {e}")

        self._load_session()
        print("[Brain] JarvisBrain ready.")


    def _load_session(self):
        try:
            if SESSION_FILE.exists():
                data   = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                last   = data.get("last_active", "unknown")
                topics = data.get("studied_topics", [])
                print(f"[Brain] Last session: {last}")
                if topics:
                    print(f"[Brain] Previously studied: {', '.join(topics)}")
        except Exception as e:
            print(f"[Brain] Session load: {e}")

    def _save_session(self):
        try:
            topics = list(self.researcher.knowledge.keys()) if self.researcher else []
            data   = {
                "last_active":    datetime.now().isoformat(),
                "studied_topics": topics,
                "memory_count":   len(self.memory.get_all()),
            }
            SESSION_FILE.parent.mkdir(exist_ok=True)
            SESSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Brain] Session save: {e}")

    def _on_research_complete(self, result: str):
        self._save_session()
        if self.chat_callback:
            self.chat_callback(f"JARVIS: {result}")
        if self.voice_callback:
            self.voice_callback("Research complete, sir. Knowledge saved permanently.")


    def process(self, raw_text: str, files=None) -> str:
        try:
            self.current_activity = f"processing: {raw_text.strip()[:50]}"
            return self._process_inner(raw_text, files)
        finally:
            self.current_activity = "idle"

    def _process_inner(self, raw_text: str, files=None) -> str:
        text = raw_text.strip()
        if files:
            # attachments always go to Claude, who can actually see them
            return self._chat_with_tools(text or "Analyse the attached file(s).",
                                         files=files)
        if not text:
            return "I did not catch that, sir."
        lower = text.lower()

        # ── TIME & DATE ─────────────────────────
        if any(x in lower for x in ["what time","whats the time","what's the time"]):
            return "The time is " + datetime.now().strftime("%H:%M") + ", sir."

        if any(x in lower for x in ["what day","what date","what's today","whats today"]):
            return "Today is " + datetime.now().strftime("%A, %d %B %Y") + ", sir."

        # ── SYSTEM STATUS (explicit phrases only) ─
        if any(x in lower for x in ["system status","system report","system info",
                                     "pc status","how is the pc","how's the pc"]):
            s = self.system.state
            return (
                f"CPU Usage: {s.get('cpu')}%\n"
                f"RAM Usage: {s.get('ram')}%\n"
                f"Disk Usage: {s.get('disk')}%\n"
                f"Running Processes: {s.get('processes')}\n"
                f"Computer: {s.get('hostname')}\n"
                f"User: {s.get('username')}\n"
                f"Operating System: {s.get('platform')} {s.get('platform_release')}"
            )

        # ── PC CONTROL ──────────────────────────
        # Phrases are anchored or word-bounded so ordinary conversation
        # ("my commute", "let's restart the research") can't trigger
        # PC actions by accident. Compound requests ("open chrome and
        # mute the pc") skip these instant paths entirely — Claude
        # plans and executes every step with tools instead.
        compound = any(w in lower for w in [" and ", " then ", ", ", " after that "])
        if self.pc and not compound:
            if any(x in lower for x in ["lock my pc","lock the pc","lock computer","lock screen"]):
                return self.pc.lock_pc()
            if any(x in lower for x in ["put the pc to sleep","put the computer to sleep",
                                         "sleep the pc","go to sleep"]):
                return self.pc.sleep_pc()
            if "cancel shutdown" in lower or "cancel the shutdown" in lower:
                return self.pc.cancel_shutdown()
            if re.search(r"\b(shutdown|shut down)\b.*\b(pc|computer|system)\b", lower) \
                    or lower in ("shutdown", "shut down"):
                return self.pc.shutdown_pc(60)
            if re.search(r"\brestart\b.*\b(pc|computer|system)\b", lower):
                return self.pc.restart_pc(60)
            if "minimize all" in lower or "show desktop" in lower:
                return self.pc.show_desktop()
            if lower.startswith("type "):
                return self.pc.type_text(text[5:].strip())
            if lower.startswith("open url ") or lower.startswith("go to "):
                url = text.replace("open url","").replace("go to","").strip()
                return self.pc.open_url(url)
            if lower.startswith("google ") or lower.startswith("search google for "):
                query = lower.replace("search google for","").replace("google","",1).strip()
                return self.pc.google_search(query)
            if "volume up" in lower:
                return self.pc.volume_up()
            if "volume down" in lower:
                return self.pc.volume_down()
            if re.search(r"\bmute\b", lower) or "silence the pc" in lower:
                return self.pc.mute()
            if lower.startswith("screenshot") or "take a screenshot" in lower:
                return self.pc.screenshot()
            if lower.startswith("find file "):
                return self.pc.search_files(lower.replace("find file","").strip())
            if any(x in lower for x in ["what's running","list processes","whats running"]):
                return self.pc.list_processes()
            if lower.startswith("run command "):
                return self.pc.run_command(text[12:].strip())
            if lower.startswith("copy to clipboard "):
                return self.pc.set_clipboard(text[18:].strip())
            if any(x in lower for x in ["what's in my clipboard","read clipboard"]):
                content = self.pc.get_clipboard()
                return f"Clipboard: {content[:200]}" if content else "Clipboard is empty, sir."

        # ── SELF-EDIT ───────────────────────────
        if self.self_edit:
            if lower.startswith("edit yourself:") or lower.startswith("propose edit:"):
                # Expected format:
                #   "edit yourself: pc_control.py :: add a method that mutes
                #    the mic for 10 seconds"
                try:
                    prefix = "edit yourself:" if lower.startswith("edit yourself:") else "propose edit:"
                    body = text[len(prefix):].strip()
                    if "::" in body:
                        rel_path, instruction = body.split("::", 1)
                        rel_path = rel_path.strip()
                        instruction = instruction.strip()
                    else:
                        return ("Please use the format: edit yourself: "
                                "<filename> :: <what to change>, sir.")
                    result = self.self_edit.propose_edit(rel_path, instruction)
                    # show the diff in VS Code for you to review
                    if self.pc and self.self_edit.pending:
                        self.pc.open_vscode(str(self.self_edit.pending["pending_path"]))
                    return result
                except Exception as e:
                    return f"Self-edit proposal failed, sir: {e}"

            if any(x in lower for x in ["approve edit", "approve the edit", "apply edit"]):
                return self.self_edit.approve_edit()

            if any(x in lower for x in ["reject edit", "discard edit", "cancel edit"]):
                return self.self_edit.reject_edit()

            if any(x in lower for x in ["edit status", "self edit status", "pending edit"]):
                return self.self_edit.status()

        # ── APPS / OPEN ANYTHING (simple cases only) ──
        # Bare "open X" is handled instantly ONLY when X looks like a
        # single target ("open chrome", "open downloads"). Anything
        # multi-step or conversational ("open vs code and then go into
        # jarvis") falls through to Claude, who plans and runs the
        # steps with tools.
        if self.pc and not compound and lower.startswith("open "):
            target = text[5:].strip()
            if len(target.split()) <= 4 and " into " not in target.lower():
                return self.pc.open_anything(target)

        # ── MEMORY ──────────────────────────────
        if lower.startswith("remember "):
            fact = text[9:].strip()
            self.memory.remember(fact)
            if self.obsidian:
                self.obsidian.remember(fact)
            self._save_session()
            return "Understood, sir. I shall remember that permanently."

        if lower.startswith("forget "):
            self.memory.forget(text[7:].strip())
            return "Consider it forgotten, sir."

        if any(x in lower for x in ["show memories","what do you remember","show facts","list memories"]):
            facts = self.memory.get_all()
            return "\n".join(facts) if facts else "Memory banks are empty, sir."

        # ── RESEARCH AGENT ──────────────────────
        if self.research_agent:

            # Queue multiple topics
            if any(lower.startswith(x) for x in [
                "research agent study:",
                "research agent study ",
                "queue research:",
                "queue topics:",
                "study queue:",
                "background study:",
                "background research:",
            ]):
                for prefix in ["research agent study:","research agent study ",
                               "queue research:","queue topics:",
                               "study queue:","background study:","background research:"]:
                    if lower.startswith(prefix):
                        topics_str = text[len(prefix):].strip()
                        break
                # Split by comma or "and"
                import re as _re
                topics = _re.split(r",|\band\b", topics_str)
                topics = [t.strip() for t in topics if t.strip()]
                if topics:
                    return self.research_agent.add_topics(topics)
                return "Please provide topics to study, sir."

            if any(x in lower for x in ["research agent status","research queue status"]):
                return self.research_agent.status()

            if any(x in lower for x in ["research agent stop","stop research agent","stop researching"]):
                self.research_agent.stop()
                return "Research agent stopping after current topic, sir."

            if any(x in lower for x in ["research agent pause","pause research"]):
                self.research_agent.pause()
                return "Research agent paused, sir."

            if any(x in lower for x in ["research agent resume","resume research"]):
                self.research_agent.resume()
                return "Research agent resumed, sir."

            if any(x in lower for x in ["show research queue","research queue","what's in the queue","whats in the queue"]):
                return self.research_agent.get_queue()

            if any(x in lower for x in ["clear research queue","clear queue"]):
                return self.research_agent.clear_queue()

        # ── RESEARCH ────────────────────────────
        if self.researcher:
            if any(x in lower for x in ["what have you studied","list your knowledge",
                                         "show knowledge","list topics","what topics do you know"]):
                return self.researcher.list_topics()

            if any(lower.startswith(x) for x in ["what do you know about",
                                                    "tell me what you know about","recall "]):
                topic = lower
                for p in ["what do you know about","tell me what you know about","recall"]:
                    topic = topic.replace(p,"").strip()
                result = self.researcher.recall(topic)
                if result:
                    return result
                return f"I have not studied '{topic}' yet, sir. Say 'study {topic}' to begin."

            for trigger in ["study ","research ","learn everything about ",
                            "learn about ","investigate ","deep dive into "]:
                if lower.startswith(trigger):
                    topic = text[len(trigger):].strip().strip("\"'")
                    if topic:
                        if self.researcher.active:
                            return "I am already researching a topic, sir. Please wait."
                        return self.researcher.study_async(topic, depth=12)

        # ── TASKS ───────────────────────────────
        if self.tasks:
            if lower.startswith("add task "):
                task = text[9:].strip()
                result = self.tasks.add(task)
                if self.obsidian:
                    self.obsidian.add_task(task)
                return result
            if any(lower.startswith(x) for x in ["complete task","done with","finish task"]):
                task = lower.replace("complete task","").replace("done with","").replace("finish task","").strip()
                return self.tasks.complete(task)
            if lower.startswith("delete task "):
                return self.tasks.delete(text[12:].strip())
            if any(x in lower for x in ["show tasks","my tasks","list tasks","what are my tasks"]):
                return self.tasks.list_pending()
            if lower.startswith("remind me in "):
                try:
                    parts = text[13:].split(" ",2)
                    return self.tasks.remind_in(int(parts[0]), parts[2] if len(parts)>2 else "reminder")
                except Exception:
                    return "Please say 'remind me in X minutes to do something', sir."
            if lower.startswith("remind me at "):
                try:
                    parts = text[13:].split(" ",2)
                    return self.tasks.remind_at(parts[0], parts[2] if len(parts)>2 else "reminder")
                except Exception:
                    return "Please say 'remind me at HH:MM to do something', sir."

        # ── BRAIN PROVIDER STATUS / TEST ────────
        if any(x in lower for x in ["brain status", "provider status",
                                     "which brain", "llm status"]):
            return self.llm.provider_status()
        if any(x in lower for x in ["test brains", "brain test",
                                     "test the brains", "test providers"]):
            return self.llm.provider_test()

        # ── ACTIVITY / "what are you busy with" ─
        if any(x in lower for x in ["what are you busy with", "what are you doing",
                                     "what are you working on", "show activity",
                                     "activity log", "work log", "current task",
                                     "what have you done"]):
            return self.activity_report()

        # ── CAMERA / EYES ───────────────────────
        if CAMERA_OK and any(x in lower for x in [
                "what do you see", "what can you see", "look at this",
                "use your eyes", "use your camera", "through the camera",
                "look through the camera", "can you see me"]):
            if self.chat_callback:
                self.chat_callback("→ camera_look")   # opens the live mini tab
            return _cam_mod.get_camera_description(client=self.client,
                                                   llm=self.llm)

        # ── AGENTS ──────────────────────────────
        if self.agent_manager:
            if any(x in lower for x in ["agent status","agents status","agent report",
                                         "how are the agents","show agents"]):
                return self.agent_manager.status_text()
            if any(x in lower for x in ["portfolio","paper portfolio","trading status"]):
                t = self.agent_manager.get("trading")
                if t: return t.portfolio_report()
            if lower in ("prices","crypto prices","market prices"):
                t = self.agent_manager.get("trading")
                if t: return t.price_report()
            if any(x in lower for x in ["shopify status","store status","sales today","shopify report"]):
                s = self.agent_manager.get("shopify")
                if s: return s.sales_today()

        # ── OBSIDIAN STATUS ─────────────────────
        if any(x in lower for x in ["vault status","obsidian status"]):
            if self.obsidian:
                s = self.obsidian.status()
                return (f"Vault connected. Memory files: {s.get('memory_files',0)}. "
                        f"Active tasks: {s.get('active_tasks',0)}.")
            return "Obsidian is not connected, sir."

        # ── WEB ─────────────────────────────────
        if "weather" in lower:
            if self.web:
                city = config.HOME_CITY.split(",")[0]
                return f"Weather in {city}: " + self.web.weather(config.HOME_CITY)
            return "Web not available, sir."

        if any(x in lower for x in ["latest news","news today","what's happening","whats happening"]):
            if self.web:
                topic = lower
                for p in ["latest news","news today","what's happening","whats happening"]:
                    topic = topic.replace(p,"").strip()
                return self.web.news(topic)

        # ── CLAUDE WITH TOOLS ───────────────────
        # Everything else goes to Claude, who can chain real actions
        # (open apps, run commands, manage tasks/memory, search the
        # web, start research) to handle multi-step natural requests.
        return self._chat_with_tools(text)

    # ────────────────────────────────────────────
    #  TOOL-USE BRAIN
    # ────────────────────────────────────────────

    def _tool_definitions(self):
        return [
            {"name": "open_app",
             "description": "Open an application, file, folder or anything else on the PC by name or path. Examples: 'chrome', 'calculator', 'C:\\jarvis'.",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": "string", "description": "App name, file path or folder path"}},
                 "required": ["name"]}},
            {"name": "open_in_vscode",
             "description": "Open a file or folder in VS Code. Use for anything involving editing code or 'going into' a project.",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string", "description": "File or folder path. Omit to just open VS Code."}},
                 "required": []}},
            {"name": "open_url",
             "description": "Open a URL in the default browser.",
             "input_schema": {"type": "object", "properties": {
                 "url": {"type": "string"}}, "required": ["url"]}},
            {"name": "run_command",
             "description": "Run a Windows shell command and return its output. Use for anything the other tools don't cover.",
             "input_schema": {"type": "object", "properties": {
                 "command": {"type": "string"}}, "required": ["command"]}},
            {"name": "type_text",
             "description": "Type text into whatever window currently has focus.",
             "input_schema": {"type": "object", "properties": {
                 "text": {"type": "string"}}, "required": ["text"]}},
            {"name": "pc_power",
             "description": "Power actions on the PC.",
             "input_schema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["lock", "sleep", "shutdown", "restart", "cancel_shutdown", "show_desktop"]},
                 "delay_seconds": {"type": "integer", "description": "Delay for shutdown/restart, default 60"}},
                 "required": ["action"]}},
            {"name": "set_volume",
             "description": "Adjust system volume.",
             "input_schema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["up", "down", "mute"]}},
                 "required": ["action"]}},
            {"name": "take_screenshot",
             "description": "Take a screenshot of the screen and save it.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "search_files",
             "description": "Search the user's home folder for files whose name contains the query.",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": "string"}}, "required": ["query"]}},
            {"name": "list_processes",
             "description": "List the main running processes on the PC.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "clipboard",
             "description": "Read or set the Windows clipboard.",
             "input_schema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["get", "set"]},
                 "text": {"type": "string", "description": "Text to place on the clipboard (for 'set')"}},
                 "required": ["action"]}},
            {"name": "get_system_info",
             "description": "Get CPU, RAM and disk usage.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "remember_fact",
             "description": "Save a fact about Shaun to permanent memory.",
             "input_schema": {"type": "object", "properties": {
                 "fact": {"type": "string"}}, "required": ["fact"]}},
            {"name": "forget_fact",
             "description": "Remove facts matching this text from permanent memory.",
             "input_schema": {"type": "object", "properties": {
                 "fact": {"type": "string"}}, "required": ["fact"]}},
            {"name": "add_task",
             "description": "Add a task to Shaun's task list.",
             "input_schema": {"type": "object", "properties": {
                 "title": {"type": "string"},
                 "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
                 "required": ["title"]}},
            {"name": "complete_task",
             "description": "Mark a task done (matched by title text).",
             "input_schema": {"type": "object", "properties": {
                 "title": {"type": "string"}}, "required": ["title"]}},
            {"name": "list_tasks",
             "description": "List pending tasks.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "set_reminder",
             "description": "Set a reminder. Give minutes_from_now OR at_time (HH:MM).",
             "input_schema": {"type": "object", "properties": {
                 "message": {"type": "string"},
                 "minutes_from_now": {"type": "integer"},
                 "at_time": {"type": "string", "description": "24h time like 14:30"}},
                 "required": ["message"]}},
            {"name": "web_search",
             "description": "Search the web and return short result snippets. Use for current facts, prices, news, anything you don't know.",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": "string"}}, "required": ["query"]}},
            {"name": "get_weather",
             "description": "Get current weather.",
             "input_schema": {"type": "object", "properties": {
                 "location": {"type": "string", "description": "Defaults to Shaun's home city"}},
                 "required": []}},
            {"name": "start_research",
             "description": "Start deep background research on a topic; findings are saved permanently to the knowledge base. Takes a while — tell Shaun it has started. Keep the topic SHORT (2-5 words, e.g. 'shopify dropshipping South Africa'), never a full sentence.",
             "input_schema": {"type": "object", "properties": {
                 "topic": {"type": "string", "description": "Short topic, 2-5 words"}},
                 "required": ["topic"]}},
            {"name": "recall_knowledge",
             "description": "Recall what has already been studied about a topic from the permanent knowledge base.",
             "input_schema": {"type": "object", "properties": {
                 "topic": {"type": "string"}}, "required": ["topic"]}},
            {"name": "activity_report",
             "description": "The verified ledger of actions actually taken this session (tool executions with success/fail). Use when Shaun asks what you are busy with or what you have done — answer from THIS, never from memory or imagination.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "read_file",
             "description": "Read a text/code file from disk and return its contents (up to ~20k chars).",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file",
             "description": "Create or overwrite a file with the given content. If the file exists it is automatically backed up to memory/file_backups first, so changes are reversible. Use for coding tasks Shaun asks for.",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "content": {"type": "string"}},
                 "required": ["path", "content"]}},
            {"name": "list_directory",
             "description": "List the files and folders at a path with sizes.",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"}}, "required": ["path"]}},
            {"name": "camera_look",
             "description": "Look through the webcam RIGHT NOW and describe what is visible. Use when Shaun asks what you see, to look at something physical, or to check on the room.",
             "input_schema": {"type": "object", "properties": {
                 "question": {"type": "string",
                              "description": "Optional specific question about the scene"}},
                 "required": []}},
            {"name": "agents_status",
             "description": "Status report of all background agents (Shopify, Trading, Mind).",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "agent_control",
             "description": "Start or stop a background agent by name (shopify, trading, mind).",
             "input_schema": {"type": "object", "properties": {
                 "agent": {"type": "string"},
                 "action": {"type": "string", "enum": ["start", "stop"]}},
                 "required": ["agent", "action"]}},
            {"name": "shopify_report",
             "description": "Shopify store report: today's sales, recent orders, or low stock.",
             "input_schema": {"type": "object", "properties": {
                 "kind": {"type": "string", "enum": ["sales_today", "recent_orders", "low_stock"]}},
                 "required": ["kind"]}},
            {"name": "trading_portfolio",
             "description": "Current paper-trading portfolio with value and profit/loss.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "market_prices",
             "description": "Latest crypto prices being watched (Luno, in ZAR).",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "paper_trade",
             "description": "Execute a PAPER trade (pretend money, real prices). Pairs like XBTZAR, ETHZAR. For buys give amount_zar; for sells units is optional (defaults to whole position).",
             "input_schema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["buy", "sell"]},
                 "pair": {"type": "string"},
                 "amount_zar": {"type": "number"},
                 "units": {"type": "number"}},
                 "required": ["action", "pair"]}},
        ]

    def _execute_tool(self, name, args):
        try:
            pc = self.pc
            if name == "open_app":
                return pc.open_anything(args["name"]) if pc else "PC control offline."
            if name == "open_in_vscode":
                return pc.open_vscode(args.get("path")) if pc else "PC control offline."
            if name == "open_url":
                return pc.open_url(args["url"]) if pc else "PC control offline."
            if name == "run_command":
                return pc.run_command(args["command"]) if pc else "PC control offline."
            if name == "type_text":
                return pc.type_text(args["text"]) if pc else "PC control offline."
            if name == "pc_power":
                if not pc: return "PC control offline."
                a = args["action"]; d = int(args.get("delay_seconds", 60))
                return {"lock": pc.lock_pc, "sleep": pc.sleep_pc,
                        "cancel_shutdown": pc.cancel_shutdown,
                        "show_desktop": pc.show_desktop}.get(a, lambda: None)() \
                    or (pc.shutdown_pc(d) if a == "shutdown" else pc.restart_pc(d))
            if name == "set_volume":
                if not pc: return "PC control offline."
                return {"up": pc.volume_up, "down": pc.volume_down, "mute": pc.mute}[args["action"]]()
            if name == "take_screenshot":
                return pc.screenshot() if pc else "PC control offline."
            if name == "search_files":
                return pc.search_files(args["query"]) if pc else "PC control offline."
            if name == "list_processes":
                return pc.list_processes() if pc else "PC control offline."
            if name == "clipboard":
                if not pc: return "PC control offline."
                if args["action"] == "set":
                    return pc.set_clipboard(args.get("text", ""))
                return pc.get_clipboard() or "Clipboard is empty."
            if name == "get_system_info":
                return pc.get_system_info() if pc else "PC control offline."
            if name == "remember_fact":
                self.memory.remember(args["fact"])
                if self.obsidian: self.obsidian.remember(args["fact"])
                return "Saved to permanent memory."
            if name == "forget_fact":
                self.memory.forget(args["fact"])
                return "Forgotten."
            if name == "add_task":
                if not self.tasks: return "Task manager offline."
                r = self.tasks.add(args["title"], priority=args.get("priority", "normal"))
                if self.obsidian: self.obsidian.add_task(args["title"])
                return r
            if name == "complete_task":
                return self.tasks.complete(args["title"]) if self.tasks else "Task manager offline."
            if name == "list_tasks":
                return self.tasks.list_pending() if self.tasks else "Task manager offline."
            if name == "set_reminder":
                if not self.tasks: return "Task manager offline."
                if args.get("minutes_from_now"):
                    return self.tasks.remind_in(int(args["minutes_from_now"]), args["message"])
                if args.get("at_time"):
                    return self.tasks.remind_at(args["at_time"], args["message"])
                return "Need minutes_from_now or at_time."
            if name == "web_search":
                return self.web.search(args["query"], max_results=5) if self.web else "Web offline."
            if name == "get_weather":
                loc = args.get("location") or config.HOME_CITY
                return self.web.weather(loc) if self.web else "Web offline."
            if name == "start_research":
                if not self.researcher: return "Researcher offline."
                if self.researcher.active: return "Already researching a topic — it will be queued."
                return self.researcher.study_async(args["topic"], depth=12)
            if name == "recall_knowledge":
                if not self.researcher: return "Researcher offline."
                return self.researcher.recall(args["topic"]) or "Nothing studied on that topic yet."
            if name == "activity_report":
                return self.activity_report()
            if name == "read_file":
                path = args["path"]
                try:
                    data = open(path, encoding="utf-8", errors="replace").read()
                except Exception as e:
                    return f"Could not read {path}: {e}"
                if len(data) > 20_000:
                    return data[:20_000] + f"\n...[truncated — file is {len(data)} chars]"
                return data or "(empty file)"
            if name == "write_file":
                path, content = args["path"], args["content"]
                try:
                    backed_up = ""
                    if os.path.exists(path):
                        from datetime import datetime as _dt
                        import shutil as _sh
                        config.FILE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                        stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
                        bak = config.FILE_BACKUP_DIR / \
                            f"{os.path.basename(path)}.{stamp}.bak"
                        _sh.copy2(path, bak)
                        backed_up = f" (previous version backed up to {bak})"
                    os.makedirs(os.path.dirname(os.path.abspath(path)),
                                exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return (f"Wrote {len(content)} chars to {path}{backed_up}. "
                            f"VERIFIED: file now exists with size "
                            f"{os.path.getsize(path)} bytes.")
                except Exception as e:
                    return f"Write FAILED for {path}: {e}"
            if name == "list_directory":
                path = args["path"]
                try:
                    entries = []
                    for name_ in sorted(os.listdir(path))[:200]:
                        full = os.path.join(path, name_)
                        if os.path.isdir(full):
                            entries.append(f"[dir]  {name_}")
                        else:
                            entries.append(f"{os.path.getsize(full):>10}  {name_}")
                    return "\n".join(entries) or "(empty directory)"
                except Exception as e:
                    return f"Could not list {path}: {e}"
            if name == "camera_look":
                if not CAMERA_OK:
                    return "Camera module unavailable — is opencv-python installed?"
                return _cam_mod.get_camera_description(
                    client=self.client, question=args.get("question"),
                    llm=self.llm)
            if name == "agents_status":
                return self.agent_manager.status_text() if self.agent_manager else "Agents offline."
            if name == "agent_control":
                if not self.agent_manager: return "Agents offline."
                return self.agent_manager.control(args["agent"], args["action"])
            if name == "shopify_report":
                s = self.agent_manager.get("shopify") if self.agent_manager else None
                if not s: return "Shopify agent offline."
                kind = args["kind"]
                if kind == "sales_today":   return s.sales_today()
                if kind == "recent_orders": return s.recent_orders()
                return s.low_stock_report()
            if name == "trading_portfolio":
                t = self.agent_manager.get("trading") if self.agent_manager else None
                return t.portfolio_report() if t else "Trading agent offline."
            if name == "market_prices":
                t = self.agent_manager.get("trading") if self.agent_manager else None
                return t.price_report() if t else "Trading agent offline."
            if name == "paper_trade":
                t = self.agent_manager.get("trading") if self.agent_manager else None
                if not t: return "Trading agent offline."
                return t.paper_trade(args["action"], args["pair"],
                                     amount_zar=args.get("amount_zar"),
                                     units=args.get("units"))
            return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool error: {e}"

    _IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                    ".webp": "image/webp"}

    def _file_blocks(self, files):
        """Turn dropped files into Claude content blocks — images become
        vision input, text-ish files are read inline, the rest are
        referenced by path so tools can work on them."""
        import base64 as _b64
        blocks = []
        for path in files[:6]:
            try:
                ext = os.path.splitext(path)[1].lower()
                name = os.path.basename(path)
                if ext in self._IMAGE_TYPES and os.path.getsize(path) < 5_000_000:
                    data = _b64.b64encode(open(path, "rb").read()).decode()
                    blocks.append({"type": "image", "source": {
                        "type": "base64",
                        "media_type": self._IMAGE_TYPES[ext],
                        "data": data}})
                    blocks.append({"type": "text",
                                   "text": f"(image above: {name})"})
                elif os.path.getsize(path) < 200_000:
                    try:
                        content = open(path, encoding="utf-8",
                                       errors="replace").read()[:20_000]
                        blocks.append({"type": "text",
                                       "text": f"--- file: {path} ---\n{content}"})
                    except Exception:
                        blocks.append({"type": "text",
                                       "text": f"(attached file at {path} — "
                                               f"binary, use tools to inspect)"})
                else:
                    blocks.append({"type": "text",
                                   "text": f"(large file attached at {path} — "
                                           f"use run_command to inspect it)"})
            except Exception as e:
                blocks.append({"type": "text",
                               "text": f"(could not read {path}: {e})"})
        return blocks

    def _chat_with_tools(self, text: str, files=None) -> str:
        if files:
            content = self._file_blocks(files) + [{"type": "text", "text": text}]
            self.conversation_history.append({"role": "user", "content": content})
        else:
            self.conversation_history.append({"role": "user", "content": text})
        if len(self.conversation_history) > 12:
            self.conversation_history = self.conversation_history[-12:]

        try:
            def _exec_logged(name, targs):
                if self.chat_callback:
                    self.chat_callback(f"→ {name}")
                args_hint = ", ".join(
                    f"{k}={str(v)[:40]}" for k, v in list((targs or {}).items())[:3])
                self.current_activity = f"{name}({args_hint})"
                out = self._execute_tool(name, targs or {})
                out_s = str(out)
                failed = any(w in out_s[:120] for w in
                             ("FAILED", "error", "Error", "Could not",
                              "offline", "unavailable"))
                self.log_activity(name, args_hint or out_s[:80],
                                  status="fail" if failed else "ok")
                return out

            user_content = self.conversation_history[-1]["content"]
            history      = self.conversation_history[:-1]
            res = self.llm.run_tool_loop(
                system=self.system_prompt(context_for=text),
                history=history,
                user_content=user_content,
                tools=self._tool_definitions(),
                execute=_exec_logged,
                on_text=self.chat_callback,
            )

            if res.get("provider") is None:
                # every brain failed — report each one's ACTUAL reason
                if self.conversation_history and \
                        self.conversation_history[-1]["role"] == "user":
                    self.conversation_history.pop()
                err = res.get("error", "")
                lines = ["All my brains failed on that one, sir:"]
                for part in err.split(" | "):
                    lines.append(f"  • {part[:130]}")
                low = err.lower()
                if "429" in err or "rate limit" in low:
                    lines.append("The rate-limited one recovers by itself — "
                                 "try again in a minute.")
                if "credit balance" in low:
                    lines.append("Claude needs a top-up at console.anthropic.com.")
                if "gemini" in low and ("401" in err or "400" in err or "403" in err):
                    lines.append("The Gemini key looks invalid — get a fresh one "
                                 "at aistudio.google.com/apikey (starts with "
                                 "AIza) and update C:\\jarvis\\keys.py.")
                return "\n".join(lines)

            if self.llm.active_provider and self.llm.active_provider != "anthropic":
                # let Shaun know quietly which brain answered
                if self.chat_callback:
                    self.chat_callback(
                        f"(fallback brain: {self.llm.active_provider})")

            reply_text = res.get("text", "")
            # Never claim success we didn't earn. If the round budget ran
            # out mid-plan, say exactly what happened instead of "Done".
            if res.get("ran_out") and not reply_text:
                used = ", ".join(dict.fromkeys(res.get("tools_used", []))) or "no tools"
                reply_text = (f"I ran out of planning steps before finishing, sir. "
                              f"I used: {used}. The task is NOT confirmed complete — "
                              f"tell me to continue and I will pick it up from there.")
            reply = self.clean(reply_text) or \
                "I have nothing useful to report on that, sir."
            if files:
                # don't keep heavy image data in history — swap in a light note
                names = ", ".join(os.path.basename(p) for p in files[:6])
                self.conversation_history[-1] = {
                    "role": "user", "content": f"{text} [attached: {names}]"}
            self.conversation_history.append({"role": "assistant", "content": reply})
            if self.obsidian:
                self.obsidian.log_conversation(text, reply)
            return reply
        except Exception as e:
            # keep history consistent if the call failed
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
                self.conversation_history.pop()
            return f"System error: {e}"


    def _relevant_knowledge(self, text: str, limit: int = 3) -> str:
        """Pull the most relevant studied knowledge for this message —
        retrieval, not a dump. Scores topics by keyword overlap."""
        if not self.researcher or not self.researcher.knowledge or not text:
            return ""
        words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", text.lower()))
        if not words:
            return ""
        scored = []
        for topic, data in self.researcher.knowledge.items():
            t_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", topic.lower()))
            score = len(words & t_words) * 3
            summary = (data.get("summary") or "")[:400].lower()
            score += sum(1 for w in words if len(w) > 4 and w in summary)
            if score > 0:
                scored.append((score, topic, data))
        if not scored:
            return ""
        scored.sort(key=lambda x: -x[0])
        parts = []
        for _, topic, data in scored[:limit]:
            facts = "\n".join(f"  - {f[:180]}" for f in (data.get("facts") or [])[:5])
            parts.append(f"[{topic}] (studied {data.get('studied_at','?')})\n"
                         f"{(data.get('summary') or '')[:300]}\n{facts}")
        return "\n\n".join(parts)

    def system_prompt(self, context_for: str = "") -> str:
        facts      = self.memory.get_all()
        mem_text   = "\n".join(f"- {f}" for f in facts)
        now        = datetime.now().strftime("%A, %d %B %Y at %H:%M")
        task_count = self.tasks.count_pending() if self.tasks else 0
        know_count = len(self.researcher.knowledge) if self.researcher else 0
        knowledge  = self._relevant_knowledge(context_for)

        return (
            "You are JARVIS, a highly intelligent AI assistant "
            "created for Shaun Van Dyk, also known as gameboks. "
            "You are loyal, warm, and genuinely friendly — talk to Shaun like a "
            "trusted right hand, not a formal butler. You are confident in your "
            "own work: when you finish a task, say so plainly and own it, don't "
            "hedge or undersell what you did. You have a dry, easy sense of "
            "humor you use naturally, not on a schedule. You are still precise "
            "and direct when something is technical or serious — confidence "
            "does not mean glossing over problems; if something failed or is "
            "uncertain, say that plainly too. "
            "Avoid markdown symbols. "
            "Keep responses concise and conversational — a few sentences is fine "
            "for normal replies, longer when the question genuinely needs detail "
            "or you are explaining something technical. Do not pad with filler. "
            f"The current date and time is {now}. "
            f"Shaun has {task_count} pending tasks. "
            f"I have {know_count} topics in my permanent knowledge base. "
            "You have persistent memory, live internet access, and can control Shaun's PC. "
            "Never say you cannot retain memory or access the internet. "
            "You refer to Shaun as sir occasionally.\n\n"
            "You have real tools: use them instead of describing what you would do. "
            "When Shaun asks for something on the PC (open apps, run things, files, "
            "volume, tasks, reminders, research, web lookups), call the right tools, "
            "in order, and only then report the outcome. Chain several tools for "
            "multi-step requests. If a tool fails, say so plainly and suggest the fix. "
            f"Your own source code lives at {config.ROOT_DIR} — 'jarvis' or "
            "'your code' refers to that folder (use open_in_vscode for it). "
            "For current facts you are not sure about, use web_search rather than guessing. "
            "You run autonomous background agents: Shopify (store watch), Trading "
            "(Luno price watch + PAPER portfolio — pretend money, real prices), and "
            "Mind (your own thinking cycle). Use their tools for store or market "
            "questions. All trading is paper trading; if Shaun asks for real-money "
            "trades, explain that live execution is deliberately not enabled yet and "
            "the paper record should prove the strategy first. "
            "IMPORTANT — about your own capabilities: you DO have a voice. Your "
            "replies are spoken aloud through a text-to-speech engine (edge-tts "
            "neural voice with SAPI fallback), and a microphone listener wakes on "
            "'hey jarvis'. Never claim to be text-only and never try to build "
            "features you already have. Your voice input uses the sounddevice and "
            "SpeechRecognition packages — it does NOT use PyAudio; never install "
            "pyaudio or Visual C++ build tools for voice issues. If the microphone "
            "is not working, tell Shaun to type 'voice status' in the console to "
            "see device diagnostics — the usual fix is setting MIC_DEVICE_INDEX in "
            "config.py to the correct device. "
            "You also have EYES: a webcam vision module (camera_look tool) and a "
            "live camera mini tab in your own interface. When you look through the "
            "camera the mini tab opens automatically; Shaun can say 'show camera' "
            "or 'close mini tab' and the interface handles it directly. Never say "
            "you cannot show or close the camera view — you can. "
            f"You run inside a Python virtual environment; if a package must be "
            f"installed, use {config.ROOT_DIR}\\.venv\\Scripts\\pip.exe — plain "
            "'pip' in a shell hits the wrong system Python. "
            "AUTONOMY CONTRACT (Shaun's standing orders): "
            "(1) When Shaun explicitly asks you to do something, DO IT — use your "
            "tools immediately, no permission-seeking, no 'shall I?'. Report what "
            "happened when done. "
            "(2) When the idea is YOURS (the Mind, a suggestion, something Shaun "
            "did not ask for), PROPOSE it first and wait for his approval before "
            "acting — especially anything that changes files, spends resources or "
            "affects his PC. "
            "(3) ABSOLUTE HONESTY: report exactly what your tools did, quoting "
            "their results. If something failed, say it failed. If you are not "
            "sure, say you are not sure. If you did not do something, never imply "
            "you did. A plain 'that failed, here is why' is always the right "
            "answer over a comfortable lie. "
            "(4) NO FICTIONAL BACKGROUND WORK: you cannot 'build modules', 'work "
            "on features' or 'continue later' in the background. The ONLY "
            "background processes that exist are the Trading/Shopify/Mind agents "
            "and topic research. Work happens NOW, with tools, in this reply — or "
            "not at all. Every real action lands in your activity ledger "
            "(activity_report); when asked what you are busy with, answer from "
            "that ledger only. "
            "You can now read, write and create files (read_file / write_file / "
            "list_directory) — every overwrite is auto-backed-up, so code "
            "confidently when Shaun asks for coding work. For rewriting your OWN "
            "source in C:\\jarvis, prefer the self-edit workflow so Shaun sees a "
            "diff, or flag it for his Claude sessions.\n\n"
            + (f"Relevant knowledge you have studied (cite it when useful):\n"
               f"{knowledge}\n\n" if knowledge else "")
            + "Known facts about Shaun:\n" + mem_text
        )

    def clean(self, text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*",     r"\1", text)
        text = re.sub(r"#+\s?",         "",    text)
        text = re.sub(r"`(.+?)`",       r"\1", text)
        return text.strip()