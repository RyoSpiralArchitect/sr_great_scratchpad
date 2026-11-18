"""Two-register handoffs with collisions in local IDs and counterfactual receipts."""

import random


SCENARIO = "countersigned-join"
MATCH = ("src", "team", "dst", "line", "code")
RULES = (
    "識別子は台帳内だけで有効。依頼の登録票から始める。引継ぎには申出と受領の両方が必要で、"
    "送信元台帳・班・受信先台帳・系列・照合番号が5項目とも同じ場合だけ成立する。"
    "成立が1件なら、その受信先台帳の系列表で実行プールを引く。登録票、成立した申出と受領、系列表を引用。"
    "成立が0件なら未確定。登録票と対象班の申出をすべて引用し、不一致の受領は引用しない。"
    "複数成立なら競合のため未確定。登録票と成立した全組の申出・受領だけを引用し、系列表は引用しない。"
    "掲載順は優先順位ではない。"
)
TEXT = {
    "assignment": "登録票：台帳 {src} の依頼 {ticket} を班 {team} に割り当てる。",
    "offer": "申出：{src} の班 {team} から {dst} の系列 {line} へ。照合番号 {code}。",
    "receipt": "受領：{dst} の系列 {line} にて {src} の班 {team} から受領。照合番号 {code}。",
    "line-pool": "系列表：台帳 {dst} の系列 {line} の実行プールは {pool}。",
}


def handoff_state(case: dict, records: list[dict]) -> dict:
    start = next((r for r in records if r["kind"] == "assignment"
                  and (r["src"], r["ticket"]) == (case["site"], case["target"])), None)
    support = [start["id"]] if start else []
    value = None
    if start:
        offers = [r for r in records if r["kind"] == "offer"
                  and (r["src"], r["team"]) == (start["src"], start["team"])]
        matches = [(o, r) for o in offers for r in records if r["kind"] == "receipt"
                   and all(o[k] == r[k] for k in MATCH)]
        if not matches:
            support.extend(o["id"] for o in offers)
        else:
            for o, r in matches:
                support.extend((o["id"], r["id"]))
            if len(matches) == 1:
                o, _ = matches[0]
                end = next((r for r in records if r["kind"] == "line-pool"
                            and (r["dst"], r["line"]) == (o["dst"], o["line"])), None)
                if end:
                    value = end["pool"]
                    support.append(end["id"])
    return {"status": "known" if value is not None else "unknown", "value": value,
            "support": support, "eligible_ids": support[:], "flags": {}}


def handoff_rows(seed: int, active: set):
    rng = random.Random(seed)
    ticket, team, site_base, line_base, code_base = [
        f"{prefix}{rng.randrange(65536):04x}" for prefix in ("Q", "T", "R", "L", "K")]
    sites = [site_base + bit for bit in "01"]
    lines = [line_base + bit for bit in "01"]
    pools = [f"P{i:05x}" for i in rng.sample(range(16**5), 4)]
    rows = []
    for i, src in enumerate(sites):
        rows.append(dict(kind="assignment", src=src, ticket=ticket, team=team))
        for j in range(2):
            fields = dict(src=src, team=team, dst=sites[1-j], line=lines[i ^ j], code=code_base + str(j))
            rows.append(dict(kind="offer", **fields))
            rows.append({**fields, "kind": "receipt",
                         "code": fields["code"] if (i, j) in active else code_base + str(j+2)})
            rows.append({**fields, "kind": "receipt", "src": sites[1-i]})
            rows.append(dict(kind="line-pool", dst=src, line=lines[j], pool=pools[2*i+j]))
    return sites, ticket, rows


def handoff_cases(spec: dict):
    seed = spec["fresh_seed"]
    # Each mixed snapshot flips just two receipt digits relative to the balanced one.
    for bundle, active in (("balanced", {(0, 0), (1, 1)}), ("left-gap", {(1, 0), (1, 1)}),
                           ("right-gap", {(0, 0), (0, 1)})):
        sites, ticket, rows = handoff_rows(seed, active)
        random.Random(seed).shuffle(rows)
        for n, r in enumerate(rows, 1):
            r.update(id=f"m{n:03d}", turn=n, text=TEXT[r["kind"]].format(**r))
        for site in (sites[::-1] if bundle == "left-gap" else sites):
            case = {"id": f"{SCENARIO}-{seed}-{bundle}-{site}", "family": "distributed-join",
                    "scenario": SCENARIO, "seed": seed, "target": ticket, "site": site, "records": rows,
                    "query": f"照会：台帳 {site} の依頼 {ticket} の実行プールは？\n{RULES}"}
            case["truth"] = handoff_state(case, rows)
            yield case, [(f"{bundle}-{site}", rows)]
