"""Read-only project review over saved records, never a readiness verdict."""
from backend import AppError, now
from reading import Reading


def project_review(store, workspace_id):
    workspace = store._workspace(workspace_id)
    reading = Reading(store)
    claims = [row for row in reading.public(reading.load(workspace_id))['claims'] if not row['archived']]
    notes = []
    totals = dict(drafts=0, drafts_without_reviews=0, claims=len(claims),
                  needs_source=sum(c['status']=='needs_source' for c in claims),
                  stale_claims=sum(c['stale'] for c in claims),
                  checked_claims=sum(c['status']=='checked' and not c['stale'] for c in claims),
                  unresolved_references=0, missing_metadata_sources=0, failed_checks=0)
    missing_sources = set()
    for note in store.db.execute('SELECT * FROM notes WHERE workspace_id=? ORDER BY updated_at DESC,id', (workspace_id,)):
        linked = [claim for claim in claims if claim['note_id']==note['id']]
        row = {'id':note['id'], 'title':note['title'], 'version':note['version'], 'claims':linked,
               'stale_claims':sum(c['stale'] for c in linked),
               'needs_source':sum(c['status']=='needs_source' for c in linked)}
        totals['drafts'] += 1
        totals['drafts_without_reviews'] += not bool(linked)
        try:
            checked = store._writing_check({'workspace_id':workspace_id,'note_id':note['id'],'version':note['version']})
        except AppError as error:
            totals['failed_checks'] += 1
            row.update(check_status='failed',error=str(error),unresolved_references=None,missing_metadata=None,mechanical_issues=None)
        else:
            row.update(check_status='checked',error='',**{key:checked[key] for key in ('unresolved_references','missing_metadata','mechanical_issues')})
            totals['unresolved_references'] += len(checked['unresolved_references'])
            missing_sources.update(item['document_id'] for item in checked['missing_metadata'])
        notes.append(row)
    totals['missing_metadata_sources'] = len(missing_sources)
    if totals['failed_checks']:
        totals['unresolved_references'] = None
        totals['missing_metadata_sources'] = None
    return {'workspace_id':workspace_id,'title':workspace['title'],'checked_at':now(),'totals':totals,'notes':notes,
            'notice':'Saved drafts and recorded claim reviews only; not a readiness certification. Unrecorded claims have not been assessed. Counts can overlap. No documents or writing were changed.'}
