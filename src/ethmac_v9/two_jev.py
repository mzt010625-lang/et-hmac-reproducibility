"""Contracts and compression for JEV-fast action -> JEV-verifier -> L2."""
from __future__ import annotations
import json
import math
import re
from collections import Counter
from .models import ACTIONS

ACTION_KEYS={"v","id","action","p","confidence","alternative","uncertainty","risk","evidence"}
ACTION_RISKS={"NONE","POLICY_UNCERTAINTY","MARKET_CONFLICT","GOAL_CONFLICT",
              "MEMORY_CONFLICT","NETWORK","MULTISTEP","LOW_MARGIN","HIGH_STAKES"}

_NUMBER_RE=re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

def _json_number(value):
    """Repair only a JSON representation difference, never a model judgment."""
    if isinstance(value,str) and _NUMBER_RE.fullmatch(value.strip()):
        return float(value)
    return value

def normalize_action(out: dict, record: dict) -> list[str]:
    """Canonicalize lossless output variants and return an audit trail.

    Raw provider responses remain immutable in ``*_responses.jsonl``.  This
    function only repairs redundant JSON representation details that cannot
    change the chosen action, ranking, risk meaning, or evidence provenance.
    """
    if not isinstance(out,dict):
        raise ValueError("JEV-fast output must be an object")
    repairs=[]
    probabilities=out.get("p")
    if isinstance(probabilities,dict):
        repaired={k:_json_number(v) for k,v in probabilities.items()}
        if repaired!=probabilities:
            out["p"]=repaired; repairs.append("numeric_strings_in_p")
        # If the returned entries already exhaust probability mass, omitted
        # legal actions are mathematically forced to zero.  This is safe to
        # repair; a partial distribution whose mass is below one is rejected.
        allowed=list(record.get("allowed") or [])
        provided=set(out["p"])
        values=list(out["p"].values())
        numeric=(values and all(not isinstance(x,bool) and isinstance(x,(int,float))
                                and math.isfinite(x) and 0<=x<=1 for x in values))
        if (provided < set(allowed) and not (provided-set(allowed)) and
            out.get("action") in provided and numeric and abs(sum(values)-1)<=1e-5):
            out["p"].update({action:0.0 for action in allowed if action not in provided})
            repairs.append("zero_filled_forced_omitted_probabilities")
    for key in ("confidence","uncertainty"):
        repaired=_json_number(out.get(key))
        if repaired!=out.get(key):
            out[key]=repaired; repairs.append("numeric_string_"+key)
    if isinstance(out.get("risk"),str):
        out["risk"]=[out["risk"]]; repairs.append("singleton_risk_to_list")
    if isinstance(out.get("evidence"),str):
        out["evidence"]=[out["evidence"]]; repairs.append("singleton_evidence_to_list")
    evidence=out.get("evidence")
    if isinstance(evidence,list):
        source_by_ref={item["ref"]:item for item in record.get("evidence",[])}
        normalized=[]; changed=False
        for item in evidence:
            if isinstance(item,dict) and isinstance(item.get("ref"),str):
                ref=item["ref"]; source=source_by_ref.get(ref)
                # Accept a ref wrapper or an exact subset copied from the
                # corresponding visible evidence.  Any invented/altered field
                # remains unnormalized and is rejected by validation below.
                if source is not None and all(k in source and source[k]==v
                                              for k,v in item.items() if k!="ref"):
                    normalized.append(ref); changed=True
                else:
                    normalized.append(item)
            else:
                normalized.append(item)
        if changed:
            out["evidence"]=normalized; repairs.append("evidence_ref_objects_to_strings")
    # ``alternative`` is redundant with p. Filling an omitted/null value is
    # safe only when the complete probability map makes it directly derivable.
    allowed=list(record.get("allowed") or [])
    if len(allowed)>1 and out.get("alternative") is None and isinstance(out.get("p"),dict):
        action=out.get("action")
        if action in allowed and set(out["p"])==set(allowed):
            out["alternative"]=max((a for a in allowed if a!=action),
                                   key=lambda a:(out["p"][a],-allowed.index(a)))
            repairs.append("derived_missing_alternative_from_p")
    return repairs

def action_input(compact: dict) -> dict:
    out=json.loads(json.dumps(compact,ensure_ascii=False))
    out.pop("l1",None)
    return out

def validate_action(out: dict, record: dict) -> None:
    normalize_action(out,record)
    if set(out)!=ACTION_KEYS or out["v"]!="jev_action_v1" or out["id"]!=record["id"]:
        raise ValueError("JEV-fast action schema/id mismatch")
    allowed=list(record["allowed"])
    if not isinstance(out["p"],dict) or out["action"] not in allowed or set(out["p"])!=set(allowed):
        raise ValueError("JEV-fast action/probability keys violate allowed actions")
    vals=list(out["p"].values())
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in vals):
        raise ValueError("action probabilities must be finite in [0,1]")
    if abs(sum(vals)-1)>1e-5:
        raise ValueError("action probabilities must sum to one")
    top=max(out["p"].values())
    if abs(out["p"][out["action"]]-top)>1e-9:
        raise ValueError("action must be an argmax")
    if len(allowed)==1:
        if out["alternative"] is not None:
            raise ValueError("alternative must be null for one legal action")
    else:
        if out["alternative"] not in allowed or out["alternative"]==out["action"]:
            raise ValueError("alternative must be another legal action")
        second=max(out["p"][a] for a in allowed if a!=out["action"])
        if abs(out["p"][out["alternative"]]-second)>1e-9:
            raise ValueError("alternative must have the second-highest probability; ties are allowed")
    for k in ("confidence","uncertainty"):
        x=out[k]
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1:
            raise ValueError(k+" must be finite in [0,1]")
    risks=out["risk"]
    if (not isinstance(risks,list) or not 1<=len(risks)<=3 or
        any(not isinstance(x,str) for x in risks) or
        len(set(risks))!=len(risks) or set(risks)-ACTION_RISKS):
        raise ValueError("invalid risk codes")
    if "NONE" in risks and len(risks)!=1:
        raise ValueError("NONE must be exclusive")
    refs={e["ref"] for e in record["evidence"]}
    if (not isinstance(out["evidence"],list) or len(out["evidence"])>5 or
        any(not isinstance(x,str) for x in out["evidence"]) or
        len(set(out["evidence"]))!=len(out["evidence"]) or set(out["evidence"])-refs):
        raise ValueError("invalid evidence references")

def verifier_input(record: dict, fast: dict) -> dict:
    validate_action(fast,record)
    market=[]; policies=[]; network=0
    for e in record["evidence"]:
        kind=e.get("evidence_type")
        if kind=="market_observation":
            claim=e.get("claim") or ""
            name=claim.split(":",1)[0]
            vals=dict(re.findall(r"(demand_pressure|unmet_demand|inventory_end)=(-?\d+(?:\.\d+)?)",claim))
            market.append({"kind":name,"demand":vals.get("demand_pressure"),
                           "unmet":vals.get("unmet_demand"),"inventory":vals.get("inventory_end")})
        elif kind=="policy_claim":
            policies.append({"source":e.get("source_id"),"state":e.get("policy_state"),
                             "valid":e.get("validity_evidenced"),"reliability":e.get("reliability"),
                             "used":e["ref"] in fast["evidence"]})
        elif kind=="network_topology":
            network=max(network,int(e.get("neighbor_count") or 0))
    memory=[]
    for m in record.get("memory",[])[-3:]:
        if m.get("action") is not None or m.get("success") is not None:
            memory.append({k:m.get(k) for k in ("round_index","action","success","satisfaction","regret","credibility")})
    goals=sorted(record["goals"].items(),key=lambda x:(-x[1],x[0]))[:3]
    return {"id":record["id"],"round":record["round"],"allowed":record["allowed"],
            "fast":fast,"state":record["state"],"top_goals":dict(goals),
            "uncertainty":record["beliefs"].get("uncertainty",{}),
            "policy_digest":policies,"market_digest":market,"network_count":network,
            "memory_outcomes":memory,"ontology":record["ontology"]}

def action_diagnostics(actions: list[dict], records: list[dict]) -> dict:
    by={r["id"]:r for r in records}
    for a in actions: validate_action(a,by[a["id"]])
    return {"action_support":dict(Counter(a["action"] for a in actions)),
            "mean_confidence":sum(a["confidence"] for a in actions)/len(actions),
            "mean_uncertainty":sum(a["uncertainty"] for a in actions)/len(actions),
            "collapsed_action_over_80pct":max(Counter(a["action"] for a in actions).values())/len(actions)>.8}
