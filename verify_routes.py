from two_apis_app import app

print("=== SETTLEMENT / HANDOVER ROUTES ===")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if "settlement" in rule.endpoint.lower() or "handover" in rule.endpoint.lower():
        print(rule.endpoint, "->", rule.rule)
