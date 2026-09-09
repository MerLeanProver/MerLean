# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities through GitHub's private vulnerability
reporting interface:

<https://github.com/MerLeanProver/MerLean/security/advisories/new>

Do not include API keys, credentials, private repositories, or private proof
artifacts in a public issue. If private reporting is unavailable, open a public
issue containing only a non-sensitive request for a maintainer to enable a
private reporting channel.

## Credential handling

MerLean never distributes an API key. Local credentials belong in environment
variables or ignored `.env` files. Release archives are built exclusively from
Git-tracked files and are checked for credential filenames, common secret
formats, private-key blocks, and absolute user-home paths before publication.
The release builder reads Git objects directly rather than copying the working
plugin directory, so ignored local runtime files cannot enter an archive.
