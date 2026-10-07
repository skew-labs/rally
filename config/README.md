# Integration metadata

This directory contains the runtime's public interoperability inputs, not account state or operating plans.

- `tokens.json` and `protocols.json`: address-based Monad registry inputs. The live collectors enrich these inputs; an entry does not establish executable liquidity.
- `venue-inventory.csv`: public venue names, categories and official links. Internal review/action columns are excluded.
- `venue-pins.json`, `leverup-pins.json` and venue-specific manifests: observed chain 143 deployments, bytecode/proxy identities and interface constraints used to fail closed on changes.
- `venues/`, `nadfun/`, `drake/`, `leverup-abi.json`: external interface definitions used by the adapters.

Deployment pins are observations at the blocks recorded in each manifest, not permanent guarantees. Review against current official source/interfaces before replacing a failed pin. Do not weaken code-identity checks to make an unavailable route appear connected.

Source ABIs/metadata retain applicable upstream rights. No provider credential, private key, production wallet session or private account database belongs in this directory.
