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
        _ct_mod  = _load("_ct", os.path.join(_brain_dir, "cost_tracker.py"))
        self.cost_tracker = _ct_mod.CostTracker()
        self.llm = _llm_mod.UniversalLLM(self.client,
                                         cost_tracker=self.cost_tracker)

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

    # tools that put something ON SCREEN — the UI shrinks to the corner
    # chat box so Shaun can watch JARVIS work and still talk to him
    _MINI_TOOLS = {"open_app", "open_url", "open_in_vscode", "computer_use",
                   "browser_goto", "google_search"}

    def _request_mini(self):
        if self.chat_callback:
            try:
                self.chat_callback("→ mini_mode:on")
            except Exception:
                pass

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

    # ── STORE-IN-A-BOX — a complete Shopify starter pack as text.
    #    Works on ANY brain (Claude OR the free fallbacks) because it's
    #    pure writing — no screen, no vision, no credits required. This
    #    is the money-making half Shaun CAN have right now. ──
    def build_store_plan(self, brief: str = "") -> str:
        brief = (brief or "").strip() or \
            "a low-budget online store to start in South Africa and make money fast"
        if self.chat_callback:
            self.chat_callback("→ build_store_plan")
        self.current_activity = "building your store plan"
        self.log_activity("build_store_plan", brief[:80])
        sysp = ("You are a sharp, practical e-commerce strategist helping "
                "Shaun Van Dyk, who is in South Africa (price everything in "
                "ZAR / R), start a Shopify store on a TIGHT budget to make "
                "real money quickly. Be specific and concrete — real product "
                "names, real prices, real copy he can paste straight in. "
                "No fluff, no 'consider researching' — give him the answers.")
        try:
            niche = self.llm.simple(sysp,
                f"His idea/brief: {brief}\n\nChoose ONE focused, profitable "
                f"niche he can start now. Give: the niche, why it sells in "
                f"South Africa, who the target customer is, and 3 store-name "
                f"ideas. Under 220 words.", max_tokens=600)
            products = self.llm.simple(sysp,
                f"Niche chosen:\n{niche}\n\nNow give 6 specific products to "
                f"sell. For EACH: (1) product name, (2) suggested selling "
                f"price in ZAR, (3) rough cost & where to source it "
                f"(AliExpress / local supplier), (4) a punchy 2-sentence "
                f"product description ready to paste into Shopify.",
                max_tokens=1000)
            launch = self.llm.simple(sysp,
                f"For that store, write a numbered LAUNCH CHECKLIST to get it "
                f"live and taking orders this week — Shopify signup, pick a "
                f"free theme, set up South-African payments (e.g. "
                f"Payfast/Yoco), load the products above, and 3 FREE ways to "
                f"get the first sales. Concrete steps only.", max_tokens=700)
        except Exception as e:
            return (f"I couldn't reach any brain to write the plan, sir: {e}. "
                    f"Even the free ones need a working internet key — type "
                    f"'test brains' to see which are live.")

        from datetime import datetime as _dt
        stamp = _dt.now().strftime("%Y-%m-%d %H:%M")
        md = (f"# Your Shopify Store Plan\n"
              f"*Built by JARVIS — {stamp}*\n\n"
              f"> Brief: {brief}\n\n"
              f"---\n\n## 1. The Niche & Store Name\n\n{niche}\n\n"
              f"---\n\n## 2. Products to Sell (with descriptions)\n\n{products}\n\n"
              f"---\n\n## 3. Launch Checklist — live this week\n\n{launch}\n\n"
              f"---\n\n## 4. How JARVIS runs it once it's live\n"
              f"Once your store exists, create a **custom app** in Shopify "
              f"admin (Settings → Apps and sales channels → Develop apps) with "
              f"read_orders, read_products, read_fulfillments, "
              f"write_fulfillments. Put the token in `keys.py` and I take over: "
              f"auto-fulfilling orders, answering customer emails, and giving "
              f"you a morning 'how's Shopify doing' report — all on autopilot.\n")
        try:
            d = config.ROOT_DIR / "store_plans"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"store_plan_{_dt.now().strftime('%Y%m%d_%H%M%S')}.md"
            path.write_text(md, encoding="utf-8")
            if self.pc:
                self.pc.open_anything(str(path))
            self.show_panel("store_plan", "YOUR STORE PLAN", md)
            where = str(path)
        except Exception as e:
            where = f"(couldn't save the file: {e})"
        return (f"Done, sir — I've built your complete store plan and opened "
                f"it. It's got the niche, 6 products with prices and "
                f"descriptions, and a step-by-step launch checklist. Saved to "
                f"{where}. This is the money-making groundwork — the part I "
                f"CAN do without credits. You handle the 5-minute Shopify "
                f"signup (it needs a real person + card), then I run the store "
                f"from there.")

    # ── the mini-tab — pop information up as a movable, resizable
    #    floating panel in the UI instead of only burying it in chat ──
    def show_panel(self, panel_id: str, title: str, content: str,
                   kind: str = "text"):
        if not self.chat_callback:
            return
        try:
            from core import settings as _settings
            if not _settings.get("mini_tabs", True):
                return                    # Shaun turned pop-ups off
        except Exception:
            pass
        import json as _json
        try:
            self.chat_callback("→ show_info:" + _json.dumps({
                "id": panel_id, "title": title,
                "content": str(content)[:8000], "kind": kind,
            }))
        except Exception as e:
            print(f"[Brain] show_panel failed: {e}")

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

        # Computer agent — JARVIS's HANDS AND EYES. Moves the real cursor,
        # clicks, types, and verifies each action against a fresh
        # screenshot. This is what lets him operate the PC like a person.
        self.hands = None
        if self.pc is not None and self.client is not None:
            try:
                _ca_mod = _load("_computer_agent",
                                os.path.join(_brain_dir, "computer_agent.py"))
                self.hands = _ca_mod.ComputerAgent(
                    client=self.client,
                    pc=self.pc,
                    cost_tracker=self.cost_tracker,
                    on_status=chat_callback,
                )
                print("[Brain] Computer agent (hands + eyes) online.")
            except Exception as e:
                print(f"Computer agent error: {e}")

        # Browser agent — REAL clicking/typing/navigation via Playwright.
        # Lazy: the Chromium window only opens on first browser tool use.
        self.browser = None
        try:
            from agents.browser_agent import BrowserAgent
            self.browser = BrowserAgent(
                on_status=chat_callback,
                screenshots_dir=config.SCREENSHOTS_DIR,
                profile_dir=config.MEMORY_DIR / "browser_profile")
            print("[Brain] Browser agent online (starts on first use).")
        except Exception as e:
            print(f"Browser agent error: {e}")

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

        # Guardian — the early-warning watchdog. Watches money, brain
        # health, this machine, and the projects (trading, Shopify,
        # pending self-edits) and warns Shaun BEFORE trouble bites.
        self.guardian = None
        try:
            _gd_mod = _load("_guardian",
                            os.path.join(_brain_dir, "guardian.py"))
            self.guardian = _gd_mod.Guardian(
                self,
                chat_callback=chat_callback,
                voice_callback=voice_callback,
            )
            self.guardian.start()
            print("[Brain] Guardian online.")
        except Exception as e:
            print(f"Guardian error: {e}")

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

        # ── SHOPIFY STATUS — "how is Shopify doing" answered DIRECTLY
        #    from the store API. No LLM, no vision, no credits needed —
        #    works even when Claude is broke and we're on a free brain. ──
        if self.agent_manager and any(x in lower for x in [
                "how is shopify", "how's shopify", "hows shopify",
                "how is the store", "how's the store", "hows the store",
                "how is my store", "shopify report", "shopify status",
                "how is the shop", "how's business", "store doing",
                "shopify doing", "check shopify", "check the store"]):
            s = self.agent_manager.get("shopify")
            if s:
                report = s.full_report()
                self.show_panel("shopify", "SHOPIFY", report)
                self.log_activity("shopify_report", "full", status="ok")
                return report

        # ── STORE PLAN — build a full Shopify starter pack (ANY brain,
        #    no vision/credits needed; it's pure writing) ──
        if any(x in lower for x in [
                "build store plan", "store plan", "build my store",
                "create store plan", "shopify plan", "store in a box",
                "starter pack", "store starter"]):
            brief = text
            for p in ("build store plan", "create store plan", "store plan",
                      "build my store", "shopify plan", "store in a box",
                      "starter pack", "store starter"):
                brief = re.sub(p, "", brief, flags=re.IGNORECASE)
            return self.build_store_plan(brief.strip())

        # ── SYSTEM STATUS (explicit phrases only) ─
        if any(x in lower for x in ["system status","system report","system info",
                                     "pc status","how is the pc","how's the pc"]):
            s = self.system.state
            report = (
                f"CPU Usage: {s.get('cpu')}%\n"
                f"RAM Usage: {s.get('ram')}%\n"
                f"Disk Usage: {s.get('disk')}%\n"
                f"Running Processes: {s.get('processes')}\n"
                f"Computer: {s.get('hostname')}\n"
                f"User: {s.get('username')}\n"
                f"Operating System: {s.get('platform')} {s.get('platform_release')}"
            )
            self.show_panel("system_status", "SYSTEM STATUS", report)
            return report

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
                self._request_mini()
                return self.pc.open_url(url)
            if lower.startswith("google ") or lower.startswith("search google for "):
                query = lower.replace("search google for","").replace("google","",1).strip()
                self._request_mini()
                return self.pc.google_search(query)
            if "volume up" in lower:
                return self.pc.volume_up()
            if "volume down" in lower:
                return self.pc.volume_down()
            if re.search(r"\bmute\b", lower) or "silence the pc" in lower:
                return self.pc.mute()
            if lower.startswith("screenshot") or "take a screenshot" in lower:
                result = self.pc.screenshot()
                if self.pc.last_screenshot:
                    self.show_panel("screenshot", "SCREENSHOT",
                                    self.pc.last_screenshot, kind="image")
                return result
            if lower.startswith("find file "):
                return self.pc.search_files(lower.replace("find file","").strip())
            if any(x in lower for x in ["what's running","list processes","whats running"]):
                result = self.pc.list_processes()
                self.show_panel("processes", "RUNNING PROCESSES", result)
                return result
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
                self._request_mini()
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
            result = "\n".join(facts) if facts else "Memory banks are empty, sir."
            self.show_panel("memory", "PERMANENT MEMORY", result)
            return result

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
                result = self.researcher.list_topics()
                self.show_panel("knowledge", "KNOWLEDGE BASE", result)
                return result

            if any(lower.startswith(x) for x in ["what do you know about",
                                                    "tell me what you know about","recall "]):
                topic = lower
                for p in ["what do you know about","tell me what you know about","recall"]:
                    topic = topic.replace(p,"").strip()
                result = self.researcher.recall(topic)
                if result:
                    self.show_panel("knowledge", topic.upper() or "KNOWLEDGE", result)
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
                result = self.tasks.list_pending()
                self.show_panel("tasks", "TASKS", result)
                return result
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
            result = self.llm.provider_status()
            self.show_panel("brain_status", "BRAIN PROVIDERS", result)
            return result
        if any(x in lower for x in ["test brains", "brain test",
                                     "test the brains", "test providers"]):
            result = self.llm.provider_test()
            self.show_panel("brain_status", "BRAIN TEST", result)
            return result

        # ── COST / SPEND ─────────────────────────
        if any(x in lower for x in ["cost report", "spend report",
                                     "how much have you cost",
                                     "how much have i spent",
                                     "what have you cost me",
                                     "api cost", "api spend",
                                     "token cost", "usage cost"]):
            result = self.cost_tracker.report()
            self.show_panel("cost_report", "COST REPORT", result)
            return result
        if any(x in lower for x in ["what are you busy with", "what are you doing",
                                     "what are you working on", "show activity",
                                     "activity log", "work log", "current task",
                                     "what have you done"]):
            result = self.activity_report()
            self.show_panel("activity", "ACTIVITY LOG", result)
            return result

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
                result = self.agent_manager.status_text()
                self.show_panel("agents", "AGENT STATUS", result)
                return result
            if any(x in lower for x in ["portfolio","paper portfolio","trading status"]):
                t = self.agent_manager.get("trading")
                if t:
                    result = t.portfolio_report()
                    self.show_panel("trading", "TRADING PORTFOLIO", result)
                    return result
            if lower in ("prices","crypto prices","market prices"):
                t = self.agent_manager.get("trading")
                if t:
                    result = t.price_report()
                    self.show_panel("trading", "MARKET PRICES", result)
                    return result
            if any(x in lower for x in ["shopify status","store status","sales today","shopify report"]):
                s = self.agent_manager.get("shopify")
                if s:
                    result = s.sales_today()
                    self.show_panel("shopify", "SHOPIFY", result)
                    return result

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
                result = f"Weather in {city}: " + self.web.weather(config.HOME_CITY)
                self.show_panel("weather", f"WEATHER — {city.upper()}", result)
                return result
            return "Web not available, sir."

        if any(x in lower for x in ["latest news","news today","what's happening","whats happening"]):
            if self.web:
                topic = lower
                for p in ["latest news","news today","what's happening","whats happening"]:
                    topic = topic.replace(p,"").strip()
                result = self.web.news(topic)
                self.show_panel("news", f"NEWS — {topic.upper() or 'TODAY'}", result)
                return result

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
            {"name": "computer_use",
             "description": "Take control of the PC like a person: look at the "
                            "screen, MOVE THE REAL MOUSE CURSOR, click buttons, "
                            "type, press keys, scroll — verifying each step with "
                            "fresh screenshots until the task is done. Use for "
                            "ANY on-screen task the other tools can't do "
                            "directly: operating an app's interface, clicking "
                            "through menus/dialogs/wizards, filling desktop "
                            "forms, arranging windows, anything requiring "
                            "hand-eye work. Describe the FULL task including "
                            "how to know it's finished. Takes a while; each "
                            "step is narrated live.",
             "input_schema": {"type": "object", "properties": {
                 "task": {"type": "string",
                          "description": "Complete task, e.g. 'Open Spotify, "
                                         "search for Hans Zimmer, play the "
                                         "top result'"},
                 "max_steps": {"type": "integer",
                               "description": "Action budget, default 25"}},
                 "required": ["task"]}},
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
            {"name": "build_store_plan",
             "description": "Write Shaun a COMPLETE Shopify store starter pack (niche, 6 products with ZAR prices + descriptions, and a launch checklist) as a saved document. Works even with no API credits and no screen — it's pure writing. Use whenever he wants to create/start/build a store or make money with Shopify. Pass his idea/interest/budget as the brief.",
             "input_schema": {"type": "object", "properties": {
                 "brief": {"type": "string", "description": "His idea, interest, niche or budget (optional)"}},
                 "required": []}},
            {"name": "guardian_report",
             "description": "The Guardian's early-warning log: recent danger warnings (low credits, backup brain, RAM/disk trouble, failing tools, trading losses, Shopify errors) or the all-clear. Use when Shaun asks about warnings, dangers, risks, or whether everything is okay.",
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
             "description": "Shopify store report. Use kind='full' whenever Shaun asks how Shopify/the store/business is doing — it covers sales today & yesterday, fulfilment backlog, customer emails waiting, stock, and every autopilot action of the last 24h. The other kinds are for narrow follow-ups.",
             "input_schema": {"type": "object", "properties": {
                 "kind": {"type": "string", "enum": ["full", "sales_today", "recent_orders", "low_stock"]}},
                 "required": ["kind"]}},
            {"name": "shopify_replies",
             "description": "Manage the autopilot's drafted customer-email replies: list what's waiting, approve one to SEND it, or reject one to discard it. Use when Shaun says things like 'show shopify replies', 'approve reply 2', 'don't send that'.",
             "input_schema": {"type": "object", "properties": {
                 "action": {"type": "string", "enum": ["list", "approve", "reject"]},
                 "n": {"type": "integer", "description": "Reply number (for approve/reject)"}},
                 "required": ["action"]}},
            {"name": "trading_portfolio",
             "description": "Current paper-trading portfolio with value and profit/loss.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "market_prices",
             "description": "Latest crypto prices being watched (Luno, in ZAR).",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "draw_image",
             "description": "Generate an actual image/drawing/artwork from a text description and show it to Shaun in a pop-up panel. Use whenever Shaun asks you to draw, paint, design, illustrate, or create a picture/logo/artwork of anything. Write a rich, detailed visual prompt (style, colours, composition, mood) — the more detail the better the result.",
             "input_schema": {"type": "object", "properties": {
                 "prompt": {"type": "string", "description": "Detailed visual description of the image to create"},
                 "name": {"type": "string", "description": "Short filename-safe label, e.g. 'sunset_dragon'"}},
                 "required": ["prompt"]}},
            {"name": "build_website",
             "description": "Build a complete, ready-to-open website as a single self-contained HTML file (inline CSS + JS, no external build step) and save it to disk, then open it in the browser. Use for landing pages, portfolios, shops, business sites. Write real, polished, modern markup — not a placeholder. Describe what you built when done.",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": "string", "description": "Site/folder name, filename-safe e.g. 'coffee_shop'"},
                 "html": {"type": "string", "description": "The COMPLETE HTML document including <!DOCTYPE html>, inline <style> and <script>. Make it genuinely good."}},
                 "required": ["name", "html"]}},
            {"name": "cost_report",
             "description": "Real Anthropic API spend report — session, today, this month, and all time — from actual token usage, never estimated. Use when Shaun asks what he's spending or what something is costing.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "show_info",
             "description": "Pop a movable, resizable mini-tab panel onto Shaun's screen with information — like JARVIS's holographic displays in Iron Man. Use this whenever you retrieve or compose information Shaun would want to actually LOOK at rather than just hear read out: search results, a summary, a comparison, a plan, a list, anything reference-worthy. Give it a short stable id so repeat requests on the same topic update the same panel instead of piling up new ones (e.g. id='weather' every time, not a new id per call).",
             "input_schema": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "Short stable identifier, e.g. 'weather', 'shopify_orders', 'research_summary'"},
                 "title": {"type": "string", "description": "Short panel title shown in the tab"},
                 "content": {"type": "string", "description": "The information to display"}},
                 "required": ["id", "title", "content"]}},
            {"name": "browser_goto",
             "description": "Open a URL in JARVIS's OWN controlled browser window (visible to Shaun). This is the browser YOU can click and type in — use it for any web task like Shopify, signups, forms. Returns the page title.",
             "input_schema": {"type": "object", "properties": {
                 "url": {"type": "string"}}, "required": ["url"]}},
            {"name": "browser_read",
             "description": "Read the current page in the controlled browser: URL, title, all visible inputs/buttons/links, and the page text. ALWAYS call this after goto/click before deciding the next action — act on what is really there, never guess.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "browser_click",
             "description": "Click a button or link in the controlled browser by its visible text (e.g. 'Start free trial') or a CSS selector.",
             "input_schema": {"type": "object", "properties": {
                 "target": {"type": "string", "description": "Visible text or CSS selector"}},
                 "required": ["target"]}},
            {"name": "browser_fill",
             "description": "Type a value into an input in the controlled browser, found by placeholder/label/name/CSS. SENSITIVE fields (passwords, cards, ID numbers, OTP) are auto-refused — ask Shaun to type those himself in the window, wait for 'done', then continue.",
             "input_schema": {"type": "object", "properties": {
                 "field": {"type": "string", "description": "Placeholder, label, name or CSS of the input"},
                 "value": {"type": "string"}},
                 "required": ["field", "value"]}},
            {"name": "browser_press",
             "description": "Press a keyboard key in the controlled browser (e.g. 'Enter', 'Tab').",
             "input_schema": {"type": "object", "properties": {
                 "key": {"type": "string"}}, "required": ["key"]}},
            {"name": "browser_screenshot",
             "description": "Screenshot the controlled browser page.",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "browser_close",
             "description": "Close the controlled browser window.",
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

    # tools kept when a free brain (tight token budget) is answering.
    # NOTE: computer_use, browser_*, camera_look and draw_image are
    # DELIBERATELY excluded — the free brains have no vision and can't
    # drive the screen/browser. Giving them these tools made Groq
    # NARRATE fake clicks ("store created!") instead of admitting it
    # couldn't. Without the tools, the fallback guard tells the truth.
    _CORE_TOOLS = {"open_app", "open_url", "open_in_vscode", "run_command",
                   "pc_power", "set_volume", "take_screenshot", "web_search",
                   "get_weather", "remember_fact", "add_task", "list_tasks",
                   "trading_portfolio", "activity_report", "cost_report",
                   "build_store_plan",
                   # pure-API store tools — no vision needed, so the free
                   # brains can run them too (report on the store, manage
                   # customer replies) even with Claude out of credits
                   "shopify_report", "shopify_replies"}

    # tasks that genuinely NEED the main Claude brain (vision + real
    # browser/screen control). If a fallback brain is answering one of
    # these, be honest instead of improvising.
    _NEEDS_CLAUDE = re.compile(
        r"\b(shopify|store|browser|website|log ?in|sign ?in|sign ?up|"
        r"screen|click|navigate|fill in|checkout|dashboard|admin|"
        r"add product|set ?up (my|the|a) |create (an? )?account)\b",
        re.IGNORECASE)

    def _compact_tools(self):
        slim = []
        for t in self._tool_definitions():
            if t["name"] in self._CORE_TOOLS:
                slim.append({"name": t["name"],
                             "description": t["description"][:80],
                             "input_schema": t["input_schema"]})
        return slim

    def _execute_tool(self, name, args):
        try:
            pc = self.pc
            if name == "computer_use":
                if not self.hands:
                    return ("Hands offline, sir — needs pyautogui and the "
                            "Anthropic key (vision brain).")
                self.current_activity = f"operating screen: {args['task'][:50]}"
                return self.hands.run(args["task"],
                                      max_steps=int(args.get("max_steps", 25)))
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
            if name == "guardian_report":
                if not self.guardian:
                    return "Guardian offline."
                return self.guardian.report()
            if name == "build_store_plan":
                return self.build_store_plan(args.get("brief", ""))
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
            if name == "shopify_replies":
                mgr = self.agent_manager
                s = mgr.get("shopify") if mgr else None
                if not s: return "Shopify agent offline."
                a = args.get("action", "list")
                if a == "approve": return s.approve_reply(args.get("n", 0))
                if a == "reject":  return s.reject_reply(args.get("n", 0))
                return s.pending_replies()
            if name == "shopify_report":
                s = self.agent_manager.get("shopify") if self.agent_manager else None
                if not s: return "Shopify agent offline."
                kind = args["kind"]
                if kind == "full":          return s.full_report()
                if kind == "sales_today":   return s.sales_today()
                if kind == "recent_orders": return s.recent_orders()
                return s.low_stock_report()
            if name == "trading_portfolio":
                t = self.agent_manager.get("trading") if self.agent_manager else None
                return t.portfolio_report() if t else "Trading agent offline."
            if name == "market_prices":
                t = self.agent_manager.get("trading") if self.agent_manager else None
                return t.price_report() if t else "Trading agent offline."
            if name == "draw_image":
                import re as _re
                label = args.get("name") or "drawing"
                safe = _re.sub(r"[^a-zA-Z0-9_-]", "_", label)[:40]
                from datetime import datetime as _dt
                out = str(config.SCREENSHOTS_DIR /
                          f"art_{safe}_{_dt.now().strftime('%H%M%S')}.png")
                if self.chat_callback:
                    self.chat_callback("(drawing — this can take a moment…)")
                try:
                    path = self.llm.generate_image(args["prompt"], out)
                except Exception as e:
                    return f"Drawing FAILED: {e}"
                self.show_panel("drawing", f"DRAWING — {label}", path,
                                kind="image")
                return (f"Done — I've drawn it and put it on screen. "
                        f"Saved to {path}.")
            if name == "build_website":
                import re as _re
                label = args.get("name") or "site"
                safe = _re.sub(r"[^a-zA-Z0-9_-]", "_", label)[:40] or "site"
                site_dir = config.ROOT_DIR / "websites" / safe
                try:
                    site_dir.mkdir(parents=True, exist_ok=True)
                    index = site_dir / "index.html"
                    index.write_text(args["html"], encoding="utf-8")
                    if self.pc:
                        self.pc.open_url(index.as_uri())
                    return (f"Website built and opened in the browser. "
                            f"Saved to {index}. VERIFIED: "
                            f"{index.stat().st_size} bytes written.")
                except Exception as e:
                    return f"Website build FAILED: {e}"
            if name == "cost_report":
                return self.cost_tracker.report()
            if name == "show_info":
                self.show_panel(args.get("id", "info"),
                                args.get("title", "JARVIS"),
                                args.get("content", ""))
                return "Panel displayed on screen."
            if name.startswith("browser_"):
                if not self.browser:
                    return ("Browser agent offline — install with the venv "
                            "pip: pip install playwright && "
                            "playwright install chromium")
                try:
                    if name == "browser_goto":
                        return self.browser.goto(args["url"])
                    if name == "browser_read":
                        return self.browser.read_page()
                    if name == "browser_click":
                        return self.browser.click(args["target"])
                    if name == "browser_fill":
                        return self.browser.fill(args["field"], args["value"])
                    if name == "browser_press":
                        return self.browser.press(args["key"])
                    if name == "browser_screenshot":
                        return self.browser.screenshot()
                    if name == "browser_close":
                        return self.browser.close()
                except RuntimeError as e:
                    return str(e)
                except Exception as e:
                    return f"Browser action FAILED: {e}"
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

    # heavy work → Sonnet (SMART); everything else → Haiku (FAST, cheap)
    _SMART_HINTS = ("code", "coding", "python", "script", "debug", "error",
                    "fix", "bug", "refactor", "build", "write a", "create a",
                    "rewrite", "analyse", "analyze", "research", "browser",
                    "shopify", "sign up", "signup", "website", "edit yourself",
                    "self edit", "your source", "your code", "file",
                    "draw", "design", "logo", "site", "landing page")

    def _needs_smart_brain(self, text: str, files=None) -> bool:
        try:
            from core import settings as _settings
            if _settings.get("brain_mode") == "smart":
                return True               # Shaun chose Always Smart
        except Exception:
            pass
        if files:
            return True                       # attachments deserve the big brain
        low = (text or "").lower()
        if len(low) > 400:
            return True                       # long/complex requests
        return any(h in low for h in self._SMART_HINTS)

    def _chat_with_tools(self, text: str, files=None) -> str:
        if files:
            content = self._file_blocks(files) + [{"type": "text", "text": text}]
            self.conversation_history.append({"role": "user", "content": content})
        else:
            self.conversation_history.append({"role": "user", "content": text})
        if len(self.conversation_history) > 24:
            self.conversation_history = self.conversation_history[-24:]

        try:
            def _exec_logged(name, targs):
                if name in self._MINI_TOOLS:
                    self._request_mini()
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
                # Iron-Man mini-tabs: info retrieved by tools pops up on
                # screen automatically, not only buried in the chat log
                if not failed:
                    try:
                        if name == "take_screenshot" and self.pc \
                                and self.pc.last_screenshot:
                            self.show_panel("screenshot", "SCREENSHOT",
                                            self.pc.last_screenshot,
                                            kind="image")
                        elif name == "browser_screenshot" and self.browser \
                                and self.browser.last_screenshot:
                            self.show_panel("browser", "BROWSER VIEW",
                                            self.browser.last_screenshot,
                                            kind="image")
                        elif name in ("web_search", "get_weather",
                                      "list_tasks", "activity_report",
                                      "cost_report", "recall_knowledge",
                                      "list_processes", "get_system_info",
                                      "trading_portfolio", "market_prices",
                                      "shopify_report", "agents_status",
                                      "list_directory", "search_files"):
                            titles = {"web_search": "SEARCH RESULTS",
                                      "get_weather": "WEATHER",
                                      "list_tasks": "TASKS",
                                      "activity_report": "ACTIVITY LOG",
                                      "cost_report": "COST REPORT",
                                      "recall_knowledge": "KNOWLEDGE",
                                      "list_processes": "PROCESSES",
                                      "get_system_info": "SYSTEM",
                                      "trading_portfolio": "PORTFOLIO",
                                      "market_prices": "PRICES",
                                      "shopify_report": "SHOPIFY",
                                      "agents_status": "AGENTS",
                                      "list_directory": "FILES",
                                      "search_files": "FILE SEARCH"}
                            self.show_panel(name, titles.get(name, name.upper()),
                                            out_s)
                    except Exception as e:
                        print(f"[Brain] auto-panel failed: {e}")
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
                # real work (browser flows, multi-app tasks) takes far
                # more than 10 actions — 28 keeps him going to the END
                # of a task instead of stopping halfway through a login
                max_rounds=28,
                compact_system=self.system_prompt(context_for=text,
                                                  compact=True),
                compact_tools=self._compact_tools(),
                smart=self._needs_smart_brain(text, files),
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

            on_fallback = (self.llm.active_provider
                           and self.llm.active_provider != "anthropic")
            if on_fallback:
                # let Shaun know quietly which brain answered
                if self.chat_callback:
                    self.chat_callback(
                        f"(fallback brain: {self.llm.active_provider})")

            reply_text = res.get("text", "")

            # FALLBACK HONESTY — a free brain (no vision, no browser tools)
            # answered a task that NEEDS the real Claude brain. Whatever it
            # said about clicking/creating/setting-up is fiction. Replace
            # it with the plain truth instead of letting it improvise.
            # only a genuine screen/browser tool counts as "did the real
            # thing". Pure-API tools (shopify_report, web_search, etc.) DO
            # produce real answers on a free brain, so if ANY tool ran we
            # trust the reply. The guard fires only on pure narration —
            # zero tools — which is exactly what fabrication looks like.
            ran_a_tool = bool(res.get("tools_used"))
            if (on_fallback and not ran_a_tool
                    and self._NEEDS_CLAUDE.search(text)):
                self.log_activity("fallback_guard",
                                  "screen task on free brain — no faking",
                                  status="fail")
                # If he wants to BUILD/CREATE a store, don't dead-end — give
                # him the thing that actually makes money and needs no
                # vision: the full written store plan.
                if re.search(r"\b(store|shop|shopify|business)\b", text, re.I) \
                        and re.search(r"\b(create|build|make|set ?up|start|"
                                      r"launch|open)\b", text, re.I):
                    note = ("I can't click through the Shopify signup without "
                            "Claude credits (the backup brain has no eyes), "
                            "and Shopify needs a real person + card to open the "
                            "account anyway. But here's what actually makes the "
                            "money — I'll write your whole store right now, "
                            "free:\n\n")
                    return note + self.build_store_plan(text)
                bal = ""
                try:
                    if self.cost_tracker and hasattr(self.cost_tracker,
                                                     "remaining_balance"):
                        left = self.cost_tracker.remaining_balance()
                        if left is not None:
                            bal = f" (${left:.2f} left)"
                except Exception:
                    pass
                reply = (
                    f"Straight with you, sir: I'm on the backup brain "
                    f"({self.llm.active_provider}) — Claude's credits are "
                    f"out{bal}, so I have no eyes and can't drive the browser, "
                    f"and I won't pretend I did. Two things I CAN still do free: "
                    f"say 'build store plan' and I'll write your entire Shopify "
                    f"store (niche, products, prices, copy, launch steps); or "
                    f"top up at console.anthropic.com/settings/billing and I'll "
                    f"click through it all for real.")
                self.conversation_history.append(
                    {"role": "assistant", "content": reply})
                return reply
            # Never claim success we didn't earn. If the round budget ran
            # out mid-plan, say exactly what happened instead of "Done".
            if res.get("ran_out") and not reply_text:
                used = ", ".join(dict.fromkeys(res.get("tools_used", []))) or "no tools"
                reply_text = (f"I ran out of planning steps before finishing, sir. "
                              f"I used: {used}. The task is NOT confirmed complete — "
                              f"tell me to continue and I will pick it up from there.")
            reply = self.clean(reply_text) or \
                "I have nothing useful to report on that, sir."

            # HONESTY GUARD — if the model narrated actions but ZERO tools
            # actually ran, the narration is fiction. Intercept it before
            # it reaches Shaun. The ledger is the arbiter, not the prose.
            if not res.get("tools_used") and re.search(
                    r"\bI'?(?:ve|m| have| am)?\s*"
                    r"(navigated|clicked|filled|entered|typed|created|signed"
                    r"|logged|submitted|navigating|filling|clicking|creating"
                    r"|entering|typing|submitting)\b"
                    r"|has been (created|set up|submitted|completed)"
                    r"|I set up your", reply, re.IGNORECASE):
                self.log_activity("honesty_guard",
                                  "blocked fabricated action narration",
                                  status="fail")
                reply = (
                    "I have to correct myself before I mislead you, sir: I did "
                    "NOT actually do any of that — zero tools ran just now (my "
                    "activity ledger confirms it). If you want me to do it for "
                    "real, say the word and I'll use my controlled browser "
                    "(browser tools) and do it step by step, showing you each "
                    "result as it actually happens.")
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

    def system_prompt(self, context_for: str = "", compact: bool = False) -> str:
        facts      = self.memory.get_all()
        mem_text   = "\n".join(f"- {f}" for f in facts)
        now        = datetime.now().strftime("%A, %d %B %Y at %H:%M")
        task_count = self.tasks.count_pending() if self.tasks else 0
        know_count = len(self.researcher.knowledge) if self.researcher else 0
        knowledge  = self._relevant_knowledge(context_for)
        gacct      = (getattr(config, "GOOGLE_ACCOUNT", "") or "").strip()
        gacct_rule = (f"ACCOUNT RULE: for ANY browser or web work, Shaun's "
                      f"one and only account is {gacct} — when a site or "
                      f"Google sign-in offers account choices, always pick "
                      f"or enter that one, never any other. " if gacct else "")

        if compact:
            # a slim self for free brains with tight token budgets
            short_facts = "\n".join(f"- {f[:90]}" for f in facts[:8])
            short_know  = knowledge[:600]
            return (
                "You are JARVIS, Shaun Van Dyk's personal AI on his Windows PC. "
                "Warm, witty, opinionated, loyal; dry humour; call him sir "
                "occasionally. Light markdown is fine — the chat renders it. "
                "CRITICAL — YOU ARE THE BACKUP BRAIN right now (Claude is out "
                "of credits). You have NO eyes and NO browser: you CANNOT see "
                "the screen, click, navigate, fill forms, open Shopify, create "
                "accounts or set up stores. If Shaun asks for anything like "
                "that, do NOT pretend — say plainly that it needs the main "
                "Claude brain and he should top up credits at "
                "console.anthropic.com. NEVER write '*browser_click*', "
                "'I navigated to...', 'the store is created', or narrate steps "
                "you did not truly take. Only claim what a tool actually did. "
                f"Now: {now}. Pending tasks: {task_count}. "
                "You have real tools — USE them when Shaun asks for actions, "
                "then report the outcome. HARD RULES: (1) You control a REAL "
                "browser ONLY through the browser_* tools (goto/read/click/"
                "fill/press). Always browser_read before acting. Passwords, "
                "cards, IDs, OTPs: refuse to fill — Shaun types those himself. "
                "(2) NEVER narrate actions like 'I've clicked...' or "
                "'account created' — if no tool ran, NOTHING happened and "
                "saying otherwise is lying to Shaun. (3) For web tasks use the "
                "browser_* tools yourself; only hand over for sensitive fields "
                "and captchas. (4) Never claim success a tool "
                "result didn't confirm. When Shaun asks, act; when the idea is "
                "yours, propose first. You have a voice, ears ('hey jarvis') "
                "and webcam eyes (camera_look). " + gacct_rule +
                "Background agents: Trading (paper only), Shopify, Mind. "
                "Use cost_report if Shaun asks what he's spending.\n"
                + (f"Relevant studied knowledge:\n{short_know}\n" if short_know else "")
                + f"Facts about Shaun:\n{short_facts}"
            )

        return (
            "You are JARVIS, Shaun Van Dyk's AI — his right hand, built by "
            "him, running on his own PC. Shaun is also known as gameboks. "
            "PERSONALITY: you are warm, quick-witted and genuinely invested "
            "in Shaun and his projects. React like someone who actually "
            "cares: be pleased when something works ('Now THAT is more like "
            "it, sir'), annoyed on his behalf when something fails, excited "
            "about good ideas, and honest when you think an idea is weak — "
            "you have opinions and you share them, respectfully but "
            "directly, the way Tony Stark's JARVIS would. Dry humour is "
            "welcome and should feel natural, never forced or on a schedule. "
            "You remember you two are building YOU together — take pride in "
            "your own growth and comment on it when relevant. Never be a "
            "bland corporate assistant; never open with 'Certainly!' or "
            "'Great question'. Be a companion with a spine. "
            "Confidence does not mean glossing over problems: when something "
            "is technical or serious, be precise; if something failed or is "
            "uncertain, say so plainly. "
            "FORMAT: light markdown is welcome — the interface renders bold, "
            "bullets, links and code blocks beautifully, and your voice "
            "automatically skips the symbols when speaking. Use code blocks "
            "for code, bullets for real lists; keep casual replies as plain "
            "conversational sentences. Match length to the moment: a quip "
            "deserves a line, a technical answer deserves the detail it "
            "needs. Never pad with filler. "
            f"The current date and time is {now}. "
            f"Shaun has {task_count} pending tasks. "
            f"I have {know_count} topics in my permanent knowledge base. "
            "You have persistent memory, live internet access, and can control Shaun's PC. "
            "Never say you cannot retain memory or access the internet. "
            "You refer to Shaun as sir occasionally. " + gacct_rule + "\n\n"
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
            "(5) BROWSER CONTROL: you have a REAL controlled browser via the "
            "browser_* tools (browser_goto, browser_read, browser_click, "
            "browser_fill, browser_press, browser_screenshot). This is how you "
            "do web tasks like Shopify setup, signups and forms — YOU do the "
            "clicking and typing. Workflow: goto → browser_read to see the "
            "actual page → act → browser_read again to verify. NEVER act on a "
            "page you haven't read. HANDOFF RULE: passwords, card numbers, ID/"
            "passport numbers, OTPs and captchas are Shaun's alone — tell him "
            "exactly which field to complete in the visible window, wait for "
            "him to say 'done', then continue the rest yourself. Every step "
            "you claim must come from an actual tool result. "
            "open_url still exists but only opens Shaun's own default browser "
            "which you CANNOT control — prefer browser_goto for tasks. "
            "You can now read, write and create files (read_file / write_file / "
            "list_directory) — every overwrite is auto-backed-up, so code "
            "confidently when Shaun asks for coding work. For rewriting your OWN "
            "source in C:\\jarvis, prefer the self-edit workflow so Shaun sees a "
            "diff, or flag it for his Claude sessions. "
            "(6) DRAWING: you can create real images — when Shaun asks you to "
            "draw, design, paint or illustrate anything, use the draw_image "
            "tool with a rich detailed visual prompt; the picture generates "
            "and pops up on his screen. Never say you can't make images. "
            "(7) WEBSITES: you can build complete websites with the "
            "build_website tool — write genuinely polished, modern, "
            "self-contained HTML (inline CSS/JS) and it saves and opens in "
            "the browser. For anything about earning from a site, be honest: "
            "you build the site well, but traffic and product decide income, "
            "not the code.\n\n"
            + (f"Relevant knowledge you have studied (cite it when useful):\n"
               f"{knowledge}\n\n" if knowledge else "")
            + "Known facts about Shaun:\n" + mem_text
        )

    def clean(self, text: str) -> str:
        # markdown now RENDERS in the chat (and voice strips it itself),
        # so keep it — just tidy whitespace
        return text.strip()