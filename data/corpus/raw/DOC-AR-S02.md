# Architecture Supplement - Beijing Branch

## Layering and Boundaries

Beijing Branch implementation: The system is layered into access, application, domain service and data tiers. Cross-tier calls go through defined interfaces; direct data-tier access from the application tier is prohibited. This supplement is effective from version 2021.

## Fault Tolerance and Degradation

Beijing Branch implementation: Calls to external services require timeouts, retries and circuit breakers. Degradation plans must state business impact and be validated in drills. This supplement is effective from version 2021.

## Capacity and Scaling

Beijing Branch implementation: Capacity is provisioned at twice peak traffic. Stateless services scale horizontally; stateful components scale through sharding or read-write splitting. This supplement is effective from version 2021.
