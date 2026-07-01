import subprocess


def open_notepad():
    subprocess.Popen("notepad.exe")

    return {
        "application": "Notepad"
    }


def open_calculator():
    subprocess.Popen("calc.exe")

    return {
        "application": "Calculator"
    }