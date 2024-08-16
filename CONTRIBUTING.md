## Pull Requests

PRs are greatly appreciated.

When submitting a PR, please make sure your commits follow the [Conventional Commits
spec](https://www.conventionalcommits.org/en/v1.0.0/). PRs will generally be rebased (but not
squashed) before merging.

The following checks also need to pass for all supported python versions:

```shell
$ hatch fmt --check
$ hatch test
$ hatch run types:check
```

Please add tests for any new or fixed functionality.

## Development

`buildable` uses [hatch](https://github.com/pypa/hatch) for builds and project management.

For nicer `git diff` behavior when diffing .als files, add something like the following to your git
configuration and attributes settings:

```git-config
# git configuration, e.g. ~/.gitconfig or .git/config
[diff "gz"]
    textconv = gunzip -c
    binary = true
```

```git-attributes
# git attributes, e.g. ~/.gitattributes or .git/info/attributes
*.als diff=gz
```
