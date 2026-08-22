select
  sha,
  repository_name,
  commit__message as message,
  parseDateTime64BestEffortOrNull(toString(commit__author__date)) as authored_at,
  parseDateTime64BestEffortOrNull(toString(extracted_at)) as extracted_at
from {{ source('github', 'commits') }}
