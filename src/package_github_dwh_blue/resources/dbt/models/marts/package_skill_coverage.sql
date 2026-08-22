select
  repository_name,
  count() as tracked_metadata_files,
  countIf(endsWith(path, 'SKILL.md')) as skill_definition_count,
  countIf(path = 'skills-lock.json') > 0 as has_skills_lock,
  max(extracted_at) as last_inspected_at
from {{ ref('stg_package_skills') }}
group by repository_name
