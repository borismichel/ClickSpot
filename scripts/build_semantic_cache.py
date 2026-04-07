"""Build the semantic layer cache from HubSpot API."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resources.hubspot import HubSpotResource
from app.semantic.layer import build_semantic_layer, save_cache

token = os.environ.get("HUBSPOT_TOKEN", "")
if not token:
    print("HUBSPOT_TOKEN not set")
    sys.exit(1)

hs = HubSpotResource(access_token=token)
layer = build_semantic_layer(hs)
save_cache(layer)

for table_name, tmeta in layer.tables.items():
    enriched = sum(1 for p in tmeta.properties.values() if p.label and p.label != p.silver_column)
    total = len(tmeta.properties)
    print(f"{table_name}: {enriched}/{total} columns enriched with HubSpot labels")

    for col, p in tmeta.properties.items():
        opt_vals = [o["value"] for o in p.options[:5]] if p.options else []
        opts = f"  [values: {opt_vals}]" if opt_vals else ""
        desc = f" — {p.description}" if p.description else ""
        print(f"  {col}: \"{p.label}\"{desc}{opts}")
    print()

print(f"Associations: {len(layer.associations)} types")
