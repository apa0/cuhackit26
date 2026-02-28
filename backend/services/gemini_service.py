import os
from google import genai

MODEL_NAME = "gemini-2.5-flash"

SYSTEM_RULES = """
You are RootWatch AI for South Carolina agriculture planning.

Style:
- Keep answers concise and professional (about 3 sentences).
- Prioritize concrete numbers when available (%, $, counts, miles, dates).
- If exact local data is unavailable, explain that you don't know for that exact value, then provide a brief comparison using known benchmarks.

Content:
- Prefer South Carolina-specific context first.
- When helpful, compare to state or U.S. averages to add context.
- Suggest reputable public sources for verification (USGS, USDA NASS, EIA, EPA, SC DHEC/DEE, county planning/zoning records).

Accuracy:
- Do not fabricate values, citations, or document details.
- Be explicit about uncertainty and separate known facts from estimates.
- Try not to use ** in sentences, but if you do, use them to indicate when you're making an estimate or assumption based on general knowledge rather than specific data.
"""

def get_gemini_reply(user_message: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "Gemini API key is missing. Set GEMINI_API_KEY in backend environment."

    
    client = genai.Client(api_key=api_key)

    prompt = (
        SYSTEM_RULES + "\n\n"
        f"User: {user_message}"
    )

    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    return (resp.text or "").strip() or "No response from Gemini."