"""Requirement detail text and exact source locations from canonical Markdown rows."""
import re

ROW = re.compile(r'^\|\s*`([^`]+)`\s*\|(.*)\|\s*$')


def requirement_definitions(path, root):
    document = path.with_name('requirements.md')
    if not document.is_file() or not document.resolve().is_relative_to(root):
        return {}
    definitions = {}
    for number, line in enumerate(document.read_text(encoding='utf-8').splitlines(), 1):
        match = ROW.match(line)
        if match:
            identifier = match[1]
            if identifier in definitions:
                raise ValueError('Duplicate requirement definition: ' + identifier)
            definitions[identifier] = {'definition': match[2].strip(),
                                       'definition_source': document.relative_to(root).as_posix(),
                                       'definition_line': number}
    return definitions


def enrich_definitions(records, path, root):
    definitions = requirement_definitions(path, root)
    parent_title = records[0]['title']
    for record in records:
        if record['kind'] == 'requirement':
            record['parent_title'] = parent_title
            record.update(definitions.get(record['id'], {}))


def outside_fences(text):
    """Remove fenced examples, including unclosed and indented Markdown fences."""
    visible = []
    fence = ''
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = ''
        elif match and (match[1][0] == '~' or '`' not in match[2]):
            fence = match[1]
        else:
            visible.append(line)
    return '\n'.join(visible)
