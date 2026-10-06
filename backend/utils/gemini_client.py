"""
utils/gemini_client.py
Gemini API client for AI-assisted EDI analysis.

Loads GEMINI_API_KEY from the project .env file.
All calls are gated by the ai_gate approval system.
Returns (text, error) so callers can surface failures rather than hiding them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Load .env from project root (two levels up from this file)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if _ENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH, override=False)

_API_KEY: str | None = os.environ.get("GEMINI_API_KEY", "").strip() or None
_MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()

_client = None  # lazy-initialised


def _get_client():
    """Return a cached google.genai Client instance, or None if unavailable."""
    global _client
    if _client is not None:
        return _client
    if not _API_KEY:
        return None
    try:
        from google import genai  # type: ignore[import]
        _client = genai.Client(api_key=_API_KEY)
        return _client
    except Exception:
        return None


def is_available() -> bool:
    """Return True if the Gemini client is configured and importable."""
    return _get_client() is not None


def task_step(system: str, messages: list[dict]) -> dict:
    """One AI-directed step. No deterministic fallback, implicit web access, or code execution.

    The model's native reasoning is left enabled at its provider default. Only
    concise conclusions/evidence and explicit tool requests are requested.
    GEMINI_MODEL must name a model available to the deployment's API account.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("Gemini unavailable. Configure GEMINI_API_KEY and an accessible GEMINI_MODEL.")
    from google.genai import types
    response = client.models.generate_content(
        model=_MODEL_NAME,
        contents=[types.Content(
            role=m["role"], parts=[types.Part(text=m["text"])],
        ) for m in messages],
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=16384,
            response_mime_type="application/json",
            response_json_schema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": [
                        "read", "search", "answer", "clarify", "assess", "plan",
                        "external", "write", "copy", "replace", "repeat", "check", "finish",
                    ]},
                    "arguments": {"type": "string", "description": "JSON object of action arguments"},
                },
                "required": ["action", "arguments"],
                "additionalProperties": False,
            },
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    candidates = getattr(response, "candidates", None) or []
    if candidates and str(candidates[0].finish_reason).split(".")[-1] != "STOP":
        raise RuntimeError("Gemini response did not finish normally; no partial action was executed.")
    if not response.text:
        raise RuntimeError("Gemini returned no task response; no output was published.")
    step = json.loads(response.text)
    if set(step) != {"action", "arguments"}:
        raise ValueError("Invalid Gemini task response.")
    step["arguments"] = json.loads(step["arguments"])
    if not isinstance(step["arguments"], dict):
        raise ValueError("Gemini action arguments must be an object.")
    return step


def generate(prompt: str, max_tokens: int = 1024) -> tuple[str | None, str | None]:
    """
    Send a prompt to Gemini and return ``(text, error)``.
    On success: ``(text, None)``.
    On failure: ``(None, human-readable error message)``.
    """
    client = _get_client()
    if client is None:
        reason = "GEMINI_API_KEY not configured" if not _API_KEY else "google-genai package unavailable"
        return None, f"Gemini unavailable: {reason}"
    try:
        from google.genai import types  # type: ignore[import]
        response = client.models.generate_content(
            model=_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.2,  # low temperature for factual, consistent output
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        text = response.text.strip() if response.text else None
        if text is None:
            return None, "Gemini returned an empty response"
        return text, None
    except Exception as exc:
        return None, f"Gemini API error: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Prompt builders — send structured data, never raw EDI (PHI avoidance)
# ---------------------------------------------------------------------------

def analysis_prompt_for_validation(result_dict: dict, user_prompt: str) -> str:
    status = result_dict.get("status", "UNKNOWN")
    tx_type = result_dict.get("transaction_type", "EDI")
    errors = result_dict.get("errors", [])[:10]
    warnings = result_dict.get("warnings", [])[:5]

    error_lines = "\n".join(
        f"- Segment {e.get('segment','?')}: {e.get('description','')}"
        for e in errors
    )
    warn_lines = "\n".join(
        f"- {w.get('description','')}" for w in warnings
    )

    directive = ""
    if user_prompt:
        directive = (
            f"USER DIRECTIVE: {user_prompt}\n"
            f"Execute the above directive using the following validation result as context.\n\n"
        )

    base = (
        directive
        + f"You are a healthcare EDI expert. Analyze this X12 {tx_type} validation result "
        + "and provide concise, actionable remediation guidance.\n\n"
        + f"Status: {status}\n"
        + f"Error count: {result_dict.get('error_count', 0)}\n"
        + f"Warning count: {result_dict.get('warning_count', 0)}\n"
    )
    if error_lines:
        base += f"\nErrors:\n{error_lines}\n"
    if warn_lines:
        base += f"\nWarnings:\n{warn_lines}\n"
    base += (
        "\nExplain what you are doing and why, then provide a numbered list of specific corrections. "
        "Be concise. No generic advice — reference the actual segment names and codes above."
    )
    return base


def analysis_prompt_for_999(result_dict: dict, user_prompt: str) -> str:
    tx_analyses = result_dict.get("transaction_analyses", [])
    summary_lines = []
    for ta in tx_analyses[:5]:
        ik5 = ta.get("ik5_code", ta.get("ak5_code", "?"))
        ctrl = ta.get("transaction_set_control_number", ta.get("control_number", "?"))
        errors = ta.get("segment_errors", ta.get("errors", []))[:3]
        err_str = "; ".join(
            f"seg {e.get('segment_id', e.get('segment','?'))} code {e.get('ik4_code', e.get('error_code','?'))}"
            for e in errors
        )
        summary_lines.append(f"  Transaction {ctrl}: IK5={ik5}" + (f" | {err_str}" if err_str else ""))

    directive = f"USER DIRECTIVE: {user_prompt}\n\n" if user_prompt else ""
    prompt = (
        directive
        + "You are a healthcare EDI expert specializing in X12 999 acknowledgments.\n\n"
        + "Analyze the following 999 transaction results and give specific remediation steps:\n"
        + "\n".join(summary_lines)
    )
    prompt += "\n\nExplain your reasoning, then be concise and actionable. Reference IK5/IK4 codes directly."
    return prompt


def analysis_prompt_for_277ca(result_dict: dict, user_prompt: str) -> str:
    claims = result_dict.get("claim_analyses", [])
    rejected = [c for c in claims if str(c.get("claim_status_category_code", "")).startswith("R")][:5]
    accepted_count = sum(1 for c in claims if str(c.get("claim_status_category_code", "")).startswith("A"))

    rej_lines = "\n".join(
        f"  Claim {c.get('claim_id', c.get('patient_control_number','?'))}: "
        f"STC={c.get('claim_status_category_code','?')}/{c.get('claim_status_code','?')}"
        for c in rejected
    )

    prompt = (
        "You are a healthcare EDI expert. Analyze this 277CA claim acknowledgment summary:\n\n"
        f"Total claims: {len(claims)} | Accepted: {accepted_count} | Needing action: {len(rejected)}\n"
    )
    if rej_lines:
        prompt += f"\nRejected/pending claims:\n{rej_lines}\n"
    if user_prompt:
        prompt = f"USER DIRECTIVE: {user_prompt}\n\n" + prompt
    prompt += "\nExplain your reasoning, then provide specific next steps for each rejected claim. Be concise."
    return prompt


def analysis_prompt_for_comparison(result_dict: dict, user_prompt: str) -> str:
    total_diff = result_dict.get("total_differences", 0)
    records = result_dict.get("record_comparisons", [])
    matched = sum(1 for r in records if r.get("total_differences", 0) == 0)

    diff_counts: dict[str, int] = {}
    segment_diffs: dict[str, int] = {}
    for rec in records:
        for diff in rec.get("differences", []):
            dtype = diff.get("difference_type", "VALUE_CHANGE")
            diff_counts[dtype] = diff_counts.get(dtype, 0) + 1
            seg = diff.get("segment", "").split("-")[0].strip().upper()
            if seg:
                segment_diffs[seg] = segment_diffs.get(seg, 0) + 1

    top_segs = sorted(segment_diffs.items(), key=lambda x: -x[1])[:5]

    prompt = (
        "You are a healthcare EDI expert. Analyze this EDI file comparison:\n\n"
        f"Total records: {len(records)} | Matched: {matched} | With differences: {len(records)-matched}\n"
        f"Total element differences: {total_diff}\n"
    )
    if diff_counts:
        prompt += "Difference types: " + ", ".join(f"{k}={v}" for k, v in diff_counts.items()) + "\n"
    if top_segs:
        prompt += "Most-affected segments: " + ", ".join(f"{s}({c})" for s, c in top_segs) + "\n"
    if user_prompt:
        prompt = f"USER DIRECTIVE: {user_prompt}\n\n" + prompt
    prompt += "\nExplain your reasoning, then describe what likely caused these differences and what action should be taken. Be concise."
    return prompt


def analysis_prompt_for_generate(tx_type: str, applied_updates: list, user_prompt: str) -> str:
    update_lines = "\n".join(f"  {u['field']} = {u['value']}" for u in applied_updates[:10])
    prompt = ""
    if user_prompt:
        prompt += (
            f"USER DIRECTIVE: {user_prompt}\n\n"
            f"Execute the above directive for this X12 {tx_type} EDI generation result.\n\n"
        )
    prompt += (
        f"You are a healthcare EDI expert. An AI-assisted X12 {tx_type} EDI file was just generated "
        f"with the following field updates applied:\n"
        + (update_lines or "  (none)")
        + "\n"
    )
    prompt += (
        "\nProvide a brief quality check: list any fields that commonly need review before submission "
        f"for {tx_type}, and flag any of the applied values that look unusual. Be concise."
    )
    return prompt


# ---------------------------------------------------------------------------
# Generic Q&A / follow-up chat prompt
# ---------------------------------------------------------------------------

def analysis_prompt_for_ask(
    panel: str,
    user_instruction: str,
    context: str,
    history: list[dict],
) -> str:
    """
    Build a prompt for the generic /ask endpoint used for:
      - AI Processing Mode on panels that have no dedicated AI endpoint
        (Excel Export, TP Mapping, Companion Guide)
      - Follow-up / chat messages from any panel after an AI task completes

    The user_instruction is the PRIMARY directive.  Context and history are
    supporting material for grounding the response.
    """
    system = (
        "You are an expert healthcare EDI assistant for an EDI Accelerator platform. "
        "Your role is to help users understand, generate, validate, and troubleshoot "
        "X12 healthcare EDI transactions (837P, 837I, 278, 834, 820, 999, 277CA). "
        "When context is provided, base your answer on that specific data. "
        "Explain your reasoning step by step. "
        "Never fabricate specific claim IDs, NPIs, member IDs, or dollar amounts — "
        "use placeholders like <NPI>, <MemberID> when specific values are not given."
    )

    history_text = ""
    if history:
        for msg in history[-8:]:  # last 8 messages for context window efficiency
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = (msg.get("content") or "").strip()
            if content:
                history_text += f"\n{role}: {content}"

    ctx_snippet = (context or "").strip()
    if len(ctx_snippet) > 3000:
        ctx_snippet = ctx_snippet[:3000] + "\n… (context truncated)"

    prompt = f"{system}\n\n"
    if ctx_snippet:
        prompt += f"--- Current panel context ({panel}) ---\n{ctx_snippet}\n---\n\n"
    if history_text:
        prompt += f"--- Conversation so far ---{history_text}\n---\n\n"
    prompt += (
        f"User instruction / question: {user_instruction}\n\n"
        "Provide a clear, structured answer. "
        "Explain what you are doing and why. "
        "If the answer involves EDI segments, reference them by name (e.g. NM1*85, DTP*472). "
        "Use numbered steps for multi-step reasoning. "
        "Be specific — do not give generic boilerplate."
    )
    return prompt
