"""Scout tools — the only components that touch the public internet.

Per the blueprint's security model, the LLM "Brains" are air-gapped. These
tools run in the orchestrator ("Hands") container, fetch real-world data, and
hand clean text back to the model as context.
"""
from .crawl import crawl_clean_text, crawl_many
from .funding import search_nih, search_nsf
from .openalex import openalex_professor, openalex_works
from .scraper import fetch_clean_text
from .search import web_search

TOOL_REGISTRY = {
    "web_search": web_search,
    "openalex_works": openalex_works,
    "openalex_professor": openalex_professor,
    "search_nsf": search_nsf,
    "search_nih": search_nih,
    "fetch_clean_text": fetch_clean_text,
    "crawl_clean_text": crawl_clean_text,
    "crawl_many": crawl_many,
}

__all__ = ["TOOL_REGISTRY", *TOOL_REGISTRY.keys()]
