# ADR 0023: Remote Object Store Writers

## Status
Deferred

## Context
With RowStream support from ADR-0022, Osiris can handle large datasets efficiently. However, current writers only support local filesystem and databases. Modern data architectures require direct writing to cloud object stores (S3, Azure Blob Storage, Google Cloud Storage) for data lake scenarios. We need writers that can stream data directly to these remote stores without requiring local staging.

Current limitations:
- No native support for cloud object stores
- Must stage locally then upload separately
- No multipart upload for large files
- Manual credential management for cloud providers

## Decision
Add dedicated cloud object store writers that consume RowStream and write directly to remote storage using multipart uploads for large files.

### Component Structure
Create three new component families:
- `s3.csv_writer`: Write CSV to Amazon S3
- `azure_blob.csv_writer`: Write CSV to Azure Blob Storage
- `gcs.csv_writer`: Write CSV to Google Cloud Storage

### CSV Contract (Deterministic)
All cloud writers follow the same CSV contract as `filesystem.csv_writer`:
- **Delimiter**: Configurable (default: comma)
- **Header**: Always include column names as first row
- **Encoding**: UTF-8
- **Line endings**: LF only (Unix-style)
- **Column order**: Stable, preserves RowStream order
- **Quoting**: RFC 4180 compliant
- **Null handling**: Empty string for NULL values

### Configuration Schema
```yaml
# OML step configuration (non-secret only)
steps:
  - name: write_to_s3
    type: s3.csv_writer
    config:
      bucket: my-data-lake
      object_key: data/customers/2024/${RUN_ID}.csv
      delimiter: ","
      region: us-east-1  # Optional, can be in connection
      storage_class: STANDARD  # Optional: STANDARD, GLACIER, etc.
      
  - name: write_to_azure
    type: azure_blob.csv_writer
    config:
      container: data-lake
      blob_name: customers/2024/${RUN_ID}.csv
      delimiter: ","
      tier: Hot  # Optional: Hot, Cool, Archive
      
  - name: write_to_gcs
    type: gcs.csv_writer
    config:
      bucket: my-data-lake
      object_name: data/customers/2024/${RUN_ID}.csv
      delimiter: ","
      storage_class: STANDARD  # Optional
```

### Connection Resolution
Secrets managed via `osiris_connections.yaml`:
```yaml
connections:
  s3:
    prod:
      aws_access_key_id: ${AWS_ACCESS_KEY_ID}
      aws_secret_access_key: ${AWS_SECRET_ACCESS_KEY}
      region: us-east-1
      endpoint_url: null  # Optional, for S3-compatible stores
      
  azure_blob:
    prod:
      connection_string: ${AZURE_STORAGE_CONNECTION_STRING}
      # OR
      account_name: mystorageaccount
      account_key: ${AZURE_STORAGE_KEY}
      
  gcs:
    prod:
      credentials_json: ${GCP_CREDENTIALS_JSON}  # Service account JSON
      project_id: my-project
```

### Multipart Upload Strategy
For files >100MB:
1. Initiate multipart upload
2. Stream chunks (default: 100MB per part)
3. Upload parts in parallel (configurable concurrency)
4. Complete multipart upload
5. Verify ETag/MD5 if supported

For smaller files:
- Single PUT operation with streaming body

### Error Handling
- Retry logic with exponential backoff
- Resume capability for multipart uploads
- Cleanup incomplete uploads on failure
- Clear error messages with remediation hints

### Writer Comparison

| Writer | Config Fields (non-secret) | Secrets via connections.yaml | SDK Dependency |
|--------|---------------------------|------------------------------|----------------|
| **filesystem.csv_writer** | `path`, `delimiter`, `mode` | None required | None (stdlib only) |
| **s3.csv_writer** | `bucket`, `object_key`, `delimiter`, `region`, `storage_class` | `aws_access_key_id`, `aws_secret_access_key`, `endpoint_url` | `boto3` |
| **azure_blob.csv_writer** | `container`, `blob_name`, `delimiter`, `tier` | `connection_string` OR `account_name`+`account_key` | `azure-storage-blob` |
| **gcs.csv_writer** | `bucket`, `object_name`, `delimiter`, `storage_class` | `credentials_json`, `project_id` | `google-cloud-storage` |

**Common across all writers:**
- Consume RowStream interface (ADR-0022)
- Deterministic CSV contract (UTF-8, LF, stable column order)
- No secrets in OML configuration
- Support for configurable delimiter
- Structured error reporting

## Consequences

### Pros
- **Data lake ready**: Direct integration with modern cloud architectures
- **Scalable**: Multipart uploads handle 10GB+ files efficiently
- **Cost-effective**: No local staging reduces egress costs
- **Secure**: Credentials managed via connection system
- **Consistent**: Same CSV contract across all writers
- **Progressive**: Stream data as it's generated

### Cons
- **SDK dependencies**: Requires boto3, azure-storage-blob, google-cloud-storage
- **Complexity**: Multipart upload logic and error handling
- **Testing**: Need mocked cloud services for unit tests
- **Network**: Sensitive to network interruptions
- **Costs**: Cloud storage and API call charges

## Alternatives Considered

1. **Generic object store writer**: Single component for all clouds
   - Rejected: Each cloud has unique features worth exposing
   
2. **Local staging + upload**: Write locally, then upload
   - Rejected: Doubles storage requirements, slower for large files
   
3. **Parquet/ORC support**: Native columnar format writers
   - Rejected: Scope creep, can be added later as separate components
   
4. **Direct SDK usage in OML**: Let users write upload code
   - Rejected: Violates component abstraction, credentials in OML

## Implementation Plan

### Phase 1: S3 Writer (Reference Implementation)
- Create `components/s3.csv_writer/spec.yaml`
- Implement `writer.py` with boto3
- Unit tests with moto mocking
- Integration test with MinIO
- Example: `docs/examples/mysql_to_s3.yaml`

### Phase 2: Azure Blob Writer
- Create `components/azure_blob.csv_writer/spec.yaml`
- Implement `writer.py` with azure-storage-blob
- Unit tests with azure mocks
- Integration test with Azurite
- Example: `docs/examples/mysql_to_azure.yaml`

### Phase 3: GCS Writer
- Create `components/gcs.csv_writer/spec.yaml`
- Implement `writer.py` with google-cloud-storage
- Unit tests with GCS mocks
- Integration test with fake-gcs-server
- Example: `docs/examples/mysql_to_gcs.yaml`

### Phase 4: Documentation & Testing
- Update component registry
- Performance benchmarks with large files
- Network interruption resilience tests
- Cost analysis documentation
- Migration guide from local writers

## Non-Goals
These are explicitly out of scope:
- **Parquet/ORC writers**: Separate future components
- **Bucket creation**: Must exist, fail if missing
- **Lifecycle management**: No auto-archival or TTL
- **Encryption**: Use cloud-native encryption settings
- **Compression**: Can be added later as option
- **Partitioning**: No Hive-style partitioning (yet)
- **Schema evolution**: CSV is schema-on-read

## References
- ADR-0022: Streaming IO and Spill (RowStream interface)
- ADR-0020: Connection Management (credential resolution)
- ADR-0014: Component System Architecture (component structure)
- ADR-0015: Component Health Checks (health check patterns)

## Acceptance Criteria
- All three cloud writers implemented and tested
- Multipart upload works for 10GB+ files
- Connection resolution via osiris_connections.yaml
- No secrets in OML or logs
- Examples demonstrate each cloud provider
- Performance comparable to native cloud CLIs
- Error messages actionable with clear remediation

## Implementation Notes (M1c)
The driver-based runtime provides the foundation for remote object store writers:
- Cloud writers will extend the same Driver protocol used by `filesystem.csv_writer`
- The deterministic CSV contract is already implemented in the filesystem driver
- DriverRegistry allows registration of cloud-specific drivers alongside local ones
- Connection resolution and metrics tracking work identically for all driver types

## Notes on Milestone M1

**Implementation Status**: Not implemented in Milestone M1. Postponed to Milestone M2.

The remote object store writers (S3, Azure Blob Storage, Google Cloud Storage) described in this ADR have not been implemented:
- **No S3 writer**: The `s3.csv_writer` component does not exist
- **No Azure Blob writer**: The `azure_blob.csv_writer` component does not exist
- **No GCS writer**: The `gcs.csv_writer` component does not exist
- **No cloud SDK dependencies**: boto3, azure-storage-blob, google-cloud-storage are not included

Current state:
- Only `filesystem.csv_writer` is implemented for local file writing
- No multipart upload capability for large files
- No direct cloud storage integration

This feature is postponed to Milestone M2 for implementation alongside other data lake and cloud integration features.
