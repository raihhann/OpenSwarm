# Development and repository organization

## Branch roles

- `main`: tested integration baseline for users and releases.
- `dev`: ongoing integration and testing before review into main.
- `feature/<topic>`: short-lived changes, normally based on `dev`.
- `SwarmNode`: generated Arduino-library distribution tree. Do not use it as the
  framework development branch or merge the monorepo into it.

Keep tests beside the code they verify. Moving tests onto a separate test-only
branch would make it harder to reproduce which tests validated a framework change.
Development branches retain the full framework and tests; they represent versions,
not different folders of one project.

## Working on a change

After the prepared `dev` branch has been committed and pushed, a collaborator
can start from it with:

```bash
git switch dev
git pull --ff-only origin dev
git switch -c feature/describe-the-change
python -m unittest discover -s tests -t . -v
```

Review the diff, commit the intended files, and open a pull request into `dev`.
Review tested integration changes through a pull request from `dev` into main.
Do not switch branches with uncommitted work unless you intend to carry it along.

Pushes to `dev` and `feature/**` and pull requests run the existing test/build matrix. Arduino
branch synchronization remains gated on a push to main; Python publication remains
gated on version tags. A development push does not publish packages. The workflow
continues to use the existing version/tag rules in [releases.md](releases.md).

To publish this prepared branch for review, first inspect and commit its cleanup:

```bash
git status
git diff --stat HEAD
# Stage only the reviewed cleanup files, then commit them.
git push -u origin dev
```

The cleanup has not been committed or pushed automatically. Main on GitHub will
change only after the cleanup is committed, reviewed, and merged there. Existing
commits/tags are not rewritten; untracking a virtual environment removes it from
future snapshots, not from Git history.

## Where files belong

| Location | Purpose |
| --- | --- |
| `master/` | Python coordinator/SDK and package metadata |
| `slaves/` | Arduino library and Linux agent |
| `projects/` | Applications such as HydraArm |
| `tests/` | Automated framework regression tests |
| `benchmarks/` | Reproducible software benchmarks and generated reference report |
| `benchmarks/hardware/` | Hardware fixtures, runners, and procedures |
| `benchmarks/hardware/results/campaign-*/` | Curated, versioned historical evidence |
| `benchmarks/hardware/results/local/` | New local measurements, ignored by Git |
| `docs/`, `assets/` | Framework documentation and its media |
| `.venv/`, `venv/`, `myvenv/` | Local environments, ignored by Git |

Root demo launchers remain convenient entry points. Build outputs stay ignored.
The private paper workspace is a sibling of this repository, not a framework branch
or package. Library paths, versions, and release tags are unchanged by this cleanup.
