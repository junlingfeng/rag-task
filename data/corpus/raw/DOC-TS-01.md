# Technical Specification - Open Platform Access

## Rate Limiting

Open platform APIs are limited to 1000 QPS per tenant. Exceeding the limit returns 429 with a retry-after header.

## Authentication

The platform uses OAuth2 client credentials. Access tokens are valid for 3600 seconds and refresh tokens for 14 days.

## Pagination

List endpoints return 20 records per page by default and at most 200 per page. Requests exceeding the maximum are rejected.

## Timeouts

The API gateway times out synchronous requests after 30 seconds and returns 504. Batch workloads must use the asynchronous task API.

## Scope

This specification applies to all platform APIs, internal and external, including synchronous endpoints, asynchronous jobs and event notifications. Scope for legacy system remediation is determined separately by the Architecture Review Board.

## Design and Review

Interface designs must be submitted as a specification and peer reviewed. Cross-domain calls additionally require capacity assessment and failure impact analysis.

## Change Management

Interface changes require Architecture Review Board approval and advance notice. Breaking changes must ship as a new version with a transition period and must not silently alter existing semantics.

## Testing and Acceptance

Before release, APIs must pass contract tests, exception-path tests and load tests with a published report. APIs that fail acceptance must not be exposed to consumers.
