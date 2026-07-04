from bridge.executor import Executor

executor = Executor()


def register(command_name, function):
    executor.register(command_name, function)


def execute(command_name, *args, **kwargs):
    return executor.execute(command_name, *args, **kwargs)