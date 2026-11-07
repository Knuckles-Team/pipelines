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

## State-machine tables as sparse matrices

- Unknown: whether a declared transition table is well formed beyond having a test per edge.
- Finding: a table with states as rows and events as columns is a sparse matrix. Reachability is the closure from the initial state, and a dead end is an empty row.
- Finding: a terminal state is absorbing when its row is empty. A terminal state with an outgoing cell is a lifecycle that can reopen.
- Finding: determinism means each cell holds at most one target. A missing cell is the refusal, so the complement of the table is a finite list of refusals to test.
- Decision: PIPE-GATES-R086.9 runs five static checks, linear in table size, and proves well-formedness only, not semantics.

## Secret-bearing fields in served responses (PIPE-GATES-R097)

- Decision: the gate scans response models, package schemas, served output schemas and recorded outputs, and never calls a live tool. A live call needs a backend and credentials, so the served half reads the output schema that the built server registers; recorded outputs stand in for responses.
- Decision: a secret-named field ends in a credential word. Names that continue past the word (`token_expires_at`, `api_key_env`), flags (`has_password`) and cursor tokens (`continuation_token`) describe a credential or something else and are not reported.
- Limitation: a tool that returns an untyped dictionary straight from the remote API has no output properties to read. Such a tool relies on the SDK's default response redaction, which removes secret-named keys at the connector's model layer before serving.
- First census, 77 connectors at their default branch, 26 findings in 8 connectors:
  - archivebox-api: `ArchiveSession.password`
  - dockerhub-api: `JwtToken.access_token`
  - dockerhub-api: `JwtToken.token`
  - dockerhub-api: `LoginResult.token`
  - dockerhub-api: `LoginResult.refresh_token`
  - dockerhub-api: `LoginResult.login_2fa_token`
  - dockerhub-api: `AccessToken.token`
  - dockerhub-api: `OrgAccessToken.token`
  - gitlab-api: `Project.runners_token`
  - gitlab-api: `Group.runners_token`
  - gitlab-api: `DeployToken.token`
  - gitlab-api: `Token.token`
  - gitlab-api: `GitLabInstance.token`
  - gramps-mcp: `TokenResponse.access_token`
  - gramps-mcp: `TokenResponse.refresh_token`
  - microsoft-agent: `OfficePairingGrant.pairing_token`
  - microsoft-agent: `OfficeSessionGrant.session_token`
  - qbittorrent-agent: `AppPreferences.mail_notification_password`
  - qbittorrent-agent: `AppPreferences.proxy_password`
  - qbittorrent-agent: `AppPreferences.web_ui_password`
  - qbittorrent-agent: `AppPreferences.dyndns_password`
  - servicenow-api: `Authentication.refresh_token`
  - servicenow-api: `Authentication.access_token`
  - servicenow-api: `SdkAuthModel.password`
  - servicenow-api: `SdkAuthModel.list_credentials`
  - vaultwarden-mcp: `ResolvedProviderRuntime.credentials`
