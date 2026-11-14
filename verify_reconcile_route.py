from two_apis_app import app

print("=== COD RECONCILIATION ROUTES ===")
for rule in app.url_map.iter_rules():
    endpoint = rule.endpoint.lower()
    route = rule.rule.lower()
    if "reconcile" in endpoint or "reconcile" in route:
        print(rule.endpoint, "->", rule.rule, sorted(rule.methods))
