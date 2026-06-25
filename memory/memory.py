import json
import os


class MemoryStore:

    def __init__(self):

        self.memory_file = os.path.join(
            os.path.dirname(__file__),
            "jarvis_memory.json"
        )

        self.long_term = self.load()


    def load(self):

        if os.path.exists(self.memory_file):

            with open(
                self.memory_file,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        return {
            "facts": []
        }


    def save(self):

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


    def remember(self, fact):

        if fact not in self.long_term["facts"]:

            self.long_term["facts"].append(fact)

            self.save()


    def forget(self, fact):

        self.long_term["facts"] = [

            x

            for x in self.long_term["facts"]

            if fact.lower() not in x.lower()

        ]

        self.save()


    def get_all(self):

        return self.long_term["facts"]