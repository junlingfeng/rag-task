# 架构文档 · 核心平台
## Architecture Document - Core Platform

## 数据存储 / Data Storage

核心交易数据存储于 PostgreSQL 16 主从集群，采用同步复制保证零数据丢失，读请求路由至只读副本。

Core transactional data is stored in a PostgreSQL 16 primary-replica cluster with synchronous replication for zero data loss. Reads are routed to replicas.

## 消息队列 / Messaging

异步事件通过 Kafka 传输，关键主题配置 3 副本与 acks=all，保证消息不丢失。

Asynchronous events flow through Kafka. Critical topics use 3 replicas with acks=all to prevent message loss.

## 缓存层 / Cache Layer

缓存层由 6 节点 Redis 集群组成，采用一致性哈希分片，热点数据设置 5 分钟过期时间。

The cache layer is a 6-node Redis cluster with consistent hashing sharding. Hot data expires after 5 minutes.

## 接入网关 / API Gateway

所有外部流量经统一网关 Kong 接入，网关负责认证、限流、灰度路由与访问日志采集。

All external traffic enters through the unified Kong gateway, which handles authentication, rate limiting, canary routing and access logging.

## 设计目标 / Design Goals

平台架构以高可用、可扩展与可观测为核心目标，优先保证核心交易链路的数据一致性与故障隔离能力。

The platform architecture targets high availability, scalability and observability, prioritising data consistency and fault isolation on core transactional paths.

## 分层与边界 / Layering and Boundaries

系统分为接入层、应用层、领域服务层与数据层。跨层调用须经过明确定义的接口，禁止数据层被应用层直接访问。

The system is layered into access, application, domain service and data tiers. Cross-tier calls go through defined interfaces; direct data-tier access from the application tier is prohibited.

## 容错与降级 / Fault Tolerance and Degradation

依赖外部服务时须设置超时、重试与熔断策略；降级方案需明确业务影响范围，并在演练中验证有效性。

Calls to external services require timeouts, retries and circuit breakers. Degradation plans must state business impact and be validated in drills.

## 容量与扩展 / Capacity and Scaling

容量评估按峰值流量的两倍设计，无状态服务支持水平扩展，有状态组件通过分片或读写分离提升吞吐。

Capacity is provisioned at twice peak traffic. Stateless services scale horizontally; stateful components scale through sharding or read-write splitting.
