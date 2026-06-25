"""
agent.py
────────
JARVIS autonomous agent — thinks and acts without being asked.
Location: C:\jarvis_v18\brain\agent.py

JARVIS proactively:
- Monitors time and triggers morning/evening briefings
- Watches pending tasks and reminds Shaun
- Checks weather in the morning
- Summarises the day at night
- Learns patterns from conversations
"""

import threading
import time
from datetime import datetime


class JarvisAgent:

    def __init__(self, brain, voice_callback=None, chat_callback=None):
        self.brain          = brain
        self.voice_callback = voice_callback
        self.chat_callback  = chat_callback
        self.running        = False
        self._last_hour     = -1
        self._greeted_today = False
        self._evening_done  = False
        print("[Agent] Autonomous agent online.")

    def start(self):
        self.running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    def _say(self, text: str):
        """Speak and show in chat."""
        if self.chat_callback:
            self.chat_callback(f"JARVIS: {text}")
        if self.voice_callback:
            self.voice_callback(text)

    def _loop(self):
        while self.running:
            try:
                now  = datetime.now()
                hour = now.hour

                # Reset daily flags at midnight
                if hour == 0:
                    self._greeted_today = False
                    self._evening_done  = False

                # Morning briefing — 7am
                if hour == 7 and not self._greeted_today:
                    self._morning_briefing()
                    self._greeted_today = True

                # Midday check — 12pm
                if hour == 12 and self._last_hour != 12:
                    self._midday_check()

                # Evening summary — 6pm
                if hour == 18 and not self._evening_done:
                    self._evening_summary()
                    self._evening_done = True

                self._last_hour = hour

            except Exception as e:
                print(f"[Agent] Loop error: {e}")

            time.sleep(60)  # Check every minute

    def _morning_briefing(self):
        now   = datetime.now()
        day   = now.strftime("%A, %d %B")

        lines = [f"Good morning, sir. Today is {day}."]

        # Pending tasks
        if hasattr(self.brain, "tasks") and self.brain.tasks:
            count = self.brain.tasks.count_pending()
            if count > 0:
                lines.append(f"You have {count} pending tasks.")

        # Weather
        if hasattr(self.brain, "web") and self.brain.web:
            try:
                weather = self.brain.web.weather("Benoni, South Africa")
                short   = weather[:120]
                lines.append(f"Weather in Benoni: {short}")
            except Exception:
                pass

        self._say(" ".join(lines))

    def _midday_check(self):
        if hasattr(self.brain, "tasks") and self.brain.tasks:
            count = self.brain.tasks.count_pending()
            if count > 0:
                self._say(
                    f"Midday check, sir. You still have {count} pending tasks. "
                    f"Say 'show tasks' to review them."
                )

    def _evening_summary(self):
        lines = ["Good evening, sir."]

        if hasattr(self.brain, "tasks") and self.brain.tasks:
            count = self.brain.tasks.count_pending()
            if count > 0:
                lines.append(
                    f"You have {count} tasks still pending. "
                    "Would you like to review them?"
                )
            else:
                lines.append("All tasks are complete. Well done today.")

        lines.append("Is there anything you need before you wrap up?")
        self._say(" ".join(lines))

    def proactive_reminder(self, message: str):
        """Can be called externally to trigger a proactive message."""
        self._say(message)