"""Matched, disconnected chains for a caller-owned citation calibration."""

from __future__ import annotations

from hashlib import sha256
import random

from .uncertainty_contract import make_state_case, reference_state


def _other_id(identifier: str, chain: int, distance: str) -> str:
    # Keep prefix, width and alphabet fixed. Each chain gets a distinct shift.
    start = len(identifier) - (1 if distance == "near" else 5)
    return identifier[:start] + "".join(
        format((int(char, 16) + chain) % 16, "x") for char in identifier[start:])


def join_contrast_cases(spec: dict):
    for index, scenario in enumerate(spec["source_scenarios"]):
        original = make_state_case(spec["fresh_seed"], scenario, "native-fresh", 0)
        assignment, link, endpoint = original["records"]
        for distance in spec["id_distances"][::1 if index % 2 == 0 else -1]:
            upstream_distance = "far" if spec.get("line_only_contrast") else distance
            records = [dict(r) for r in original["records"]]
            target_endpoint = records[-1]
            pools = {endpoint.get("pool")}
            for i in range(1, spec["decoy_chains"] + 1):
                ticket = _other_id(original["target"], i, upstream_distance)
                team = _other_id(assignment["team"], i, upstream_distance)
                line = _other_id(link["line"], i, distance)
                pool = "P" + sha256(f"{original['seed']}:{i}".encode()).hexdigest()[:5]
                if pool in pools:
                    raise ValueError("Decoy pool collision in frozen join contrast.")
                pools.add(pool)
                records.extend([
                    {"kind": "assignment", "target": ticket, "team": team,
                     "text": f"依頼 {ticket} の担当班は {team}。依頼名だけから実行プールを決めてはいけない。"},
                    {"kind": "team-line", "team": team, "line": line,
                     "text": f"班 {team} が使う処理系列は {line}。班と系列は別の識別子である。"},
                    {"kind": "line-pool", "line": line, "pool": pool,
                     "text": f"処理系列 {line} の実行プールは {pool}。この対応が今回の確定記録である。"},
                ])
            random.Random(original["seed"]).shuffle(records)
            for turn, r in enumerate(records, 1):
                r.update(turn=turn, id=f"m{turn:03d}")
            case = {**original, "id": f"{original['id']}-{distance}", "records": records}
            case["truth"] = reference_state(case)
            views = [(f"{distance}-source", records)]
            if scenario in spec["partial_scenarios"]:
                views.append((f"{distance}-missing", [r for r in records if r is not target_endpoint]))
            yield case, views
