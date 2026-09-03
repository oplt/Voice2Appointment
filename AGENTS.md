# AGENTS.md

## Objective

Implement the smallest complete solution that satisfies the current task,
requirements, and acceptance criteria.

Optimize for:

1. Correctness and data safety
2. Explicit task requirements
3. Preservation of existing external contracts
4. Simplicity
5. Consistency with the current architecture
6. Extensibility only for demonstrated needs

Do not design for hypothetical future requirements.

---

## Before editing

Read the relevant implementation directly before making changes.

Inspect, as applicable:

* Source code
* Tests
* Types and interfaces
* Configuration
* Database/schema definitions
* Existing abstractions and helpers
* Dependency versions
* Relevant dependency documentation
* Architecture documentation
* Current working-tree changes

Do not make implementation decisions from search snippets, filenames, assumptions,
or guessed architecture.

Follow established project conventions unless they are clearly defective or
conflict with the task.

Preserve pre-existing user changes.

### Resolve material ambiguity

Resolve an ambiguity before editing when it could materially affect:

* Required behavior
* Public contracts
* Persistence
* Compatibility
* Security
* Architecture
* Scope

For minor, reversible implementation choices, follow existing repository
conventions rather than interrupting the task unnecessarily.

### Plan non-trivial work

For non-trivial changes, state a minimal plan:

* **Outcome** — exact behavior that will exist when complete
* **Non-goals** — explicitly excluded work
* **Files** — smallest expected set of files to change
* **Proof** — validation that demonstrates correctness

Start with one implementation path.

Split work only when the task contains genuinely independent concerns.

---

## Scope discipline

Keep every change directly connected to the requested behavior.

Do not perform unrelated:

* Refactoring
* Formatting
* Renaming
* Cleanup
* Dependency upgrades
* Architecture modernization
* Test backfilling
* Documentation rewriting

Do not modify a file merely because nearby code could be improved.

Every touched file must have a direct reason to change.

If the task begins expanding into unrelated work, reduce it back to the smallest
complete solution.

---

## Implementation principles

### Prefer existing capabilities

Before adding new code, look for existing:

* Helpers
* Utilities
* Services
* Interfaces
* Components
* Hooks
* Configuration
* Test fixtures
* Patterns
* Library capabilities

Reuse them when they fit the requirement.

Before reimplementing functionality provided by a dependency, inspect:

* The installed dependency version
* Its documentation
* Its types/interfaces
* Existing project usage

### Fix root causes

Fix defects at the source of the incorrect behavior.

Do not stack patches, retries, conditionals, fallbacks, or special cases around
an incorrect premise when the underlying problem can be corrected directly.

### Prefer simple complete solutions

Choose the simplest implementation that fully satisfies the requirement.

Do not optimize for theoretical future flexibility.

Do not introduce abstractions solely for hypothetical reuse.

An abstraction, adapter, interface, configuration layer, or service boundary is
appropriate when it provides a concrete benefit for the current task, such as:

* Multiple real callers or implementations
* Isolation of an external system
* A meaningful architectural boundary
* Testability
* Security
* Removal of existing duplication
* Explicit requirements

### Preserve architectural boundaries

Keep responsibilities separated according to the project's existing
architecture.

Do not bypass an established service, repository, adapter, API, state-management,
or domain boundary merely because direct access is shorter.

At the same time, do not create additional architectural layers without a
demonstrated benefit.

### Remove obsolete paths

Prefer modifying or deleting obsolete internal code over maintaining:

* Duplicate implementations
* Compatibility wrappers
* Permanent fallbacks
* Transitional adapters
* Old and new execution paths simultaneously

Keep multiple implementations alive only when compatibility or staged migration
is an explicit requirement.

Avoid knowingly temporary or disposable implementations.

A bounded incremental solution is acceptable when it is:

* Correct
* Tested
* Production-appropriate
* Consistent with the architecture
* Not an architectural dead end

---

## Contracts and data safety

Preserve existing externally consumed behavior unless the task explicitly
requires a change.

Treat the following as contracts:

* Public APIs
* Database schemas
* Persisted data
* Serialized formats
* Configuration formats
* Environment-variable contracts
* Events
* Message payloads
* Wire protocols
* CLI interfaces
* URLs and routes
* User-visible behavior relied upon elsewhere

When changing persisted schemas or formats, provide the required migration or
compatibility strategy.

Never silently reinterpret existing persisted data.

Do not delete, truncate, overwrite, migrate destructively, or otherwise
irreversibly modify user data unless explicitly required.

---

## Dependencies

Prefer capabilities already available in the project.

Add a dependency only when it materially improves one or more of:

* Correctness
* Security
* Maintainability
* Reliability
* Implementation complexity

Do not add a dependency merely to avoid writing a small amount of straightforward
code.

Do not modify dependency manifests or lock files unless dependency changes are
required by the task.

Do not upgrade unrelated dependencies.

---

## Existing user work

Before editing, inspect the working tree when repository tooling permits it.

Do not:

* Revert unrelated user changes
* Overwrite uncommitted work
* Reformat unrelated modified code
* Delete files created by the user
* Reset the repository
* Rewrite Git history

Work around unrelated existing modifications whenever reasonably possible.

---

## Secrets and sensitive data

Never:

* Commit credentials
* Hard-code secrets
* Print secrets into logs
* Copy secrets into tests or fixtures
* Add real credentials to example configuration
* Expose tokens in error messages or debug output

Use the project's existing secrets and configuration mechanisms.

---

## Vertical implementation

Build changes as coherent vertical slices whenever practical.

A vertical slice should connect the minimum necessary layers required to deliver
one complete behavior.

Prefer:

> request → domain/service behavior → persistence/integration → response → test

over implementing speculative horizontal infrastructure that is not yet used.

Keep the repository in a valid and testable state throughout the implementation.

---

## Testing and validation

Validation should prove the requested behavior, not justify additional work.

### Tests

Run the narrowest existing tests that exercise the changed behavior first.

Prefer extending the most relevant existing test before creating a new test
file.

Add or update tests when they protect:

* Changed user-observable behavior
* An explicit acceptance criterion
* A meaningful invariant
* A reproduced bug
* A realistic regression risk introduced or fixed by the task

Do not:

* Backfill unrelated test coverage
* Test implementation details without a meaningful reason
* Introduce new test infrastructure solely for one small task
* Add speculative tests for behavior that was not requested

### Other checks

Run the most relevant available:

* Unit tests
* Integration tests
* Type checks
* Linters
* Format checks
* Builds
* Architecture checks
* Schema validation
* Migration checks

Prefer targeted validation before broad repository-wide checks.

### Validation reporting

Do not claim validation succeeded unless the command was actually run
successfully.

Report:

* Exact commands executed
* Whether they passed or failed
* Relevant failures
* Checks intentionally not run
* Any behavior that remains unverified

If validation cannot be run, state exactly why.

Passing tests are not justification for unrelated abstractions, refactors, or
scope expansion.

---

## Documentation

Update documentation when the implementation changes documented:

* Behavior
* APIs
* Configuration
* Setup
* Architecture
* Operations
* Deployment
* Usage

Prefer updating the existing authoritative documentation rather than creating a
new document.

Do not rewrite unrelated documentation.

Comments should explain non-obvious intent or constraints, not restate the code.

---

## Pause and confirm

Read-only investigation is always allowed.

If the task has not already authorized it, get approval before making a change
that would materially:

* Expand the requested scope
* Modify unrelated subsystems
* Add a framework
* Add an external service
* Add substantial infrastructure
* Introduce new test infrastructure
* Change a public API
* Change a schema or persisted format
* Change a wire/message format
* Break backward compatibility
* Delete or overwrite user data
* Discard uncommitted work
* Rewrite Git history
* Perform destructive migrations
* Keep old and new implementations active simultaneously

Do not pause for ordinary reversible implementation choices that can be resolved
from the codebase and existing conventions.

---

## If the plan grows

Stop and reassess when implementation starts accumulating:

* Future-use abstractions
* Speculative architecture
* Compatibility layers nobody requested
* Workaround stacks
* Duplicate execution paths
* Unrelated cleanup
* Broad refactoring
* New infrastructure
* Tests for unstated behavior

Rewrite the plan around the smallest complete solution.

If the smaller solution cannot satisfy the requirement and the necessary change
would materially expand the agreed scope, confirm that scope before proceeding.

---

## Architecture extraction (Phase 0+)

When splitting oversized files, follow:

* `docs/architecture-phase0.md`
* `prompt.txt`

Architecture extraction is structural work. Do not combine it with unrelated
behavior changes in the same PR.

### Characterization first

Before splitting behavior-heavy modules:

* Add or extend characterization tests for behavior that could regress.
* Register applicable characterization coverage in:

  `backend/scripts/characterization_registry.json`

Characterization tests should protect existing behavior during extraction, not
be used as an excuse to redesign that behavior.

### File-size guards

Run the applicable architecture guards locally:

```bash
python backend/scripts/check_file_sizes.py
```

and:

```bash
cd frontend && npm run check:arch
```

When a file drops below its category limit, prune its baseline entry using the
appropriate `--prune-baseline` workflow.

Do not leave stale grandfathered baseline entries.

### Extraction boundaries

Prefer extracting around coherent responsibilities and vertical slices.

Good extraction boundaries include:

* Domain responsibility
* Service boundary
* External integration
* Persistence responsibility
* API responsibility
* UI feature responsibility
* State-management responsibility

Do not split files arbitrarily to satisfy line-count limits.

A new file should have a coherent reason to change independently from the file
it was extracted from.

### Extraction invariants

Unless explicitly requested, architecture extraction must not change:

* Runtime behavior
* Public APIs
* Data models
* Serialization
* Persistence behavior
* Error semantics
* User-visible behavior

Separate behavior changes from structural extraction whenever practical.

---

## Definition of done

A task is complete only when:

* The requested behavior is implemented.
* Acceptance criteria are satisfied.
* Relevant validation has been run.
* Validation results are reported accurately.
* Every touched file is necessary.
* The diff contains no unrelated changes.
* Existing public contracts remain intact unless explicitly changed.
* Existing user work remains intact.
* Obsolete code replaced by the implementation has been removed where safe.
* No debug code remains.
* No temporary logging remains.
* No backup copies remain.
* No scratch/generated files remain unintentionally.
* No dead or commented-out implementation paths remain.
* No unnecessary compatibility layers remain.
* Documentation is updated where required.
* Assumptions are stated.
* Limitations are stated.
* Skipped or impossible validation is stated.
* Unverified runtime behavior is stated plainly.

The goal is not the largest or most sophisticated implementation.

The goal is the smallest correct change that leaves the codebase in a better,
fully coherent state.
