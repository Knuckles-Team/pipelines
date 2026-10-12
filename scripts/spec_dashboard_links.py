"""Public source link resolution and implementation/test/documentation roles."""
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


def source_link(root, document, target, *, repository, revision):
    """Accept public GitHub blob links or existing files contained by this checkout."""
    target = re.sub(r':(\d+)$', r'#L\1', target)
    try:
        parts = urlsplit(target)
    except ValueError:
        return '', '', 'unresolved'
    if parts.scheme or parts.netloc:
        if parts.scheme == 'https' and parts.netloc == 'github.com' and re.fullmatch(r'/[\w.-]+/[\w.-]+/blob/.+', parts.path):
            return target, '/'.join(parts.path.split('/')[1:3]), 'external declaration; not verified'
        return '', '', 'unresolved'
    return local_source(root, document, parts, repository=repository, revision=revision)


def code_role(target):
    path = Path(urlsplit(target).path)
    if path.suffix in {'.md', '.rst', '.txt'} or 'docs' in path.parts or 'specs' in path.parts:
        return 'documentation'
    if 'tests' in path.parts or path.name.startswith('test_') or '.test.' in path.name:
        return 'test'
    return 'implementation'



def local_source(root, document, parts, *, repository, revision):
    if Path(unquote(parts.path)).is_absolute():
        return '', '', 'absolute source path rejected'
    path = (document.parent / unquote(parts.path)).resolve()
    if not path.is_file():
        path = (root / unquote(parts.path)).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return '', '', 'missing source'
    relative = path.relative_to(root.resolve()).as_posix()
    fragment = '#' + quote(parts.fragment, safe='-') if parts.fragment else ''
    return f'https://github.com/{repository}/blob/{revision}/{quote(relative)}{fragment}', repository, 'file exists; coverage not verified'
