select
  repository_name,
  path,
  blob_sha,
  toUInt64OrZero(toString(size)) as size_bytes,
  parseDateTime64BestEffortOrNull(toString(extracted_at)) as extracted_at
from {{ source('github', 'package_skills') }}
