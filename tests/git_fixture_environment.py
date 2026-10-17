"""Keep temporary Git commands out of the worktree that invoked a hook."""

from pipelines_hooks.core.settings import process_environment

ROUTING = (
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_CEILING_DIRECTORIES",
)


def fixture_git_environment(*, index=None):
    environment = process_environment()
    for key in ROUTING:
        environment.pop(key, None)
    if index is not None:
        environment["GIT_INDEX_FILE"] = str(index)
    return environment
