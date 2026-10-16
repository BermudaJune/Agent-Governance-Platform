# Autonomous MCP Capability Growth Spec

## Background

The platform can identify missing tools during Leader planning, but it cannot currently acquire and activate a new executable capability without a person defining a tool executor in advance. MCP server configuration exists, while the runtime connection and dynamic tool registration path is not implemented.

This feature lets the platform grow new, usable tools from a controlled catalog of reviewed public MCP servers. The first release favors reliable automatic operation over unrestricted Internet package discovery.

## Goals

- Let the Leader recognize that a planned task cannot be completed with currently available tools.
- Find a suitable MCP server from a controlled public catalog without requiring the user to configure each tool individually.
- Automatically install, start, inspect, verify, and attach no-secret low-risk capabilities to the Agent that needs them.
- Pause with a precise configuration request when a selected capability requires credentials or other user-provided settings.
- Keep dynamically acquired tools inside the platform's existing policy, approval, audit, and Session lifecycle.
- Make capability acquisition observable in the API and web console.

## Functional Requirements

- F1: The controlled catalog shall describe reviewed public MCP servers, their provided capabilities, installation source, pinned version, launch requirements, credential requirements, supported platforms, risk classification, and health-check expectations.
- F2: During planning, the Leader shall compare required task capabilities with tools already available to the assigned Agent and emit explicit capability gaps.
- F3: For each capability gap, the system shall search the controlled catalog and rank compatible candidates by capability match, platform compatibility, credential availability, risk, and operational status.
- F4: The system shall automatically select a uniquely suitable low-risk candidate. Ambiguous or unsupported matches shall remain visible as unresolved gaps instead of being guessed.
- F5: A selected no-secret candidate shall be installed or prepared automatically with its declared version pinned. Repeated requests shall reuse a healthy existing installation.
- F6: The system shall start the selected MCP server, complete protocol initialization, discover its tools, and preserve the server-provided tool schemas.
- F7: Discovered tools shall be registered as executable runtime tools with collision-safe identities and linked to their catalog entry, server instance, version, and discovered schema.
- F8: Before attachment, the system shall verify that the server is healthy and that the discovered tools satisfy the requested capability. Failed verification shall leave the gap unresolved and record a diagnostic reason.
- F9: Verified tools shall be attached only to the Agent and Session that requested the capability. Session-scoped grants shall be revocable and shall not silently become global grants.
- F10: Dynamic tool calls shall pass through the same policy, approval, event, observation, and artifact recording path as built-in tools.
- F11: Catalog entries classified as low-risk and requiring no credentials shall complete discovery, installation, verification, and Session attachment without per-tool human approval.
- F12: When credentials or user configuration are required, the system shall not request secret values in task text or persist them in ordinary configuration. It shall report the exact environment-variable names and non-secret settings required, then allow acquisition to resume after they become available.
- F13: The API and web console shall expose acquisition status, including capability gap, selected server, installation state, connection health, discovered tools, verification outcome, required configuration, and assigned Agent.
- F14: Operators shall be able to disable a catalog entry, stop an active MCP server, revoke its Session grants, and retry a failed acquisition.
- F15: The initial controlled catalog shall contain a small set of useful public MCP servers that can be exercised without service credentials, including public documentation lookup and local workspace-oriented capabilities where platform support permits.

## Non-Functional Requirements

- N1: Package versions and catalog definitions shall be deterministic and reviewable; automatic installation shall not use an unconstrained latest version.
- N2: MCP startup, initialization, tool discovery, verification, and calls shall have bounded timeouts and output limits.
- N3: A failure in one MCP server shall not prevent built-in tools or other MCP servers from operating.
- N4: Secrets shall be resolved at runtime from named secret sources and shall not be returned by APIs, written to audit payloads, or included in model prompts.
- N5: Server instructions and tool results shall be treated as untrusted external content and clearly separated from platform policy and system instructions.
- N6: All acquisition state transitions shall be auditable and attributable to the requesting Leader, Agent, Session, catalog entry, and pinned version.
- N7: The implementation shall preserve compatibility with existing configured tools, Skills, runs, approvals, and scripted tests.
- N8: Automatic installation and execution shall be limited to controlled catalog entries in this release.

## Out Of Scope

- Searching arbitrary npm, PyPI, GitHub, or general web results for unknown MCP servers.
- Automatically executing an MCP server that is not present and enabled in the controlled catalog.
- Automatically creating or purchasing third-party service accounts or credentials.
- Passing secrets through Leader prompts, Skill content, task descriptions, or ordinary YAML configuration.
- Full support for MCP resources, prompts, sampling, or elicitation; the first release covers MCP tool discovery and invocation.
- Permanently granting a dynamically acquired tool to every Agent.
- Allowing a Skill document to install or execute arbitrary code by itself.
- Guaranteeing installation on every operating system when a catalog entry does not support that platform.

## Acceptance Criteria

- AC1: Given a Leader plan requiring a cataloged no-secret capability that no assigned Agent currently has, the platform automatically identifies the gap, selects the matching server, prepares it, discovers and verifies its tools, grants the matching tool to the Agent for the Session, and continues execution without per-tool approval.
- AC2: Repeating AC1 reuses the existing healthy installation and does not reinstall the same pinned package.
- AC3: Given a cataloged capability that requires a missing credential, the run pauses with the exact required environment-variable names and non-secret configuration fields; no secret appears in model prompts, API responses, events, or persisted ordinary configuration.
- AC4: Given multiple equally suitable candidates or no compatible candidate, the platform records an unresolved gap with candidate or diagnostic details and does not execute an arbitrary package.
- AC5: Given a server that installs but fails startup, initialization, discovery, or verification, the platform records the failed stage, preserves the rest of the run state, and offers a retry without granting unusable tools.
- AC6: A dynamically discovered tool has a collision-safe identity, retains its original JSON schema and provenance, and can be called successfully through the governed tool gateway.
- AC7: A dynamic tool call produces the same policy decision, tool-call, observation, event, and artifact records applicable to an equivalent built-in tool call.
- AC8: Revoking the Session grant prevents subsequent calls by that Agent without removing unrelated servers or grants.
- AC9: Disabling a catalog entry prevents new automatic acquisitions while leaving historical audit records readable.
- AC10: The API and web console show the end-to-end acquisition state and any required configuration without exposing secret values.
- AC11: Existing built-in tool and Skill workflows continue to pass their current automated tests.
- AC12: At least one no-secret public documentation MCP scenario passes end to end from Leader capability gap through a real tool result.
