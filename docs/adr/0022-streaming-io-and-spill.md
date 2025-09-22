# ADR 0022: Streaming IO and Spill

## Status
Deferred

## Context
Current Osiris extractors return complete pandas DataFrames, which requires loading all data into memory. This approach does not scale to datasets of 10GB+ and can cause OOM errors. We need an iterator-first approach that supports streaming data processing while maintaining backward compatibility.

The current architecture:
- Extractors materialize full DataFrames before returning
- Writers consume entire DataFrames at once
- No spill-to-disk capability for large datasets
- Memory usage proportional to dataset size

## Decision
Introduce a `RowStream` interface as the primary data exchange format, with optional spill-to-disk capability managed by the runner.

### RowStream Interface
```python
class RowStream(Protocol):
    """Iterator[dict[str,Any]] with column schema metadata"""
    
    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Yield rows as dictionaries"""
        
    @property
    def columns(self) -> list[ColumnSchema]:
        """Column definitions with names, types, nullable flags"""
        
    @property
    def estimated_row_count(self) -> Optional[int]:
        """Estimated rows if known (for progress tracking)"""
```

### Extractor Updates
All extractors (mysql, supabase) will add streaming methods:
```python
def extract_stream(self, query: str, **options) -> RowStream:
    """Stream results without materializing full dataset"""
```

Legacy `extract()` methods remain for compatibility, internally using `extract_stream().to_dataframe()`.

### Writer Updates
Writers consume RowStream directly:
```python
def write_stream(self, stream: RowStream, **options) -> WriteResult:
    """Write from stream with configurable batch size"""
```

### Runner Orchestration
The runner connects producers to consumers and manages spill:
- Direct streaming when possible (memory-safe pipeline)
- Optional spill-to-disk via DuckDB temp tables or Parquet files
- Configurable memory thresholds and spill strategies
- Progress tracking using estimated_row_count when available

### Spill Strategies
1. **Direct streaming**: Producer → Consumer with no intermediate storage
2. **DuckDB spill**: Stream to DuckDB temp table, then stream out
3. **Parquet spill**: Stream to Parquet file(s), then stream back
4. **Adaptive**: Start with direct, spill if memory pressure detected

Spill to disk is considered an implementation detail of the runner or components, not part of the OML schema v0.1.0.

## Consequences

### Pros
- **Scalable**: Handle datasets larger than available memory
- **Memory-safe**: Predictable memory usage independent of data size
- **Progressive**: Process data as it arrives, better UX with progress indicators
- **Flexible**: Multiple spill strategies for different scenarios
- **Compatible**: Maintain backward compatibility with DataFrame path

### Cons
- **Migration effort**: Update all extractors and writers
- **Complexity**: More complex runner orchestration logic
- **Testing**: Need new test harnesses for streaming scenarios
- **Performance**: Potential overhead from iterator abstraction

## Alternatives Considered

1. **Chunked DataFrames**: Process data in DataFrame chunks
   - Rejected: Still materializes chunks, complex chunk boundary handling
   
2. **PyArrow RecordBatch**: Use Arrow format throughout
   - Rejected: Heavy dependency, not all connectors support Arrow natively
   
3. **Generator-only approach**: Pure generators without metadata
   - Rejected: Need column schema for validation and type checking

## Implementation Plan

### Phase 1: Core Interfaces
- Define `RowStream` protocol in `interfaces.py`
- Add `ColumnSchema` dataclass for metadata
- Create adapters: `DataFrameToRowStream`, `RowStreamToDataFrame`

### Phase 2: Extractor Updates
- Update MySQL extractor with cursor-based streaming
- Update Supabase extractor with pagination-based streaming
- Maintain backward compatibility via adapters

### Phase 3: Writer Updates
- Update CSV writer to consume RowStream
- Update database writers with batch insert from stream
- Add filesystem.csv_writer as reference implementation

### Phase 4: Runner Integration
- Update runner to detect and use streaming paths
- Implement spill-to-disk strategies
- Add memory monitoring and adaptive spill

### Phase 5: Testing & Documentation
- Unit tests for all streaming components
- Integration tests with large datasets
- Performance benchmarks
- Update examples to showcase streaming

## References
- ADR-0014: Component System Architecture (defines component interfaces)
- ADR-0015: Component Health Checks (component capabilities)
- ADR-0020: Connection Management (connection resolution for components)
- ADR-0021: Component Health Check Capability (component protocol patterns)

## Acceptance Criteria
- RowStream interface defined and documented
- All extractors support streaming mode
- All writers consume RowStream
- Runner orchestrates streaming pipelines
- Backward compatibility maintained
- Tests pass with 10GB+ datasets without OOM

## Implementation Notes (M1c)
The driver-based runtime introduced in M1c provides the foundation for streaming IO:
- Drivers implement the `run()` protocol which can return DataFrames or future RowStream objects
- `filesystem.csv_writer` driver is the first concrete implementation with spill-to-disk capability
- The DriverRegistry allows seamless registration of both DataFrame and streaming-based drivers
- Metrics (`rows_read`, `rows_written`) are automatically tracked for data flow visibility

## Notes on Milestone M1

**Implementation Status**: Not implemented in Milestone M1. Planned for Milestone M2.

The RowStream API and streaming IO capabilities described in this ADR have not been implemented yet:
- **No RowStream interface**: The codebase does not contain the RowStream protocol or ColumnSchema dataclass
- **No streaming extractors**: MySQL and Supabase extractors still return full DataFrames
- **No streaming writers**: Writers still consume entire DataFrames at once
- **No spill-to-disk**: No DuckDB or Parquet spill strategies implemented

Current state:
- All data processing still uses pandas DataFrames loaded fully into memory
- The driver-based runtime in M1c provides a foundation but uses DataFrames exclusively
- Memory usage remains proportional to dataset size

This feature is postponed to Milestone M2 for implementation alongside other scaling improvements.
