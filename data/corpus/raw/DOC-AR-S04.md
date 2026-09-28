# Architecture Supplement - Singapore Office

## Capacity and Scaling

Singapore Office implementation: Capacity is provisioned at twice peak traffic. Stateless services scale horizontally; stateful components scale through sharding or read-write splitting. This supplement is effective from version 2023.

## Security Design

Singapore Office implementation: The architecture follows least privilege and zero trust. Service-to-service calls require authentication and authorisation, and secrets are delivered through a key management service. This supplement is effective from version 2023.

## ADR

Singapore Office implementation: Architecture decisions are recorded as ADRs, and material changes require Architecture Review Board approval. This document describes the target architecture; the configuration repository is authoritative. This supplement is effective from version 2023.
