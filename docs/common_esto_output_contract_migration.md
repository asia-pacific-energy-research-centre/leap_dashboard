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
- Make pipeline provenance use contract run identity and member checksums.
- Make the mapping-pipeline health report contract-aware.
- Migrate standalone mapping and transformation prototypes to shared loaders.
- Add optional economy-partition discovery and selective partition loading.
- Add full rendered-chart, publication-readiness, and all-economy equivalence gates.
