"""EasyPark — evaluated, not implemented.

Conclusion (2026-05-21): EasyPark is **not a useful data source** for the
"cheap parking in Oslo" use case. Kept as a documented dead-end so we
don't re-investigate later.

Why not:

1. **No open API.** The official developer portal at
   https://developer.easyparkgroup.com explicitly states that all APIs
   require a commercial agreement (partner / operator / city). There is
   no public read endpoint for zones or prices.

2. **EasyPark is a payment channel, not a price catalogue.** The user
   enters a zone code from the on-site sign, and EasyPark handles the
   transaction. The actual prices belong to the operator of the spot
   (Oslo kommune, Aimo Park, Onepark, P-Norge, …), not to EasyPark.

3. **Authoritative price sources already in our plan:**
   - Oslo kommune street parking → ``oslo_kommune`` adapter
     (tariff groups 2012, 2200, 2300, …, published openly on
     https://www.oslo.kommune.no/.)
   - Garage operators → ``onepark`` / ``aimopark`` adapters.

If we later want to display "you can pay this with EasyPark" on a
result, that becomes a *payment_methods* tag on ``ParkingRecord``
rather than a separate data source.

This file intentionally has no ``fetch()`` — it's not a real adapter.
"""

from __future__ import annotations

SOURCE_TYPE = "easypark"

# Marker constant other modules can import if/when we add payment_methods
# tagging to ParkingRecord.
PAYMENT_METHOD = "easypark"
