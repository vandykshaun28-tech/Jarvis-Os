import json
import os
from datetime import datetime


class MemoryStore:

    def __init__(self):

        self.memory_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "memory",
            "jarvis_memory.json"
        )

        os.makedirs(
            os.path.dirname(self.memory_file),
            exist_ok=True
        )

        self.long_term = self.load()

        self.seed_defaults()


    def load(self):

        if os.path.exists(self.memory_file):

            with open(
                self.memory_file,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        return {
            "owner": "Shaun",
            "facts": [],
            "preferences": {},
            "projects": {},
            "tasks": [],
            "notes": [],
            "people": {},
            "last_session": None
        }


    def save(self):

        self.long_term["last_session"] = (
            datetime.now().isoformat()
        )

        with open(
            self.memory_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.long_term,
                f,
                indent=4
            )


    def seed_defaults(self):

        defaults = [

            "My name is Shaun Van Dyk",

            "I live in South Africa",

            "My favourite colour is blue",

            "My wife is T.A. van Dyk",

            "My wife writes dark romance novels",

            "The Nightingale Trilogy is written by T.A. van Dyk"

        ]

        changed = False

        for fact in defaults:

            if fact not in self.long_term["facts"]:

                self.long_term["facts"].append(
                    fact
                )

                changed = True

        if changed:

            self.save()


    def remember(self, fact):

        if fact not in self.long_term["facts"]:

            self.long_term["facts"].append(
                fact
            )

            self.save()


    def forget(self, fact):

        self.long_term["facts"] = [

            f

            for f in self.long_term["facts"]

            if fact.lower() not in f.lower()

        ]

        self.save()


    def get_all(self):

        return self.long_term["facts"]