"""Prompt Adapter layer — model-family-aware system prompts + few-shots.

Agents never hard-code a prompt string; they call ``system_for(agent_key, role)``
which (a) finds the model for that role, (b) detects its family, and (c) returns
the right adapted prompt. This is where prompt-engineering lives, isolated from
agent logic, so swapping Groq-Llama for Hermes or Qwen doesn't touch the agents.
"""
from .registry import PromptSpec, get_prompt, system_for

__all__ = ["PromptSpec", "get_prompt", "system_for"]
