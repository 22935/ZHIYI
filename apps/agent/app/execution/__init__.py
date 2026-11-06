"""Public wiring exports; importing a leaf module must not load the whole runtime."""

from importlib import import_module

__all__ = [
    "RegisteredPlannerLLM",
    "bind_registered_planner_llm",
    "build_default_runtime",
    "build_model_setup",
    "close_runtime",
    "configure_runtime",
    "RunExecutionCoordinator",
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    module = 'coordinator' if name == 'RunExecutionCoordinator' else 'runtime'
    value = getattr(import_module(f'{__name__}.{module}'), name)
    globals()[name] = value
    return value
