select
  toUInt64(id) as repository_id,
  name as repository_name,
  full_name,
  private as is_private,
  archived as is_archived,
  default_branch,
  parseDateTime64BestEffortOrNull(toString(pushed_at)) as pushed_at,
  parseDateTime64BestEffortOrNull(toString(updated_at)) as updated_at,
  parseDateTime64BestEffortOrNull(toString(extracted_at)) as extracted_at
from {{ source('github', 'repositories') }}
