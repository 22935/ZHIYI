# Monorepo import

Origin: https://github.com/zongxi-Li/zhi-xing

Imported baseline: `c48f704b2599102775668739f8838274a2a77068` (main).
AgentOS baseline: `145726f0a08f9a9ee4acc8255d785c8f10848a5b`.

Tracked source, tests, lockfile, configuration, reports and the MIT DSH vendor
snapshot were imported. `.git`, `node_modules`, and historical diagnostic
`evidence/` were excluded. Historical report evidence references belong to the
origin repository; current integration evidence is in AgentOS artifacts.

The original repository remains intact. Vendor files and `vendor/LICENSE` /
`vendor/PROVENANCE.md` retain their original attribution. Integration changes
are restricted to the Hands boundary and AgentOS adapters; DSH vendor is unchanged.

Install/build checks from the AgentOS root:

```powershell
pnpm --dir apps/agentOS/src/hands install --frozen-lockfile
pnpm --dir apps/agentOS/src/hands typecheck
pnpm --dir apps/agentOS/src/hands test
pnpm --dir apps/agentOS/src/hands service --config C:\private\hands-service.json
```
