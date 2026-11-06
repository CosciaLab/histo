# All parameters

Every parameter, grouped as in `nextflow_schema.json`. Each shows its type and default; the
parameters most runs change are explained by topic in [Parameters](parameters.md).

A switch shown as default `false` is unset in the schema: nf-core pipelines leave a switch that
is off as `null`, which the pipeline reads as `false`. The params templates in `assets/` show it
as `null`.

The run checks combinations when it starts; a **Requires**, **Conflicts** or **Ignored unless**
line under a parameter states its rule.

% source: nextflow_schema.json
% source: docs/usage.md#parameters (null means off or unset)

```{include} ../_generated/parameters.md

```
