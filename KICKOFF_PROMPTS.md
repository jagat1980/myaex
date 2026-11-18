# Prompts to paste into Antigravity 2.0 (one per stage)

Open this folder as a project. Set permissions: terminal = ask, file edits = allowed inside project,
network = allow only your cloud CLIs and package registries.

## Stage 0 – alignment (run first)
/grill-me Read AGENTS.md, docs/inputs.yaml, docs/ontology.md and docs/STAGES.md. List every TODO
in inputs.yaml and any ambiguity that would block stages 1-6. Do not write code yet.

## Stage 1
/plan Execute Stage 1 from docs/STAGES.md using the deploy-neo4j skill. Produce the plan artifact,
wait for my approval, then implement. Show every kubectl/helm command before running it.

## Stage 2
/plan Execute Stage 2 using the build-connector skill, starting with `itsm`, then solarwinds, azure,
bigfix, backup. Use subagents for connectors in parallel after itsm is done. Stop after each
connector's integration test and summarise results.

## Stage 3-4
/plan Execute Stages 3 and 4 using the entity-resolution skill. Report resolution rate, conflict
count and a sample of 20 resolved CIs as an artifact.

## Stage 5
/plan Execute Stage 5 using the context-graph-mcp skill. Include test results and
docs/AEX_REGISTRATION.md.

## Stage 6
/plan Execute Stage 6 using the validate-graph skill and give a go/no-go.
