# PIPE-RELEASE — Research

## npm trusted-publisher registration

- Unknown: whether the lane can register a package's trusted publisher by itself after a token publish.
- Finding: npm 11.10.0 and newer ship `npm trust github <package> --repo <owner/repo> --file <workflow>.yml`, which creates the trusted publisher without the website. `npm trust list` and `npm trust revoke --id` read and remove it. The registry holds one configuration per package. Source: the npm CLI manual page `npm help trust` at npm 11.12.1.
- Finding: the same manual page lists its prerequisites. The package must already exist, so registration follows the first publish. The account needs two-factor authentication. Granular access tokens with the bypass 2FA option are listed as not supported, and the first call asks for a two-factor code that a CI run cannot give.
- Decision: the lane attempts `npm trust github` once after a token publish, with no prompt and a timeout, and never fails a published release over it.
- Limitation: the package's owner token is a bypass 2FA token, so the attempt is expected to be refused. Then registration is not automated. The owner has one manual step per new package: on npmjs.com open the package, Settings, Trusted publishing, and add GitHub Actions with the repository and the calling workflow file. The lane prints that step as `TRUSTED_PUBLISHER_UNREGISTERED`. No other registry interface is documented for it, and none is used.
- Decision: a package the registry knows publishes by OIDC with an empty token. A missing trusted publisher shows as a refused publish, never as a silent fallback to the token.
