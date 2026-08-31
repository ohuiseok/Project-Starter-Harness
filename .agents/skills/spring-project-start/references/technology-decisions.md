# Technology Decisions

Use this catalog to create a project-specific choice flow. It is a decision
model, not an exhaustive technology list.

## Interaction Contract

Start with a compact recommended profile instead of a long questionnaire.

```text
추천 구성을 만들었습니다.

- Application: REST API
- Security: session login
- Data: PostgreSQL + JPA + Flyway
- Structure: modular monolith
- Delivery: executable JAR

1. 추천 구성으로 진행
2. 항목별 수정
3. 기타 / 원하는 구성을 직접 설명
```

When editing one decision, ask one question at a time:

```text
화면 제공 방식을 선택해 주세요.

1. 추천: Thymeleaf — Spring MVC와 단순하게 통합됩니다.
2. JSP — 기존 JSP 자산이나 WAR 운영 환경에 적합합니다.
3. 별도 SPA — 프론트엔드와 API를 분리합니다.
4. 기타 / 직접 입력
```

Always:

- derive the recommendation from product needs;
- offer 2 to 4 relevant representative choices plus free-form input;
- allow `잘 모르겠어` to accept the recommendation;
- avoid asking for facts already supplied by the user or target evidence;
- explain immediate impact, not a general technology lecture;
- show progress such as `기술 선택 3/6` when more questions remain;
- allow `이전 선택 변경` and `나머지는 추천` at any point.

## Decision Status

| Status | Meaning |
|---|---|
| `NOW` | Required before the next implementation milestone |
| `SOON` | Required for a near-term roadmap stage |
| `DEFERRED` | Safe to decide when a triggering requirement appears |
| `NOT_USED` | Explicitly excluded for the current scope |
| `UNKNOWN` | Evidence or user intent is insufficient |

## Decision Axes

Ask only axes that matter now. Preserve custom answers even when they do not
appear in the representative examples.

### 1. Runtime and Build

- language: Java, Kotlin, Groovy, custom
- Java/runtime version
- build: Gradle Groovy DSL, Gradle Kotlin DSL, Maven, custom
- packaging: executable JAR, WAR, native image, custom

Usually decide language, runtime version, and build `NOW`. Decide packaging
`NOW` only when UI or deployment requirements depend on it.

### 2. Application Shape and Interface

- REST or GraphQL API
- server-rendered MVC
- JSP or Thymeleaf
- separate SPA/mobile client
- batch, scheduler, event consumer, CLI
- mixed application

Derive follow-up questions from actual channels. Do not ask about a view engine
for an API-only service.

### 3. Security and Identity

- no application security
- session authentication
- JWT or opaque access token
- OAuth2/OIDC with an external identity provider
- API key or machine credential
- mixed authentication by channel

First determine users, trust boundary, and client type. Do not equate every API
with JWT. Record authorization needs separately from authentication.

### 4. Data and Persistence

- no persistent store yet
- relational: H2, PostgreSQL, MySQL/MariaDB, Oracle, SQL Server, custom
- non-relational: document, key-value, search, graph, time-series, custom
- access: Spring Data JPA, JDBC, MyBatis, Spring Data variant, custom
- schema change: Flyway, Liquibase, externally managed, custom
- topology: single store, multiple data sources, read/write split,
  tenant-specific routing, database per service, custom

For multiple stores, ask the responsibility of each store and transaction
boundary. Do not describe several stores as one atomic transaction without
evidence.

### 5. Code and Deployment Structure

- single module
- layered monolith
- modular monolith / multi-module build
- microservices
- custom or hybrid

Treat MSA as an operational choice, not only a package layout. Ask whether
independent ownership, deployment, scaling, and failure isolation are required.

### 6. Integration and Asynchrony

- none yet
- HTTP/REST, GraphQL, gRPC
- Kafka, RabbitMQ, JMS, custom messaging
- scheduled polling, file exchange, custom

Decide only integrations required by the current or near-term workflow. Record
delivery, retry, ordering, and idempotency expectations when messaging matters.

### 7. Delivery and Operations

- local only, traditional server, container, Kubernetes, serverless, custom
- environment configuration and secret provider
- logging, metrics, traces, health checks
- CI/CD and release strategy

Operational requirements may constrain packaging, architecture, database, and
security choices. Ask them early when the user names a production environment.

### 8. Verification

- unit and Spring integration tests
- database integration with embedded/fake or Testcontainers
- API, contract, end-to-end, performance, security, migration tests

Choose verification based on risk and architecture. A microservice or multi-DB
decision without integration-level verification is incomplete.

## Confirmation Summary

Before implementation, show:

- selected `NOW` decisions and reasons;
- `SOON` and `DEFERRED` decisions with their trigger;
- custom inputs as interpreted;
- compatibility findings;
- immediate dependencies and generated project shape;
- remaining `UNKNOWN` that does not block the milestone.

Then distinguish these results:

- `PROFILE_VALID`: the structured profile can be parsed and references valid IDs;
- `COMPATIBILITY_RESULT`: the selected combination is supported, needs review,
  or conflicts;
- `GENERATION_READY`: all generation-blocking decisions, mappings, compound
  definitions, and user confirmation are complete.

Only `GENERATION_READY: yes` permits project generation. A profile can be valid
and compatible while still incomplete.
