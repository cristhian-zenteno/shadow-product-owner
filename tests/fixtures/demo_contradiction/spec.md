# Inventory Sync Feature

## Objective
Keep product inventory counts in sync between the online store and the warehouse system.

## Current Architecture Note
The warehouse management system runs entirely offline on a local network with no internet access.

## Business Rules
- Inventory levels must be updated in real time when orders are placed
- The system should use cloud-based webhooks to push inventory updates
- Sync must work even when the warehouse is temporarily disconnected from the internet
- Inventory discrepancies of more than 5 units must trigger an alert

## Contradiction
The spec requires both:
1. Real-time cloud webhook updates (requires internet)
2. Offline warehouse operation (no internet access)
These two requirements are mutually exclusive and must be resolved with the PO.
