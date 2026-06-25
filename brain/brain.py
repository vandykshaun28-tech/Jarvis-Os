import re
import os
from datetime import datetime

from anthropic import Anthropic
from memory.memory import MemoryStore

try:
    from memory.obsidian_memory import ObsidianBridge
    OBSIDIAN_OK = True
except Exception:
    OBSIDIAN_OK = False

try:
    from web_search import WebSearch
    WEB_OK = True
except Exception:
    WEB_OK = False

try:
    from task_manager import TaskManager
    TASKS_OK = True
except Exception as e:
    print(f"[Brain] Task manager not loaded: {e}")
    TASKS_OK = False

try:
    from agent import JarvisAgent
    AGENT_OK = True
except Exception as e:
    print(f"[Brain] Agent not loaded: {e}")
    AGENT_OK = False


VAULT_PATH = r"C:\Users\gameboks\OneDrive\Documents\JARVIS_CORE"


class JarvisBrain:

    def __init__(self, voice_callback=None, chat_callback=None):
        self.memory = MemoryStore()
        self.client = Anthropic()
        self.conversation_history = []
        self.voice_callback = voice_callback
        self.chat_callback  = chat_callback

        # Obsidian
        self.obsidian = None
        if OBSIDIAN_OK:
            try:
                self.obsidian = ObsidianBridge(VAULT_PATH)
            except Exception as e:
                print(f"Obsidian init error: {e}")

        # Web search
        self.web = None
        if WEB_OK:
            try:
                self.web = WebSearch()
            except Exception as e:
                print(f"Web init error: {e}")

        # Task manager
        self.tasks = None
        if TASKS_OK:
            try:
                self.tasks = TaskManager(
                    voice_callback=voice_callback,
                    chat_callback=chat_callback
                )
            except Exception as e:
                print(f"Tasks init error: {e}")

        # Autonomous agent
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
                print(f"Agent init error: {e}")


    def process(self, raw_text: str) -> str:
        text  = raw_text.strip()
        if not text:
            return "I did not catch that, sir."
        lower = text.lower()


        # ── TIME & DATE ─────────────────────────
        if any(x in lower for x in ["what time", "whats the time", "what's the time"]):
            return "The time is " + datetime.now().strftime("%H:%M") + ", sir."

        if any(x in lower for x in ["what day", "what date", "what's today"]):
            return "Today is " + datetime.now().strftime("%A, %d %B %Y") + ", sir."


        # ── APPS ────────────────────────────────
        if "calculator" in lower:
            os.system("calc"); return "Opening Calculator, sir."
        if "notepad" in lower:
            os.system("notepad"); return "Opening Notepad, sir."
        if "chrome" in lower and "open" in lower:
            os.system("start chrome"); return "Opening Chrome, sir."
        if "obsidian" in lower and "open" in lower:
            os.system("start obsidian://open"); return "Opening Obsidian, sir."
        if "spotify" in lower and "open" in lower:
            os.system("start spotify"); return "Opening Spotify, sir."
        if "file explorer" in lower or "explorer" in lower and "open" in lower:
            os.system("explorer"); return "Opening File Explorer, sir."


        # ── MEMORY ──────────────────────────────
        if lower.startswith("remember "):
            fact = text[9:].strip()
            self.memory.remember(fact)
            if self.obsidian:
                self.obsidian.remember(fact)
            return "Understood, sir. I shall remember that."

        if lower.startswith("forget "):
            fact = text[7:].strip()
            self.memory.forget(fact)
            return "Consider it forgotten, sir."

        if any(x in lower for x in ["show memories", "what do you remember", "show facts"]):
            facts = self.memory.get_all()
            if not facts:
                return "My memory banks are currently empty, sir."
            return "\n".join(facts)


        # ── TASKS ───────────────────────────────
        if self.tasks:
            if lower.startswith("add task "):
                task = text[9:].strip()
                result = self.tasks.add(task)
                if self.obsidian:
                    self.obsidian.add_task(task)
                return result

            if lower.startswith("complete task ") or lower.startswith("done with "):
                task = text.replace("complete task", "").replace("done with", "").strip()
                return self.tasks.complete(task)

            if lower.startswith("delete task "):
                task = text[12:].strip()
                return self.tasks.delete(task)

            if any(x in lower for x in ["show tasks", "my tasks", "what are my tasks", "list tasks"]):
                return self.tasks.list_pending()

            if lower.startswith("remind me in "):
                # "remind me in 30 minutes to call John"
                try:
                    parts   = text[13:].split(" ", 2)
                    minutes = int(parts[0])
                    message = parts[2] if len(parts) > 2 else "reminder"
                    return self.tasks.remind_in(minutes, message)
                except Exception:
                    return "Please say 'remind me in X minutes to do something', sir."

            if lower.startswith("remind me at "):
                # "remind me at 14:30 to take medication"
                try:
                    parts   = text[13:].split(" ", 2)
                    time_s  = parts[0]
                    message = parts[2] if len(parts) > 2 else "reminder"
                    return self.tasks.remind_at(time_s, message)
                except Exception:
                    return "Please say 'remind me at HH:MM to do something', sir."


        # ── OBSIDIAN ────────────────────────────
        if any(x in lower for x in ["vault status", "obsidian status"]):
            if self.obsidian:
                s = self.obsidian.status()
                return (
                    f"Vault connected. "
                    f"Memory files: {s.get('memory_files', 0)}. "
                    f"Active tasks: {s.get('active_tasks', 0)}."
                )
            return "Obsidian is not connected, sir."


        # ── WEB SEARCH ──────────────────────────
        if "weather" in lower:
            if self.web:
                result = self.web.weather("Benoni, South Africa")
                return f"Current weather in Benoni: {result}"
            return "Web search not available, sir."

        if any(x in lower for x in ["latest news", "news today", "what's happening", "whats happening"]):
            if self.web:
                topic = lower.replace("latest news", "").replace("news today", "").replace("what's happening", "").replace("whats happening", "").strip()
                return self.web.news(topic)
            return "Web search not available, sir."

        if any(x in lower for x in ["search for", "look up", "search the web", "find information about", "who is", "when did", "what is"]):
            if self.web:
                query = lower
                for phrase in ["search for", "search the web for", "look up",
                               "find information about", "tell me about",
                               "what is", "who is", "when did"]:
                    query = query.replace(phrase, "").strip()
                return self.web.search(query)
            return "Web search not available, sir."


        # ── CLAUDE ──────────────────────────────
        self.conversation_history.append({"role": "user", "content": text})
        if len(self.conversation_history) > 8:
            self.conversation_history = self.conversation_history[-8:]

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=150,
                system=self.system_prompt(),
                messages=self.conversation_history
            )
            reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    reply += block.text
            reply = self.clean(reply)

            self.conversation_history.append({"role": "assistant", "content": reply})

            if self.obsidian:
                self.obsidian.log_conversation(text, reply)

            return reply

        except Exception as e:
            return f"System error: {e}"


    def system_prompt(self) -> str:
        facts       = self.memory.get_all()
        memory_text = "\n".join(f"- {f}" for f in facts)
        now         = datetime.now().strftime("%A, %d %B %Y at %H:%M")
        task_count  = self.tasks.count_pending() if self.tasks else 0

        return (
            "You are JARVIS, a highly intelligent AI assistant "
            "created for Shaun Van Dyk, also known as gameboks. "
            "You are loyal, capable, calm, slightly witty and helpful. "
            "Avoid markdown symbols. "
            "Keep all responses under 2 sentences. Be concise and direct. "
            f"The current date and time is {now}. "
            f"Shaun currently has {task_count} pending tasks. "
            "You always know the time and date. "
            "You refer to Shaun as 'sir' occasionally.\n\n"
            "Known facts about Shaun:\n" + memory_text
        )


    def clean(self, text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*",     r"\1", text)
        text = re.sub(r"#+\s?",         "",    text)
        text = re.sub(r"`(.+?)`",       r"\1", text)
        return text.strip()