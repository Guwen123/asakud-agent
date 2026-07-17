from langchain_core.tools import tool


_fetch_web_agent = None


def _get_fetch_web_agent():
    global _fetch_web_agent
    if _fetch_web_agent is None:
        from .client import FetchWebAgent

        _fetch_web_agent = FetchWebAgent()
    return _fetch_web_agent


@tool
def fetch_web(query):
    """Search the web through a focused child agent and return a concise answer."""

    return _get_fetch_web_agent().run(query)
