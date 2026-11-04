# Components

Level 2 of the skill graph: components under each concept, each
documented by a man page (level 3) pointing at the exact source file
that generated it. The full machine corpus, with every typed link,
is published as [`corpus.jsonld`](corpus.jsonld).

## Arbora

### Capabilities

- **Capabilities** — `capabilities.md`

### Glossary

- **Glossary** — `glossary.md`

### Home

- **Home** — `index.md`

### How it fits

- **How it fits** — `architecture.md`

### Interfaces

- **Interfaces** — `interfaces.md`

### Operate

- **Deployment and configuration** — `deployment.md`
- **Release-qualification runbook** — `release-qualification-runbook.md`
- **Identity and authentication** — `identity.md`
- **Capability status** — `status.md`
- **Quality gate terms** — `quality-gate-terms.md`

### Specification status

- **Specification status** — `spec-status.html`

### Start Arbora

- **Start Arbora** — `get-started.md`

### Use Arbora

- **MCP server** — `mcp-server.md`
- **REST gateway** — `gateway.md`
- **Fleet gateway** — `fleet.md`
- **Unary A2A** — `a2a.md`
- **Browser control** — `browser-control-service.md`

## Axil

### Guides

- **Agents** — `agents.md`
- **Apps** — `apps.md`
- **Design system** — `design-system.md`

### Home

- **Home** — `index.md`

### Operate

- **Operate** — `deployment.md`

### Reference

- **Features** — `features.md`
- **Knowledge extraction** — `kg-extraction.md`
- **Concept Registry** — `concepts.md`
- **Ecosystem glossary** — `glossary.md`
- **Status** — `status.md`

### Start

- **Start** — `start.md`

## Medulla

### Architecture

- **Architecture guide** — `architecture/index.md`
- **Engine internals** — `architecture/engine.md`
- **Request authority** — `architecture/request_authority.md`
- **Mutation batches** — `architecture/mutation_batch.md`
- **Change envelopes** — `architecture/change_envelope.md`
- **Canonical property schema** — `architecture/canonical-property-schema.md`
- **Modality serving** — `architecture/modality_serving.md`
- **Program optimization** — `architecture/native-program-optimization.md`
- **Distributed analytics and reasoning** — `architecture/distributed-analytics-reasoning.md`
- **Analytics program** — `architecture/analytics_program.md`
- **Numeric kernel** — `architecture/numeric_kernel.md`
- **Hot-path complexity** — `architecture/hot-path-complexity.md`
- **Market bars and trend signals** — `architecture/finance-market.md`
- **Graph backends and mirrors** — `architecture/graph-backends.md`
- **Service layer** — `architecture/service-layer.md`
- **Code intelligence** — `architecture/code-intelligence.md`
- **Vector index lifecycle** — `architecture/vector-index-lifecycle.md`
- **Ontology library and SHACL authority** — `architecture/ontology-library.md`
- **Ontology package federation** — `architecture/ontology-federation.md`
- **Epistemic Operations Protocol** — `architecture/epistemic-operations-protocol.md`
- **AIF argumentation** — `architecture/aif-argumentation.md`

### Components

- **Overview** — `components/index.md`
- **medulla.types** — `components/medulla-types.md`
- **medulla.core** — `components/medulla-core.md`
- **medulla.storage-transaction** — `components/medulla-storage-transaction.md`
- **medulla.query-reasoning** — `components/medulla-query-reasoning.md`
- **medulla.server-protocol** — `components/medulla-server-protocol.md`
- **medulla.composition** — `components/medulla-composition.md`

### For AI agents

- **For AI agents** — `https://github.com/Knuckles-Team/medulla/blob/main/AGENTS.md`

### Home

- **Home** — `index.md`

### Interfaces

- **Interface guide** — `interfaces/index.md`
- **Python and native clients** — `interfaces/clients.md`
- **Unified Query Language** — `uql.md`
- **SQL and PostgreSQL** — `interfaces/sql.md`
- **RDF, OWL, and SHACL** — `interfaces/ontology.md`
- **SPARQL** — `interfaces/sparql.md`
- **Cypher** — `interfaces/cypher.md`
- **GraphQL** — `interfaces/graphql.md`
- **Vector search** — `interfaces/vector.md`
- **Time-series** — `interfaces/timeseries.md`
- **Memory** — `interfaces/memory.md`
- **Messaging and streams** — `interfaces/messaging.md`
- **Key-value and blobs** — `interfaces/kv_blob.md`
- **Observability** — `interfaces/observability.md`

### Operate

- **Deploy the engine** — `standalone_deployment.md`
- **Deployment reference** — `deployment.md`
- **Deployment topology** — `deployment_topology.md`
- **Service mode** — `service_mode.md`
- **Operations runbook** — `operations/runbook.md`
- **Fault and restart certification** — `operations/exact-fault-restart-certification.md`
- **Release campaigns** — `operations/exact-release-campaigns.md`
- **PyPI tombstones** — `development/pypi-tombstones.md`
- **Performance certification** — `performance_certification.md`

### Reference

- **Capabilities** — `capabilities.md`
- **Concepts** — `concepts.md`
- **Cost and capacity** — `cost_model.md`
- **Transport benchmarks** — `benchmarks.md`
- **Soak and chaos benchmarks** — `benchmarks-soak.md`
- **HelixDB comparison** — `benchmarks-helix.md`
- **Quality terms** — `quality-gate-terms.md`
- **Ecosystem glossary** — `glossary.md`
- **Skill graph reference** — `reference/skill-graph.generated.md`

### Start

- **Run locally** — `get-started.md`
- **Choose an engine mode** — `engine_modes.md`
- **Technical overview** — `overview.md`

### admission

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`
- **medulla.server-protocol** — `architecture/component-registry.yml#medulla.server-protocol`

### algorithms

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### alignment

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### ann

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### asof

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### asr

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### ast

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### audio

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### audit

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### backend

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### backup

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### belief

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### binaries

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`

### bindings

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### blob

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### capability

- **medulla.core** — `architecture/component-registry.yml#medulla.core`

### capability-ledger

- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### catalog

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### cdc

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### chart

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### claims

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### clients

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### cold-tier

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### columnstore

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### composition

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`
- **medulla.composition** — `architecture/component-registry.yml#medulla.composition`

### compute

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### confidence

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### consensus

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### content-addressed

- **medulla.kv-cache** — `architecture/component-registry.yml#medulla.kv-cache`

### contracts

- **medulla.types** — `architecture/component-registry.yml#medulla.types`
- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### contradiction

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### cost

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`
- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### cross-shard

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### cypher

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### datalog

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### datascience

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### decode

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### delta

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### deployment

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`
- **medulla.composition** — `architecture/component-registry.yml#medulla.composition`

### dispatch

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### document

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### durability

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`
- **medulla.storage-transaction** — `architecture/component-registry.yml#medulla.storage-transaction`

### durable

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### durable-routing

- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### embedded

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### evidence

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`
- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### exactness

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### export

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### features

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`

### federation

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### file-format

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### finance

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### fsm

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### gap-fill

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### gates

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`

### geo

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### governed-program

- **medulla.lm-program** — `architecture/component-registry.yml#medulla.lm-program`

### graph

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### graphql

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### handlers

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### iceberg

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### idempotency

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### identity

- **medulla.types** — `architecture/component-registry.yml#medulla.types`

### image

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### incarnation

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### interop

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### invariants

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### isolation

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### ivf-pq

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### javascript

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### jobs

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### justification

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### kvcache

- **medulla.kv-cache** — `architecture/component-registry.yml#medulla.kv-cache`

### lakehouse

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### lease

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`
- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### ledger

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### lifecycle

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`
- **medulla.composition** — `architecture/component-registry.yml#medulla.composition`

### linalg

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### lm-program

- **medulla.lm-program** — `architecture/component-registry.yml#medulla.lm-program`

### lod

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### lttb

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### m4

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### membership

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### metrics

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### modality

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### mutation

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### mutation-batch

- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### numeric

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### obda

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### observability

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### occ

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### ohlc

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### ontology

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### opq

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### optimization

- **medulla.lm-program** — `architecture/component-registry.yml#medulla.lm-program`

### otel

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### oxrdf

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### paging

- **medulla.kv-cache** — `architecture/component-registry.yml#medulla.kv-cache`

### parquet

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### persistence

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### physical-state-authority

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### piper

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### placement

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### planner

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### policy-lease-consumer

- **medulla.server-protocol** — `architecture/component-registry.yml#medulla.server-protocol`

### pre-commit

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`

### pregel

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### private-payload

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### promql

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### protocol

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`
- **medulla.server-protocol** — `architecture/component-registry.yml#medulla.server-protocol`
- **medulla.types** — `architecture/component-registry.yml#medulla.types`
- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### provider

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### pyo3

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### python

- **medulla.embedded-bindings** — `architecture/component-registry.yml#medulla.embedded-bindings`

### qaoa

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### quantum

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### query

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`
- **medulla.query-reasoning** — `architecture/component-registry.yml#medulla.query-reasoning`

### raft

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### rbac

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### rdf

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### reasoning

- **medulla.query-reasoning** — `architecture/component-registry.yml#medulla.query-reasoning`

### redb

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`
- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### release

- **medulla.binary-composition** — `architecture/component-registry.yml#medulla.binary-composition`

### replication

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### resource

- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### restore

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### rls-cache

- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### rollup

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### row-visibility

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### rowset

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### s3

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### scheduler

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### scope-binding

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### self-improvement

- **medulla.lm-program** — `architecture/component-registry.yml#medulla.lm-program`

### semantic-indexing

- **medulla.query-reasoning** — `architecture/component-registry.yml#medulla.query-reasoning`

### semantic-store

- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### server

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`
- **medulla.server-protocol** — `architecture/component-registry.yml#medulla.server-protocol`

### shacl

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### sharding

- **medulla.cluster-replication** — `architecture/component-registry.yml#medulla.cluster-replication`

### shards

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`

### shex

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### slow-query

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### sparql

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### speech

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### sql

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### sqlite

- **medulla.lake-interop** — `architecture/component-registry.yml#medulla.lake-interop`

### stabilizer

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### statechart

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

### statevector

- **medulla.quantum** — `architecture/component-registry.yml#medulla.quantum`

### storage

- **medulla.storage-transaction** — `architecture/component-registry.yml#medulla.storage-transaction`

### stream

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### tenancy

- **medulla.core** — `architecture/component-registry.yml#medulla.core`
- **medulla.graph-core** — `architecture/component-registry.yml#medulla.graph-core`

### tensor

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### text

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### tiered-cache

- **medulla.kv-cache** — `architecture/component-registry.yml#medulla.kv-cache`

### tiles

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### time-bucket

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### timeseries

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### tms

- **medulla.epistemic** — `architecture/component-registry.yml#medulla.epistemic`

### tracing

- **medulla.observability** — `architecture/component-registry.yml#medulla.observability`

### transaction

- **medulla.persistence** — `architecture/component-registry.yml#medulla.persistence`
- **medulla.storage-transaction** — `architecture/component-registry.yml#medulla.storage-transaction`

### transaction-kernel

- **medulla.mutation-store** — `architecture/component-registry.yml#medulla.mutation-store`

### transport

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`

### tree-sitter

- **medulla.compute** — `architecture/component-registry.yml#medulla.compute`

### tsdb

- **medulla.timeseries** — `architecture/component-registry.yml#medulla.timeseries`

### tts

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### udf

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### validation

- **medulla.rdf-semantics** — `architecture/component-registry.yml#medulla.rdf-semantics`

### vector-index

- **medulla.numeric-ann** — `architecture/component-registry.yml#medulla.numeric-ann`

### video

- **medulla.modality** — `architecture/component-registry.yml#medulla.modality`

### viewspec

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### viz

- **medulla.viz** — `architecture/component-registry.yml#medulla.viz`

### wasm

- **medulla.query-plan** — `architecture/component-registry.yml#medulla.query-plan`

### whisper

- **medulla.speech-providers** — `architecture/component-registry.yml#medulla.speech-providers`

### wire

- **medulla.server-dispatch** — `architecture/component-registry.yml#medulla.server-dispatch`
- **medulla.wire-contracts** — `architecture/component-registry.yml#medulla.wire-contracts`

### work-item

- **medulla.job-plane** — `architecture/component-registry.yml#medulla.job-plane`

## Meristem

### Home

- **Home** — `index.md`

## Overstory

### Guides

- **Architecture** — `architecture.md`
- **Agents and events** — `agents.md`
- **Understory workspace** — `atlas.md`
- **Apps and Markets** — `apps.md`
- **Capability Workbench** — `capability-workbench.md`
- **Design system** — `design-system.md`
- **Refresh screenshots** — `screenshots.md`

### Home

- **Home** — `index.md`

### How it fits

- **How it fits** — `ecosystem.md`

### Operate

- **Operate** — `deployment.md`

### Reference

- **Features and APIs** — `features.md`
- **Knowledge extraction** — `kg-extraction.md`
- **Concept registry** — `concepts.md`
- **Ecosystem glossary** — `glossary.md`
- **Status** — `status.md`

### Start

- **Start** — `start.md`

## Scion SDK

### Architecture

- **Overview** — `architecture.md`
- **Connectors & ingestion** — `architecture/connectors-and-ingestion.md`
- **Bidirectional ETL hub** — `architecture/etl-hub.md`
- **Chunked async drain** — `architecture/chunked-async-drain.md`
- **Content-aware ingestion** — `architecture/content-aware-ingestion.md`
- **Camunda + ARIS integration** — `architecture/camunda-aris-integration.md`
- **CISO Assistant integration** — `architecture/ciso-assistant-integration.md`
- **Privacy-safe external ingestion** — `architecture/privacy-safe-ingestion.md`
- **Universal external graph connectors** — `architecture/universal-graph-connectors.md`

### Build your first connector

- **Build your first connector** — `tutorial.md`

### Capabilities

- **Capabilities** — `capabilities.md`

### Components

- **Connector servers** — `connector-servers.md`
- **Content over MCP** — `content-over-mcp.md`
- **Schema disclosure** — `schema-disclosure.md`
- **Source synchronization** — `connector-sync.md`
- **Repository ingestion** — `repository-ingestion.md`
- **Extension ports** — `extension-ports.md`
- **Connector certification** — `connector-certify.md`
- **HTTP clients** — `http-clients.md`
- **Credentials** — `credentials.md`

### Home

- **Home** — `index.md`

### Reference

- **Conformance kit** — `conformance-kit.md`
- **Quality gates** — `quality-gates.md`
- **Ecosystem glossary** — `glossary.md`
- **Skill graph reference** — `reference/skill-graph.generated.md`

### Status

- **Status** — `status.md`

## Tuig

### Agents & Workflows

- **Agent View** — `agent_view.md`
- **Goal Command** — `goal_command.md`
- **Agents & Issues** — `agents.md`

### Architecture

- **Architecture** — `architecture.md`

### Configuration

- **Configuration** — `configuration.md`

### Deployment

- **Deployment** — `deployment.md`

### Design system

- **Design system** — `design-system.md`

### Development

- **Development** — `development.md`

### Features

- **Features** — `features.md`

### Home

- **Home** — `index.md`

### Reference

- **Concepts** — `concepts.md`

### Screenshots

- **Screenshots** — `screenshots.md`

### Sessions & State

- **Session Management** — `session_management.md`

### Start

- **Start** — `start.md`

### Status

- **Status** — `status.md`
