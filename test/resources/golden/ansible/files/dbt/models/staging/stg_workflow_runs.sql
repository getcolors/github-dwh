select
  toUInt64(id) as workflow_run_id,
  repository_name,
  name as workflow_name,
  status,
  conclusion,
  head_sha,
  parseDateTime64BestEffortOrNull(toString(created_at)) as created_at,
  parseDateTime64BestEffortOrNull(toString(updated_at)) as updated_at
from {{ source('github', 'workflow_runs') }}
