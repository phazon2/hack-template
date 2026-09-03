"""ideate — hackathon ideation system (hybrid RAG + multi-agent + LLM-judge panel + memory)."""

__version__ = "0.1.0"

__all__ = ["__version__", "IdeationSystem"]


def __getattr__(name: str):
    # Lazy so `import ideate.models` never pulls the whole tree.
    if name == "IdeationSystem":
        from ideate.pipeline import IdeationSystem

        return IdeationSystem
    raise AttributeError(name)
