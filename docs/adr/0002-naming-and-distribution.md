# 0002 Naming lives in one module, and the PyPI distribution is halkit

Superseded in part by [ADR 0018](0018-one-command-openhal-start.md), which replaces the daemon name with `openhal start`. The rest of this decision stands.

Amended twice on 2026-11-02. The owner first chose `ohal`, and PyPI turned that name down as too similar to the existing project `ohai`, so the owner chose `halkit`. The first version of this decision used `openhal-hub`, and nothing was published under any of these names.

## Context

The product is OpenHAL. The import name, CLI and daemon are `openhal`, `openhal` and `openhald`. Device files end in `.hal.yaml`. The PyPI name `openhal` is already used by an unrelated project (checked 2026-10-24).

## Options considered

1. Publish as `openhal` anyway. Impossible, the name is taken.
2. Rename the import package too. Breaks the brief's naming.
3. Keep every public name in one module and pick a free distribution name.

The distribution names compared on 2026-11-02.

- `openhal` belongs to an unrelated project, HAL (Harmful Action Limiter).
- `hal` belongs to a project abandoned since 2012 (HAL 0.0.3). Getting the name would need a PEP 541 claim, which is slow.
- `openhal-hub` was the first default.
- `ohal` was the owner's first pick, but PyPI compares names after mapping o to 0 and both l and i to 1, so `ohal` matches the existing project `ohai` and PyPI turned the name down.
- `openhal-hub` and other long names passed that check, but the owner wanted a short name.
- `halkit` passed the same check against every project on PyPI on 2026-11-02 and is six letters, a HAL toolkit.

## Decision

- `openhal/_brand.py` holds the product name, package name, distribution name, CLI name, daemon name, device file suffix, Arduino library name, default port and config directory. Every other module imports these names from `_brand.py`. Docs and the website read the same values at build time where possible.
- The distribution name is `halkit`. After the first release, users run `uv tool install halkit` or `pipx install halkit` and get the `openhal` and `openhald` commands. Until then every install command uses the git repository, as in `uv tool install --compile-bytecode "halkit[serial] @ git+https://github.com/sohan-bhat/OpenHAL"`.
- Only the distribution name changes. Code imports `openhal`, people type `openhal`, the product is OpenHAL, and `openhald` stays a silent alias.
- .github/workflows/release.yml publishes to PyPI through trusted publishing when a tag `v<version>` is pushed. NEEDS_HUMAN.md item 3 lists the owner's steps.

## Consequences

A rename later is a change to `_brand.py`, `pyproject.toml` and the website config, plus a search for prose mentions in docs. tests/packaging/test_distribution.py and test_wheel.py fail when the lock file, an install command or the built wheel names another distribution.
