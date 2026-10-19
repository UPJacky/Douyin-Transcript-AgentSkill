# Dynamic lease scope limitation

`DynamicLeaseCoordinator` is an offline lifecycle model. Its fake-session
checks do not prove that two lease sessions can coexist through native WFP.

The current compiler projection assigns each lease-dynamic filter a distinct
lease provider key and retains the persistent baseline `SublayerKey`.
`PersistentBaselineCoordinator.EnsureReady` reads the complete provider/
sublayer snapshot before each lease and `ValidateExistingOwnership` rejects
every filter in the baseline sublayer that is not a recognized persistent
baseline filter. `NativeWfpPolicyStoreAdapter` likewise validates the
enumerated scoped snapshot as baseline-only. Therefore, after a native first
lease installs filters in the shared sublayer, the next baseline read would
encounter those dynamic filters and fail closed. The current fake store does
not merge its fake session filters into the baseline snapshot, so the two-lease
harness case does not exercise this native interaction. A separate negative
compatibility fixture injects the first lease's filters into the baseline
snapshot and verifies that the second open is rejected without allocating or
closing an ambiguous session; this checks fail-closed behavior, not native
WFP coexistence.

Before wiring this coordinator to WFP, the design must establish a positively
separate ownership/readback scope for persistent baseline objects and dynamic
lease objects. A native implementation must not silently drop nonpersistent
filters from a broad provider/sublayer enumeration: it needs an explicit,
verifiable scope boundary and tests showing that unrelated, foreign, stale,
and concurrently active lease objects cannot be hidden or misclassified.
Until then, this code covers plan validation, per-handle lifecycle, dynamic
provider/filter projections, ACL readback checks, failure retention, and
worker-drain ordering only; it is neither a native isolation claim nor
deployable capture behavior.

## Scope design review (2026-10-13; source contract, native candidate)

The simplest-looking split—one dynamic provider and sublayer per lease—must not
be adopted without arbitration tests. The compiler currently places its exact
permit and catch-all block filters in one sublayer, where filter weight
determines their order. WFP evaluates every sublayer at a layer, and its basic
arbitration makes Block override Permit; moving a permit to another sublayer
can therefore change whether it survives the baseline block. Sublayer weight
also determines evaluation order. See Microsoft's [filter arbitration]
(https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration) and
[FWPM_SUBLAYER0 weight documentation]
(https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_sublayer0).

The least-semantic-change candidate for a native prototype is one unique
dynamic provider per lease, with that lease's dynamic filters still attached
to the existing persistent baseline sublayer. A WFP provider is a management
association and does not itself affect runtime packet processing ([WFP object
model](https://learn.microsoft.com/en-us/windows/win32/fwp/object-model)). The
offline contract now derives a stable lease-specific provider key, projects
the provider as non-persistent, binds dynamic filters to it while retaining
the baseline sublayer key, and requires session readback to include exact
provider and filter projections plus service-only provider/filter ACL evidence.
The fake harness checks that incomplete, mismatched, or broad-ACL readbacks
close the session.

This source contract does not solve the baseline reader's shared-sublayer
conflict. A complete sublayer enumeration includes filters from the dynamic
providers, while `PersistentBaselineCoordinator` and
`NativeWfpPolicyStoreAdapter` still reject foreign-provider filters in that
sublayer. The second lease remains unverified and will fail closed when native
baseline enumeration exposes a first lease's filters. A native implementation
must enumerate and classify the complete shared sublayer, separate the
persistent baseline provider's exact rows from registered active lease
providers, and reject every unregistered, foreign, stale, wrong-lifetime, or
wrong-sublayer row. Each lease session must create and read back its dynamic
provider and filters on the same dynamic handle, verify ownership and ACLs, and
confirm removal on close.

This candidate still has a hard visibility constraint. The filter enumeration
template can select a provider but has no sublayer-key or session-key member
([FWPM_FILTER_ENUM_TEMPLATE0]
(https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter_enum_template0)).
The native reader must therefore obtain enough rows to classify the shared
sublayer; it cannot ask WFP for “all providers in just this sublayer” through
that template. Enumeration also returns only filters for which the caller
has READ access ([FwpmFilterCreateEnumHandle0]
(https://learn.microsoft.com/en-us/windows/win32/api/fwpmu/nf-fwpmu-fwpmfiltercreateenumhandle0),
[WFP access control]
(https://learn.microsoft.com/en-us/windows/win32/fwp/access-control)). A
complete-scope claim needs approved container/object ACLs plus native tests
that prove the service identity can see every relevant row; hidden foreign
objects remain a fail-closed limitation until then.

Alternative per-lease sublayers remain possible only after a disposable native
WFP test proves the compiler's allow/block behavior, weight ordering, and
interaction with Windows Firewall and other providers. Do not change permit
hardness or sublayer weights to make the test pass without a separately
reviewed policy decision. No native backend, ACL approval, arbitration test,
or host WFP/BFE change is included in this source slice.

## Offline shared-sublayer contract (2026-10-13)

`SharedSublayerReadbackContract` now defines a closed-world managed DTO for a
complete merged view: the persistent service provider and baseline filters,
every coordinator-registered active lease provider and filter, the fixed
shared sublayer, and exact owner/DACL evidence for each object. It derives the
expected baseline from the compiler and the expected dynamic objects from
`DynamicLeaseCoordinator.GetActiveReadbackExpectations()`. Missing, duplicate,
external, stale, wrong-provider, wrong-sublayer, persistent-lifetime, ACL
mismatch, and incomplete rows fail closed. The harness merges fake baseline
rows with every still-open fake dynamic session, verifies two active leases,
then checks that a closed lease disappears and a stale re-injected row is
rejected.

This is an independent offline DTO and validator; there is no native producer
and neither `NativeWfpPolicyStoreAdapter` nor the native readback reader is
wired to it. The merged fixture synthesizes ACL evidence and cannot prove that
a native WFP enumerator sees hidden objects, that BFE transaction views are
stable across providers, that provider/filter lifetimes match actual WFP
semantics, or that close removed native objects. `FWPM_FILTER0` does not expose
a session ID, so the contract binds observed rows to a registered lease by
provider identity and exact filter set, not by native session identity. The
baseline coordinator still consumes a baseline-only store snapshot and can
reject a real shared-sublayer view containing dynamic filters. Production P2
remains fail closed pending a native full-scope producer, visibility/ACL proof,
transaction integration, real close-time removal checks, and disposable-VM
arbitration and multi-lease tests.

## Enumeration visibility and fresh dedicated sublayer candidate (2026-10-13)

The fixed shared sublayer cannot be certified complete through the current user-mode
enumerator. `FWPM_FILTER_ENUM_TEMPLATE0` has no sublayer-key member, and filter enumeration
returns only rows readable by the caller; container enumeration also requires ENUM access.
The native reader's `EnumerationCompletenessUnverified` marker is therefore intentional.
Enumerating all visible filters and locally selecting `subLayerKey` bounds the candidate
set, but it cannot prove that a READ-denied row was absent. Querying a security descriptor
by key does not discover unknown keys.

A candidate for disposable-VM evaluation is a new, service-created dedicated sublayer with
a fresh GUID/key. The service must fail closed if the key already exists instead of adopting
an unknown pre-existing object. Give the trusted service only the sublayer link/enum/read
rights that native enforcement and readback tests prove necessary; keep LocalSystem as
owner and protect the DACL. Service-created filters need explicit service READ/READ_CONTROL
access for readback, while filter creation still needs the required container ADD/ADD_LINK
rights. Do not treat the current prototype `GRGWGX` mask as minimum-rights approval.

The native producer should read security descriptors for the filter container and known
service objects, then page through enumeration and compare every visible object with the
baseline and coordinator's active lease registry inside one explicit read transaction.
Unknown rows, API failures, mismatched ACLs, or bounds reached before completion remain
fail closed. A disposable VM must demonstrate that a READ-denied legacy filter is silently
omitted by ordinary enumeration, and that a low-privilege principal cannot attach a filter
to the fresh sublayer. Also exercise BFE transaction consistency, arbitration, service
restart, concurrent leases, and native close-time deletion. This design trusts
administrators, LocalSystem, and kernel drivers; it does not retrofit proof for the old
shared sublayer or remove the need for live native tests. No WFP/BFE or host policy was
changed for this candidate.
