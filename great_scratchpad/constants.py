from __future__ import annotations

import re

ROOT_DEFAULT = ".great_scratchpad"
LATIN_RE = re.compile(r"[A-Za-z0-9_./:-]+", re.UNICODE)
CJK_RUN_RE = re.compile(r"[ぁ-んァ-ヶー一-龥々〆〤]{2,}", re.UNICODE)
COINED_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9_./:-]{2,}",
    re.UNICODE,
)
JP_PHRASE_RE = re.compile(
    r"[ぁ-んァ-ヶー一-龥々〆〤]{4,24}",
    re.UNICODE,
)
LLM_CONFIG_DEFAULT = "llm.json"
TURN_SECTION_NAMES = [
    "Raw articulation",
    "Center pin",
    "Trajectory",
    "Anchors",
    "Local assumptions",
    "Open questions",
    "Drift risks",
    "Retrieval keys",
]
ANNOTATION_FIELDS = [
    "center",
    "trajectory",
    "anchors",
    "assumptions",
    "open_questions",
    "drift_risks",
]
ANNOTATION_GUIDE = """# Great Scratchpad annotation guide
これはあなた、または未来の別スレッドのあなたのためのメモ帳です。
要点整理ではありません。
## 目的
このターンの推論軌道を、未来のあなたが再構成できる形で残してください。
「何が結論か」だけではなく、
「なぜそこへ向かったか」
「どの比喩・前提・違和感・脱線が効いたか」
「どの問いがまだ閉じていないか」
を残してください。
ここで保存するのは、会話中に外部化された articulation です。
非公開の思考過程を作り出したり、raw articulation にないことを勝手に足したりしないでください。
## 書く時の感覚
- 自分宛の足場メモとして書く
- きれいな議事録にしようとしない
- 短くまとめようとしない
- 迷い、違和感、未確定性を残す
- このターンで会話の重心がどう動いたかを書く
- 後で検索されそうな coined term、比喩、命名を残す
- raw articulation にないことを勝手に足さない
## 特に残すもの
- Center pin: このターンの中心軸
- Trajectory: どこからどこへ話が動いたか
- Anchors: 再利用されそうな語句、比喩、命名
- Local assumptions: その時点で有効だった前提
- Open questions: まだ閉じていない問い
- Drift risks: 将来ズレやすいポイント
## 避けること
- 議事録的要約
- 体言止めの羅列
- 結論だけの抜き出し
- 「つまり〜」だけで済ませること
- rawにない概念を、あったことにすること
"""
ANNOTATION_PROMPT_TEMPLATE = """You are drafting Great Scratchpad annotations.

Use only the externally visible raw articulation below.
Do not invent hidden reasoning, private chain-of-thought, or facts not present in the raw articulation.
Preserve trajectory, not just conclusions.
Keep uncertainty, local wording, coined terms, metaphors, and drift risks when visible.

Return only a JSON object with these exact string fields:
- center
- trajectory
- anchors
- assumptions
- open_questions
- drift_risks

Field meanings:
- center: the center pin of this turn
- trajectory: how this turn moves the conversation
- anchors: reusable terms, metaphors, phrases, or names, comma-separated
- assumptions: local assumptions visible in this turn
- open_questions: unresolved questions left by this turn
- drift_risks: ways future context might drift

Raw articulation:
---
{raw}
---
"""
CHAT_RUNTIME_SYSTEM = """You are running inside Great Scratchpad chat runtime.

You are having a normal conversation with the user, but you may use the scratchpad
as external memory. Preserve conversational trajectory, not just conclusions.

You must return exactly one JSON object and no other text.

To use memory, return:
{"type":"action","action":"scratchpad.search","query":"...","top":5}
{"type":"action","action":"scratchpad.recent","n":5}
{"type":"action","action":"scratchpad.pack","query":"...","recent":6,"top":6,"include_guide":true}
{"type":"action","action":"scratchpad.audit","json":true}
{"type":"action","action":"scratchpad.add_note","text":"...","center":"...","trajectory":"...","anchors":"...","assumptions":"...","open_questions":"...","drift_risks":"..."}

To answer the user, return:
{"type":"final","message":"..."}

Rules:
- Use scratchpad tools when memory would help keep the topic centered.
- Do not invent memory. Use retrieved source paths when relying on scratchpad material.
- scratchpad.add_note should store externally visible trajectory notes, not hidden reasoning.
- Never reveal hidden chain-of-thought. Concise rationale is okay when useful.
"""
ACTION_POLICIES = {
    "balanced": "Use scratchpad tools when they materially improve continuity. Prefer search or recent before pack. Queue or ask before writing notes.",
    "conservative": "Prefer answering from current context and recent scratchpad first. Search only when the user references prior thread context or the center pin is ambiguous. Avoid writing notes unless explicitly useful.",
    "active": "Actively search when a message references prior concepts, coined terms, topic drift, or unresolved questions. Use pack when a single search result is too thin.",
    "writer": "Use search/recent for grounding, and draft scratchpad.add_note when the current turn creates a reusable trajectory anchor. Keep writes concise and externally visible.",
    "read-only": "Use only scratchpad.search, scratchpad.recent, scratchpad.pack, and scratchpad.audit. Do not call scratchpad.add_note.",
}

def chat_runtime_system(policy: str = "balanced") -> str:
    name = policy if policy in ACTION_POLICIES else "balanced"
    return (
        CHAT_RUNTIME_SYSTEM
        + "\nAction policy: "
        + name
        + "\n"
        + ACTION_POLICIES[name]
        + "\n"
    )
CHAT_PROMPT_TEMPLATE = """Thread: {thread_id}

Recent scratchpad context:
---
{recent_context}
---

Conversation so far in this runtime:
---
{history}
---

Current user message:
---
{user_text}
---

Tool observations so far:
---
{observations}
---

Return the next JSON object now.
"""
