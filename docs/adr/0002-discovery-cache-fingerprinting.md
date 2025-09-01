# ADR 0002: Discovery Cache Fingerprinting

## Context
In the current Osiris Pipeline system, the discovery cache is used to store metadata about components to improve performance by avoiding repeated expensive discovery operations. However, the cache has suffered from issues related to stale entries and context mismatches, leading to incorrect or outdated component information being used. This has caused failures or inconsistencies in pipeline execution. The challenge lies in ensuring that the cache is invalidated deterministically whenever relevant aspects of the component or its environment change, while maintaining efficient cache lookups and minimizing unnecessary recomputations.

## Decision
To address these issues, we decided to implement a robust fingerprinting mechanism for the discovery cache entries. This mechanism uses a SHA-256 hash that combines multiple critical factors:

- The component type and its version to capture changes in the component implementation.
- The connection reference to account for changes in external system connectivity.
- The input options provided to the component.
- The specification schema of the component to detect structural changes.

This fingerprint serves as a unique identifier for a given component context, ensuring that cache entries are only reused when all relevant factors match exactly.

Additionally, structured logging is introduced around cache operations to facilitate debugging and monitoring of cache hits, misses, and invalidations. The cache now supports a configurable Time To Live (TTL) to allow automatic expiration of entries after a certain period, further reducing the risk of stale data.

Backward compatibility is maintained by supporting existing cache formats and gradually migrating to the new fingerprinting scheme without disrupting current deployments.

## Consequences
This approach provides several benefits:

- Improved correctness and reliability of the discovery cache by preventing stale or mismatched data usage.
- Deterministic and fine-grained cache invalidation based on comprehensive component context.
- Enhanced observability through structured logging, aiding in troubleshooting and performance tuning.
- Flexibility to configure cache TTLs according to operational needs.
- Seamless migration path preserving backward compatibility.

Trade-offs include increased complexity in cache key computation and slightly higher overhead in generating SHA-256 fingerprints. There are also security considerations to ensure that the fingerprinting process does not leak sensitive information and that the cache storage is protected.

Overall, this design positions the Osiris Pipeline to better handle component evolution and environment changes, and lays the groundwork for future integration with a centralized component registry for improved versioning and distribution.
