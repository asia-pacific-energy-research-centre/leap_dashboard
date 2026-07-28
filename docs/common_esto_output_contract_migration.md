# Common ESTO output contract migration

## Phase 1

The dashboard has strict, explicit opt-in support for
`common_esto_output_contract.json` version `common_esto_output_contract_v1`.
The contract provides an observed-row narrow fact table and compound-keyed
Common ESTO row metadata. The loader validates the manifest, member identity,
schemas, keys, numeric values, and complete fact/metadata membership before
reconstructing the existing denormalized dashboard input.

The legacy long and wide CSV adapters remain the production default. Set
`COMMON_ESTO_USE_OUTPUT_CONTRACT=1` to select the contract and optionally set
`COMMON_ESTO_OUTPUT_CONTRACT_PATH` to an alternate manifest. A selected invalid
contract fails without falling back to legacy data.

## Phase 2 work queue

- Make mapping diagnostics use manifest-declared compressed artifacts.
- Migrate standalone mapping and transformation prototypes to shared loaders.
- Add optional economy-partition discovery and selective partition loading.
- Add full rendered-chart, publication-readiness, and all-economy equivalence gates.

Completed:

- Pipeline provenance identifies the explicitly selected contract run and warns
  when a failed or different latest Stage 3 attempt preserved an older contract.
- The mapping-pipeline health report shows selected contract identity, declared
  fact/metadata freshness, and the same preserved-contract divergence warning.
- Sankey routing QA and fixture refresh use the shared comparison-data loader,
  retain legacy defaults, and fail without fallback when a contract is selected.
- Production mapping diagnostics and the full-tree explorer already receive the
  workflow's normalized comparison frame, so they need no separate reader.

Deferred one-off readers:

- `render_transformation_rollup_diagnostics_prototype.py`
- `render_mapping_tree_explorer_prototype.py`

These investigation prototypes still read fixed artifacts directly. Migrating
them is deferred until they are promoted into a maintained production workflow.

The fixture updater still copies `common_esto_rows.csv` as a supplemental
component-membership fixture. V1 contract metadata is deliberately one row per
compound key and does not contain the component-grain fields used by mapping
diagnostics; replacing that file would require a future metadata contract.
