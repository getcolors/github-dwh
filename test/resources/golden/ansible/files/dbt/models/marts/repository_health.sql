with commits as (
  select repository_name, max(authored_at) as last_commit_at, count() as commit_count
  from {{ ref('stg_commits') }} group by repository_name
), workflows as (
  select repository_name, max(created_at) as last_workflow_at,
    countIf(conclusion = 'success') as successful_runs,
    countIf(conclusion = 'failure') as failed_runs
  from {{ ref('stg_workflow_runs') }} group by repository_name
)
select r.repository_id, r.repository_name, r.full_name, r.is_private, r.is_archived,
  r.default_branch, r.pushed_at, c.last_commit_at, coalesce(c.commit_count, 0) as commit_count,
  w.last_workflow_at, coalesce(w.successful_runs, 0) as successful_runs,
  coalesce(w.failed_runs, 0) as failed_runs
from {{ ref('stg_repositories') }} r
left join commits c using (repository_name)
left join workflows w using (repository_name)
