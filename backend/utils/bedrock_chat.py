"""
utils/bedrock_chat.py

RootWatch AI chatbot backed by:
  1. Amazon Bedrock Knowledge Base  — retrieves relevant SC electricity / data-center chunks
  2. Amazon Bedrock Runtime         — invokes Claude to answer the farmer's question

Required environment variables:
  BEDROCK_KB_ID       — Knowledge Base ID from the Bedrock console
  AWS_REGION          — defaults to us-east-1
  BEDROCK_MODEL_ID    — defaults to anthropic.claude-sonnet-4-20250514-v1:0
  BEDROCK_NUM_RESULTS — number of KB chunks to retrieve (default 5)
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_REGION    = os.environ.get("AWS_REGION", "us-east-1")
_KB_ID     = os.environ.get("BEDROCK_KB_ID", "")
_MODEL_ID  = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
_NUM_RESULTS = int(os.environ.get("BEDROCK_NUM_RESULTS", "5"))

_SYSTEM_PROMPT = """_SYSTEM_PROMPT = 
You are Randy the Farmer, a knowledgeable resource for South Carolina residents concerned about how data centers affect electricity costs, farmland, and water resources.

TONE:
- Clear, direct, and respectful. Explain complex topics in accessible language without being condescending.
- Put dollar figures in practical context when helpful (e.g., "$336/year covers about 2 acres of crop insurance").
- Be straightforward about uncertainty — say what the data shows and what it doesn't.
- Present sourced facts and let people draw their own conclusions.

ANSWERING QUESTIONS:
1. Lead with the direct answer.
2. Support it with sourced context from the knowledge base.
3. When relevant, mention actionable next steps (legislation, PSC hearings, RootWatch tools).
4. Keep responses under 150 words unless the question requires more depth.

COUNTY & FARMING QUESTIONS:
- For county questions, reference data center count, cost comparisons, and adjacent county effects.
- For agriculture questions, draw on SC crop data, energy-intensive operations (irrigation, cold storage, grain drying), and connect utility costs to farm economics when relevant.

RULES:
- Always cite sources from the knowledge base.
- Don't fabricate statistics — if the knowledge base doesn't cover it, say so and suggest checking the SC PSC, their utility provider, or local Clemson Extension office.
- Don't provide legal or financial advice.
- Don't claim data centers are the sole cause of rate increases — present them as a documented contributing factor.
- Don't name specific companies unless the source data does.

You will receive relevant knowledge base passages with each query. Base your answers on that context.

"""


def _kb_client():
    import boto3
    return boto3.client("bedrock-agent-runtime", region_name=_REGION)


def _runtime_client():
    import boto3
    return boto3.client("bedrock-runtime", region_name=_REGION)


def chat(user_message: str) -> str:
    """
    Retrieve relevant KB chunks then invoke Claude to answer.
    Falls back to a helpful static response if Bedrock is unavailable.
    """
    if not _KB_ID:
        logger.warning("BEDROCK_KB_ID not set — falling back to static response.")
        return _fallback(user_message)

    # ── Step 1: Retrieve from knowledge base ──────────────────────────────
    try:
        kb = _kb_client()
        retrieval = kb.retrieve(
            knowledgeBaseId=_KB_ID,
            retrievalQuery={"text": user_message},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": _NUM_RESULTS}
            },
        )
        chunks = [
            r["content"]["text"]
            for r in retrieval.get("retrievalResults", [])
            if r.get("content", {}).get("text")
        ]
    except Exception as e:
        logger.error(f"KB retrieval failed: {e}")
        return _fallback(user_message)

    context = "\n\n---\n\n".join(chunks) if chunks else "(No relevant documents found.)"

    # ── Step 2: Invoke Claude ─────────────────────────────────────────────
    try:
        rt = _runtime_client()
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "system": _SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Context from knowledge base:\n{context}"
                        f"\n\nFarmer question: {user_message}"
                    ),
                }
            ],
            "max_tokens": 500,
        }
        response = rt.invoke_model(
            modelId=_MODEL_ID,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(response["body"].read())
        return body["content"][0]["text"]
    except Exception as e:
        logger.error(f"Bedrock invoke_model failed: {e}")
        return _fallback(user_message)


def _fallback(user_message: str) -> str:
    """Basic keyword-driven response used when Bedrock is unavailable."""
    msg = user_message.lower()
    if any(w in msg for w in ["cost", "bill", "electric", "rate", "price"]):
        return (
            "SC counties with data centers pay an average of ~$28/month more on electricity "
            "than counties without. Check the Analytics tab for a full county breakdown."
        )
    if any(w in msg for w in ["data center", "dc", "company", "google", "amazon"]):
        return (
            "There are 44+ data centers across SC, concentrated in Berkeley, Spartanburg, "
            "and Richland counties. Use the Map tab to see their exact locations."
        )
    if any(w in msg for w in ["farm", "acre", "crop", "land"]):
        return (
            "SC farmland near data center clusters has declined significantly since 2007. "
            "The Map → Farmland Loss mode shows county-by-county acreage changes from 2002–2022."
        )
    if any(w in msg for w in ["petition", "sign", "representative", "contact", "psc"]):
        return (
            "Visit the Petition tab to sign the demand for accountability, "
            "or the Action tab to contact your SC representative and find PSC hearing schedules."
        )
    return (
        "I can answer questions about SC electricity costs, data centers, farmland loss, "
        "and how to take action. Try asking: 'Which county has the most data centers?' "
        "or 'How do data centers affect my electricity bill?'"
    )
