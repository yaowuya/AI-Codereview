# Refresh Policy

Generated intel is navigation, not proof of current behavior.

Every generated intel artifact should include a small freshness block near the top:

```markdown
Generated: <timestamp>
Refreshed: <timestamp or never>
Generated from Git SHA: <sha or unavailable>
Working tree: clean | dirty | unavailable
Depends on:
- <source path> @ <git blob sha or content hash or unavailable>
Generated body hash: <sha256 of generated body excluding this freshness block or unavailable>
Freshness: fresh | soft-stale | hard-stale | unknown
Refresh decision: keep | regenerate | conflict
Use as: navigation-hint-only
```

## Hard-stale

- Referenced paths disappear.
- Package manifests/config files change.
- Test/build/lint config changes.
- Route/API framework config changes.
- Auth/permission files change.
- Component library/theme/token files change.
- Any depends-on source recorded in `sources-and-provenance.md` has a changed git blob SHA or content hash.

## Soft-stale

- Git SHA differs from recorded SHA.
- Working tree was dirty during generation.
- Profile is old.
- Current change touches an area covered by an intel artifact.

## Selective refresh

1. Read only the manifest, this policy, the target artifact freshness block, and its recorded dependency paths.
2. Recompute dependency fingerprints and classify the artifact before reading its whole generated body.
3. If the body hash differs from `Generated body hash`, classify `conflict`; never overwrite without file-specific approval.
4. After batch approval, regenerate only listed stale generated artifacts, record new fingerprints, and set `Refresh decision: regenerate`.
5. Never refresh settings, unknowns/decisions, active change artifacts, archive, or history through this policy.

On stale intel, verify just-in-time. A stale or conflicted artifact is never current-state proof.
