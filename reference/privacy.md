# Tracked artifact privacy

The `tracked-privacy` gate requires the operator's prohibited-identity catalog.
Account names, host names, home-path identities, email values and explicit identity overrides match everywhere.
The prohibited catalog also matches everywhere.

Git display names retain their provenance. A name supplied only by Git matches in explicit identity or attribution contexts.
These include author/account fields, authored-by statements and parenthesized role labels.
An independent strict source takes precedence over this contextual treatment.
No product-name allowlist applies.

This rule permits product references that share a Git display name.
It can also permit a bare personal name outside attribution when Git supplies the only identity evidence.
Operators can declare such names through the existing explicit identity setting or prohibited catalog for unconditional matching.
Missing or malformed catalog behavior remains unchanged.
