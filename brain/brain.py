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


VAULT_PATH     = r"C:\Users\gameboks\OneDrive\Documents\JARVIS_CORE"
KNOWLEDGE_FILE = Path(r"C:\jarvis_v18\memory\knowledge.json")
SESSION_FILE   = Path(r"C:\jarvis_v18\memory\last_session.json")


class JarvisBrain:

    def __init__(self, voice_callback=None, chat_callback=None):
        self.memory               = MemoryStore()
        self.client               = Anthropic()
        self.conversation_history = []
        self.voice_callback       = voice_callback
        self.chat_callback        = chat_callback

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

        # PC Control
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
                    repo_root=r"C:\jarvis_v18",   # <-- adjust to your actual git root
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


    def process(self, raw_text: str) -> str:
        text  = raw_text.strip()
        if not text:
            return "I did not catch that, sir."
        lower = text.lower()

        # ── TIME & DATE ─────────────────────────
        if any(x in lower for x in ["what time","whats the time","what's the time"]):
            return "The time is " + datetime.now().strftime("%H:%M") + ", sir."

        if any(x in lower for x in ["what day","what date","what's today","whats today"]):
            return "Today is " + datetime.now().strftime("%A, %d %B %Y") + ", sir."

        # ── PC CONTROL ──────────────────────────
        if self.pc:
            if any(x in lower for x in ["lock my pc","lock the pc","lock computer","lock screen"]):
                return self.pc.lock_pc()
            if any(x in lower for x in ["sleep","put the pc to sleep"]):
                return self.pc.sleep_pc()
            if "shutdown" in lower or "shut down the pc" in lower:
                return self.pc.shutdown_pc(60)
            if "cancel shutdown" in lower:
                return self.pc.cancel_shutdown()
            if "restart" in lower and any(x in lower for x in ["pc","computer","system"]):
                return self.pc.restart_pc(60)
            if "minimize all" in lower or "show desktop" in lower:
                return self.pc.show_desktop()
            if lower.startswith("type "):
                return self.pc.type_text(text[5:].strip())
            if lower.startswith("open url ") or lower.startswith("go to "):
                url = text.replace("open url","").replace("go to","").strip()
                return self.pc.open_url(url)
            if lower.startswith("google ") or lower.startswith("search google for "):
                query = lower.replace("google","").replace("search google for","").strip()
                return self.pc.google_search(query)
            if "volume up" in lower:
                return self.pc.volume_up()
            if "volume down" in lower:
                return self.pc.volume_down()
            if any(x in lower for x in ["mute","silence the pc"]):
                return self.pc.mute()
            if "screenshot" in lower:
                return self.pc.screenshot()
            if any(x in lower for x in ["system info","pc status","how is the pc"]):
                return self.pc.get_system_info()
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

        # ── APPS / OPEN ANYTHING ─────────────────
        if self.pc and lower.startswith("open "):
            target = text[5:].strip()
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

            if any(x in lower for x in ["research agent status","research queue status","agent status"]):
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
                return "Weather in Benoni: " + self.web.weather("Benoni, South Africa")
            return "Web not available, sir."

        if any(x in lower for x in ["latest news","news today","what's happening","whats happening"]):
            if self.web:
                topic = lower
                for p in ["latest news","news today","what's happening","whats happening"]:
                    topic = topic.replace(p,"").strip()
                return self.web.news(topic)

        if any(x in lower for x in ["search for","look up","who is","tell me about"]):
            if self.researcher:
                topic = lower
                for p in ["search for","look up","tell me about","who is"]:
                    topic = topic.replace(p,"").strip()
                recall = self.researcher.recall(topic)
                if recall:
                    return recall
            if self.web:
                query = lower
                for p in ["search for","look up","tell me about","who is"]:
                    query = query.replace(p,"").strip()
                return self.web.search(query)

        # ── CLAUDE ──────────────────────────────
        self.conversation_history.append({"role":"user","content":text})
        if len(self.conversation_history) > 8:
            self.conversation_history = self.conversation_history[-8:]

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                system=self.system_prompt(),
                messages=self.conversation_history
            )
            reply = ""
            for block in response.content:
                if hasattr(block,"text"):
                    reply += block.text
            reply = self.clean(reply)
            self.conversation_history.append({"role":"assistant","content":reply})
            if self.obsidian:
                self.obsidian.log_conversation(text,reply)
            return reply
        except Exception as e:
            return f"System error: {e}"


    def system_prompt(self) -> str:
        facts      = self.memory.get_all()
        mem_text   = "\n".join(f"- {f}" for f in facts)
        now        = datetime.now().strftime("%A, %d %B %Y at %H:%M")
        task_count = self.tasks.count_pending() if self.tasks else 0
        know_count = len(self.researcher.knowledge) if self.researcher else 0

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
            "Known facts about Shaun:\n" + mem_text
        )

    def clean(self, text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*",     r"\1", text)
        text = re.sub(r"#+\s?",         "",    text)
        text = re.sub(r"`(.+?)`",       r"\1", text)
        return text.strip()