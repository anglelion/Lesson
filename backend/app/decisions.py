# app/decision.py
def arbitrate(findings: list[dict]) -> dict:
    # 硬性拒绝条件
    for f in findings:
        if f.get("severity") == "CRITICAL" and f.get("evidence_level") == "confirmed":
            return {"decision": "reject", "reason": f["rule_id"]}
        if f.get("type") == "tool_poisoning" and f.get("evidence_level") == "confirmed":
            return {"decision": "reject", "reason": "confirmed tool poisoning"}

    # 人工复核触发条件
    for f in findings:
        if f.get("severity") == "HIGH" and f.get("evidence_level") != "confirmed":
            return {"decision": "manual_review", "reason": f["rule_id"]}
        if f.get("type") == "tool_error":  # 关键检查失败
            return {"decision": "manual_review", "reason": "coverage gap"}

    # 辅助评分（仅用于排序，此处略）
    return {"decision": "pass", "reason": "all required checks completed"}