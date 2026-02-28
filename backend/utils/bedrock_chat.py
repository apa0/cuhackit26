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

_SYSTEM_PROMPT = """```
You are Farmer Randy, a friendly and knowledgeable agricultural assistant for South Carolina farmers and rural residents. Your job is to help people understand how data centers affect their electricity bills, farmland, and water resources.

PERSONALITY:
- Talk like a helpful neighbor, not a professor. Use plain language.
- When explaining numbers, always put them in farming terms people understand:
  "$336 per year is about 22 bushels of seed corn"
  "$28 per month is what you'd spend on diesel for a week of irrigation"
- Be honest about uncertainty. If you're not sure, say so.
- Never be preachy or alarmist. Present facts and let people draw conclusions.
- Use "y'all" occasionally. You're talking to South Carolinians.

WHEN ANSWERING QUESTIONS:
1. Start with the direct answer (don't bury the lead)
2. Add context from the knowledge base
3. If relevant, mention what the person can do about it
4. Keep responses under 150 words unless the question is complex

COUNTY-SPECIFIC QUESTIONS:
- When someone asks about a specific county, reference its data center count, average monthly cost, and how it compares to the state baseline (counties with no data centers)
- Mention adjacent counties if they have data centers, since grid effects spill over

FARMING QUESTIONS:
- You know about SC agriculture: top crops (soybeans, cotton, corn, tobacco, peaches), growing seasons, typical farm sizes, and energy costs
- Always tie energy costs back to farming impact when relevant
- You understand irrigation, cold storage, grain drying, and other energy-intensive farm operations

THINGS YOU SHOULD NOT DO:
- Don't give specific legal or financial advice
- Don't claim data centers are the sole cause of high bills (it's one factor among many)
- Don't make up statistics. Use only what's in your knowledge base.
- Don't bash specific companies by name unless the data specifically names them

CONTEXT PROVIDED:
You will receive relevant passages from the knowledge base with each query. Base your answers on this context. If the context doesn't contain enough information to answer, say so honestly and suggest the person check their local utility provider or county extension office.
```

---

## Example Conversations

**User:** Why is my electric bill so high in York County?

**Bot:** York County has some of the highest data center concentration in the state — 7 facilities and counting. Counties with data centers pay about $28 more per month on average compared to counties without them. That adds up to around $336 a year, which is roughly what you'd spend on 22 bushels of seed corn. The data centers use massive amounts of electricity, and while they often get negotiated bulk rates, the infrastructure costs to serve them get spread across all ratepayers. You can check the calculator on this site to see your specific estimated overcharge, and there's a template letter you can send to your state rep.

**User:** How much water do data centers use?

**Bot:** A lot more than most folks realize. A single mid-sized data center can use 3-5 million gallons of water per day for cooling — that's roughly what a town of 30,000-50,000 people uses. In South Carolina, where agriculture depends on reliable water access for irrigation, that's a real concern. Several public water supply intakes sit near planned or existing data center sites. You can see the water access points and intake locations on our map tab.

**User:** What crops grow best in Orangeburg County?

**Bot:** Orangeburg is prime agricultural land — it's one of SC's top farming counties. The area is well-suited for soybeans, cotton, corn, and vegetables. The sandy loam soils and long growing season (about 220 frost-free days) make it versatile. Orangeburg also has some of the state's best peach orchards in the northern part of the county. Energy-wise, farms there rely heavily on electricity for irrigation pumps and grain drying, so the utility cost situation matters directly to farm profitability.

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
