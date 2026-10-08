"""Canonical source normalization shared by current and historical snapshots."""
import json
import re

STATES = {'UNKNOWN': 'unknown', 'SPECIFIED': 'documented', 'PLANNED': 'planned',
          'BUILDING': 'in-progress', 'BUILT': 'built', 'LANDED': 'source-landed',
          'CLOSED': 'closed', 'DEFERRED': 'deferred', 'REJECTED': 'rejected'}


def record(raw, path, kind, *, parent=None):
    """Allowlist public fields; status never propagates between specs and slices."""
    delivery = str(raw.get('delivery_state', 'UNKNOWN')).upper()
    acceptance = str(raw.get('acceptance_state', 'NOT_AUDITED')).upper()
    done = delivery in {'LANDED', 'CLOSED'} and acceptance == 'ACCEPTED'
    return {'id': str(raw.get('spec_id', raw.get('id', path.parent.name))),
            'kind': kind, 'parent': parent, 'source': path.as_posix(),
            'title': str(raw.get('title', raw.get('spec_id', raw.get('id', path.parent.name)))),
            'delivery_state': delivery, 'acceptance_state': acceptance,
            'state': 'done' if done else STATES.get(delivery, 'unknown'),
            'done': done, 'release_state': 'unknown'}


def read_records(root, config):
    records = []
    seen = set()
    for source in config['sources']:
        for path in sorted(root.glob(source['glob'])):
            relative = path.relative_to(root)
            if '_template' in relative.parts or path.resolve().is_relative_to(root) is False:
                continue
            if relative in seen:
                continue
            seen.add(relative)
            records.extend(read_source(path, relative, source.get('kind', 'spec'), root=root))
    return records


def read_source(path, relative, kind, *, root):
    if kind not in {'spec', 'requirement'}:
        raise ValueError('kind must be spec or requirement')
    raw = json.loads(path.read_text(encoding='utf-8'))
    result = source_records(raw, relative, kind)
    if kind == 'spec':
        result[0].update(document_metadata(path, root))
    return result


def source_records(raw, relative, kind):
    primary = record(raw, relative, kind)
    result = [primary]
    children = {str(item['id']): item for item in raw.get('requirements', [])}
    ids = dict.fromkeys([*raw.get('requirement_ids', []), *children])
    for identifier in ids:
        result.append(record(children.get(identifier, {'id': identifier}), relative,
                             'requirement', parent=primary['id']))
    return result


def document_metadata(path, root):
    document = path.with_name('spec.md')
    if not document.is_file() or not document.resolve().is_relative_to(root):
        return {}
    headings = re.findall(r'^# (.+)$', document.read_text(encoding='utf-8'), re.MULTILINE)
    metadata = {'document': document.relative_to(root).as_posix()}
    if headings:
        metadata['title'] = headings[0]
    return metadata
