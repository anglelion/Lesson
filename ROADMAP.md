# MCP Audit delivery roadmap

Development is organized as eight sequential checkpoints on `feat/mcp-audit-v1`.
The checkpoints are implementation milestones, not stable releases. Formal testing is deferred
until all eight checkpoints are implemented; the project is released as `v1.0.0` only after the
final verification and repair pass succeeds.

| Checkpoint | Scope | Status |
| --- | --- | --- |
| v0.1 | Project foundation, configuration, containers, migrations | Complete |
| v0.2 | Correct Git snapshots and reliable task lifecycle | Planned |
| v0.3 | Normalized evidence and decision arbitration | Planned |
| v0.4 | Static, secret, and dependency security checks | Planned |
| v0.5 | MCP-specific semantic security checks | Planned |
| v0.6 | Transport checks and untrusted-repository isolation | Planned |
| v0.7 | API completion, frontend, progress, and reports | Planned |
| v0.8 | Deployment packaging, documentation, and demo fixtures | Planned |
| v1.0.0 | Unified test, repair, acceptance, and release | Blocked by v0.1-v0.8 |
