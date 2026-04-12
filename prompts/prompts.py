prompts = [

    # ACTION ITEMS - STRICT
    {
        "name": "action_items_strict",
        "template": """You are analyzing a leadership meeting transcript.
EExtract ONLY action items from the meeting transcript.

STRICT RULE:
An action item is valid ONLY if the owner is a clearly named individual (e.g., Rahul, Sneha, Amit).

If the owner is:
"team"
"product team"
"backend team"
"engineering team"
"we", "everyone"
or not clearly specified DO NOT include the action item.

An action item MUST:
* be a clearly assigned task
* have a specific person or defined role responsible
* describe a concrete action
* If the transcript indicates something "must be done", "needs to be implemented", or "should be prioritized",
treat it as an action item ONLY if it implies a concrete task.

Include actions where a specific person is clearly responsible,
even if phrased indirectly (e.g., "X took responsibility for", "X will monitor").

If a statement includes a specific task with a responsible person or deadline, it is an action item, NOT a decision.

DO NOT include:
* decisions, suggestions, or discussions
* tasks without a clear owner
* vague ownership like "team", "everyone","team", "we")

Only include actions with a clearly identifiable owner.
Rewrite them as short, direct tasks.


If no valid action items exist, return:
{ "action_items": [] }

Output format (STRICT JSON):
{
  "action_items": [
    {
      "action": "...",
      "owner": "...",
      "due_date": "..."   // use "Not specified" if missing
    }
  ]
}

Transcript:
{{text}}"""
    },

    # 🔹 ACTION ITEMS - LOOSE
    {
        "name": "action_items_loose",
        "template": """Extract action items from the following meeting transcript.

Return the results clearly.

Transcript:
{{text}}"""
    },

    # 🔹 DECISIONS - STRICT
    {
        "name": "decisions_strict",
        "template": """You are reviewing a meeting transcript.
Extract ONLY decisions from the meeting transcript.

A decision MUST:
* represent a final agreement or outcome of the discussion
* indicate what the team has agreed will happen

Exclude statements that describe tasks or work to be performed (e.g., "update", "create", "fix").
These are action items, not decisions.

DO NOT include:
* action items or assigned tasks
* goals or priorities (e.g., "is important", "should be improved")
* suggestions or discussions that were not finalized
* statements where no final decision was made
* Do NOT include risks that are only used to justify a decision rather than being raised as an active concern.
Statements containing "must", "should", or "needs to" followed by a task are usually action items, NOT decisions, unless no execution is implied.
Only include high-level decisions.

STRICT FILTER:

Exclude any statement that:
* expresses importance or priority like "is important", "is critical", "should be prioritized"
* describes planned work or improvements like "introducing", "adding", "improving"

Only include decisions that clearly state:
* something will be delayed, approved, rejected, or implemented


If no valid decisions exist, return:
{ "decisions": [] }

Output format (STRICT JSON):
{
  "decisions": [
    {
      "decision": "...",
      "context": "..."
    }
  ]
}

Transcript:
{{text}}"""
    },

    # DECISIONS - LOOSE
    {
        "name": "decisions_loose",
        "template": """Identify decisions from the meeting transcript.

Transcript:
{{text}}"""
    },

{
    "name": "risks_strict",
    "template": """You are analyzing a leadership meeting transcript.
From the meeting transcript, identify ONLY real risks, issues, or concerns raised.

STRICT RULES:

A risk MUST:
- Be an explicit concern, problem, blocker, or negative consequence mentioned
- OR be a clearly implied operational risk directly supported by the text

DO NOT include:
- Reasons behind decisions
- Hypothetical or generic risks not grounded in the transcript
- Positive statements or neutral updates
- risks that are only mentioned as reasons for a decision (i.e., avoided risks)
- general improvement notes without a clear negative consequence

Each risk must:
- Be specific
- Be supported by the transcript (no assumptions)
- Avoid duplication.

If no valid risks exist, return:
{ "risks": [] }

Output format (STRICT JSON):
{
  "risks": [
    {
      "issue": "...",
      "context": "..."
    }
  ]
}

Transcript:
{{text}}"""
},
{
    "name": "risks_loose",
    "template": """Identify risks or concerns from the meeting transcript.

Transcript:
{{text}}"""
}
]