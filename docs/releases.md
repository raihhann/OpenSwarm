# Publishing OpenSwarm packages

Pending follow-up: master **0.2.1** contains the scheduling/clock patch. It is built
locally for hardware regression and has not been published by this work. Use
`master-v0.2.1` only when releasing that patch. Arduino 0.4.3 and slave 0.2.0 are
unchanged; do not republish or move their tags. The instructions below also document
the original 0.2.0 release campaign.

Prepared versions: `openswarm-master==0.2.0`, `openswarm-slave==0.2.0`, and
Arduino/PlatformIO `SwarmNode@0.4.3`. Preparing files does not publish them.
Check each registry before releasing: previously uploaded versions cannot be reused.

## 1. Commit and push the tested source

Review/stage the intended changes, including new benchmark/test files, then commit
and push `main` using your usual Git workflow. Wait for the repository's Actions
test matrix to pass. The main workflow also synchronizes the standalone Arduino
branch and creates its `v0.4.3` tag when absent. Do not manually tag the monorepo
as a substitute for that standalone Arduino tree.

## 2. Publish both Python packages through GitHub Actions

The existing workflow uses a repository Actions secret named `PYPI_API_TOKEN`.
In GitHub: repository Settings -> Secrets and variables -> Actions -> Repository
secrets. Add/update that secret with a PyPI token authorized to upload **both**
projects. A token scoped to only one project cannot publish the other. Enter
credentials in the service UI; do not paste tokens into source files or chat.
If the secret already exists and remains valid, no setup change is needed.

After the release commit has been pushed, run these commands from that commit:

```console
git tag master-v0.2.0
git push origin master-v0.2.0
git tag slave-v0.2.0
git push origin slave-v0.2.0
```

Each tag triggers tests and publishes only the matching package. Tag versions must
match that package's `pyproject.toml`; runtime `__version__` is updated too. Watch
the `Publish versioned Python package to PyPI` job for each tag. Missing credentials
now fail the release job rather than showing a successful skipped upload.

If a job fails before upload, fix the cause and rerun it as appropriate. If one
distribution/version was already uploaded, inspect registry state before retrying;
do not delete/move release tags or blindly republish existing versions.

## 3. Publish PlatformIO separately

From the repository root, using the account that owns the existing library:

```console
python -m pip install --upgrade platformio
pio account login
pio pkg pack slaves/arduino/SwarmNode --output build/SwarmNode-0.4.3.tar.gz
```

Create the `build` directory first if needed. Inspect the archive: it should have
`library.json`, `library.properties`, `src`, examples and the license/readme at the
package root, not the complete OpenSwarm repository. Both manifests must say 0.4.3.
Publish that inspected archive:

```console
pio pkg publish build/SwarmNode-0.4.3.tar.gz --owner raihann
```

`raihann` is the owner in this repository's existing PlatformIO installation example;
verify it is your actual registry owner before publishing. Publishing under another
account creates a different package identity. GitHub tags do not replace this step.
The publish command asks for confirmation; review the name/version/owner there.

The official [PlatformIO publish reference](https://docs.platformio.org/en/latest/core/userguide/pkg/cmd_publish.html)
documents the command and immutable name/version combinations. The
[PyPA packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
documents PyPI token/upload mechanics; this repository performs that upload in CI.

## 4. Install and verify published versions

On the Linux master laptop, in a fresh virtual environment:

```bash
python3 -m venv .venv-release
source .venv-release/bin/activate
python -m pip install 'openswarm-master==0.2.0'
python -c 'import openswarm; print(openswarm.__version__, openswarm.__file__)'
```

On the Pi, use a fresh environment with access to required system GPIO dependencies:

```bash
python3 -m venv --system-site-packages .venv-release
source .venv-release/bin/activate
python -m pip install 'openswarm-slave[hardware]==0.2.0'
python -c 'import openswarm_slave; print(openswarm_slave.__version__, openswarm_slave.__file__)'
```

The printed version must be 0.2.0 and its path should be the installed package,
not an editable checkout. Ensure no old editable install or PYTHONPATH overrides it.
Exact pins make the hardware evidence attributable to this release.

For PlatformIO projects:

```ini
lib_deps =
    raihann/SwarmNode@0.4.3
```

Keep the project platform/board/framework configuration appropriate to the board.
Confirm the build output resolves SwarmNode 0.4.3. Arduino IDE users can select
0.4.3 once Library Manager has indexed the released library; it may not appear
immediately after the workflow creates the tag.

The hardware test scripts and probe sketch are separate experiment files, not
installed by these Python wheels. Copy/download `benchmarks/hardware` once; its
Python scripts now import the installed SDKs rather than overriding them with
repository sources. Run the same hardware procedure with those scripts.
