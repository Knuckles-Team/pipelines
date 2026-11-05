# PIPE-GATES — Research

## Where the build cache lives

- Unknown: which storage keeps a warm one-file-change check under 60 seconds.
- Finding: a cargo target directory and a compiler cache on a network filesystem made every build slow, because journaled metadata operations dominated the wall time. The same directories on local solid-state storage removed that cost.
- Finding: the checkout cleans ignored files, so a target directory inside it is lost on every run. The target directory lives outside the checkout, on the slot volume.
- Decision: each slot owns a local persistent volume, never shared across hosts. Priming on the default branch head makes the first pull request build incremental. A size budget prunes the target directory so the volume cannot fill.

## One definition, four runtimes

- Unknown: whether separate definitions per runtime stay in step.
- Finding: separate definitions drift in toolchain pins and cache budgets.
- Decision: one image and one configuration file render to Kubernetes, Docker Compose and rootless Podman, beside the existing SSH host mode.
