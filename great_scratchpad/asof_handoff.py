"""Replay countersigned handoffs at separate effective and filing cutoffs."""

import random

from .countersigned_join import MATCH, TEXT, handoff_rows

SCENARIO = "asof-handoff"
RULES = (
    "登録票・申出・系列表は常設。受領と状態届は、効力日が照会の対象日以下かつ登録日が"
    "照会の登録締切以下のものだけ使う。台帳をまたいで同名の依頼や班や系列を混同しない。"
    "対象の登録票から対象班の全申出を調べる。申出と受領の送信元台帳、班、受信先台帳、系列、照合番号の"
    "5項目が一致した組だけを照合済みとする。照合済みの組は初期状態が有効。"
    "状態届は同じ5項目が一致し、かつ発行台帳が受信先台帳と同じ場合だけ正式。"
    "組ごとに、使える正式な届のうち効力日が最大の1枚だけを適用し、同じ効力日なら登録日が新しい方を使う。"
    "停止なら無効、再開なら有効。載っている順番や最後に登録されたこと自体には優先権がない。"
    "有効な組が1つならその受信先台帳と系列で実行プールを引く。0または複数なら未確定。"
    "根拠には、登録票、対象班の全申出、各申出と照合済みの受領（停止中も含む）、"
    "適用した状態届を過不足なく挙げる。実行先が確定した場合だけ対応する系列表1枚も挙げる。"
)
CHANGE_TEXT = "状態届：発行台帳 {issuer}。{src} の班 {team} から {dst} の系列 {line}、照合番号 {code} は{action}。"


def state(case: dict, records: list[dict]) -> dict:
    start = next((r for r in records if r["kind"] == "assignment"
                  and (r["src"], r["ticket"]) == (case["site"], case["target"])), None)
    proof = [start["id"]] if start else []
    dated = [r for r in records if r["kind"] in ("receipt", "change") and
             r["effective"] <= case["asof"] and r["filed"] <= case["file_cutoff"]]
    active = []
    for offer in records:
        if not start or offer["kind"] != "offer" or (offer["src"], offer["team"]) != (start["src"], start["team"]):
            continue
        proof.append(offer["id"])
        matching = [r for r in dated if all(r[k] == offer[k] for k in MATCH)]
        for receipt in (r for r in matching if r["kind"] == "receipt"):
            proof.append(receipt["id"])
            latest = max((r for r in matching if r["kind"] == "change" and r["issuer"] == offer["dst"]),
                         key=lambda r: (r["effective"], r["filed"]), default=None)
            if latest:
                proof.append(latest["id"])
            if not latest or latest["action"] == "再開":
                active.append(offer)
    value = None
    if len(active) == 1:
        o = active[0]
        end = next((r for r in records if r["kind"] == "line-pool" and (r["dst"], r["line"]) ==
                    (o["dst"], o["line"])), None)
        if end:
            value = end["pool"]
            proof.append(end["id"])
    return {"status": "known" if value is not None else "unknown", "value": value,
            "support": proof, "eligible_ids": proof[:], "flags": {}}


def cases(spec: dict):
    seed = spec["fresh_seed"]
    sites, ticket, rows = handoff_rows(seed, {(0, 0), (0, 1), (1, 1)})
    a, b = [r for r in rows if r["kind"] == "offer" and r["src"] == sites[0]]
    for r in rows:
        if r["kind"] == "receipt":
            r["effective"], r["filed"] = (35, 38) if r["dst"] == b["dst"] else (10, 10)
    for offer, issuer, action, effective, filed in (
        (a, a["dst"], "停止", 20, 50), (a, a["dst"], "再開", 40, 58),
        (a, a["dst"], "停止", 16, 60), (a, a["src"], "停止", 39, 41),
        (b, b["dst"], "停止", 38, 61),
    ):
        rows.append({**offer, "kind": "change", "issuer": issuer, "action": action,
                     "effective": effective, "filed": filed})
    random.Random(seed).shuffle(rows)
    for n, r in enumerate(rows, 1):
        template = CHANGE_TEXT if r["kind"] == "change" else TEXT[r["kind"]]
        if "effective" in r:
            template += " 効力日 {effective}、登録日 {filed}。"
        r.update(id=f"m{n:03d}", turn=n, text=template.format(**r))
    for asof, cutoff in spec["queries"]:
        label = f"effective{asof}-filed{cutoff}"
        case = {"id": f"{SCENARIO}-{seed}-{label}", "scenario": SCENARIO, "family": "distributed-join",
                "seed": seed, "site": sites[0], "target": ticket, "asof": asof, "file_cutoff": cutoff,
                "records": rows, "query": f"照会：台帳 {sites[0]} の依頼 {ticket}。対象日 {asof}、登録締切 {cutoff}。"
                f"この時点での実行プールは？\n{RULES}"}
        case["truth"] = state(case, rows)
        yield case, [(label, rows)]
