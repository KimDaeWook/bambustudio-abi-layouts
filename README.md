# BambuStudio ABI Layouts

[한국어](README.ko.md)

BambuStudio ABI Layouts is an independent, open-source build and analysis project that reconstructs C++ ABI layout evidence from the public [BambuStudio](https://github.com/bambulab/BambuStudio) source code.

The project exists for extension runtimes, compatibility adapters, diagnostics, and other tools that must interoperate with an installed BambuStudio without rebuilding or replacing the application. It extracts source-derived record/vtable layouts and reviewed function/event addresses from the exact official release binary, then combines both into a small versioned runtime profile.

This project is not affiliated with or endorsed by Bambu Lab.

## Why this exists

Exported symbols can usually be checked directly in an installed binary. C++ object and member offsets are harder: recovering them only from instructions at one call site is sensitive to compiler optimizations and ordinary source changes.

Compiler-emitted record and vtable layouts provide a stronger source-derived signal. Those descriptions can then be checked against structural evidence in the installed binary before an adapter accepts them.

This is evidence, not an automatic compatibility guarantee:

- The source revision alone does not fully determine a C++ ABI. Xcode, Apple Clang, SDK, deployment target, CMake options, dependency revisions, generated headers, and compile definitions can all affect the result.
- A layout manifest must remain unavailable when the build provenance is incomplete or validation against the target binary is ambiguous.

## Complete profile pipeline

The manual **Generate complete ABI profile** workflow is the publishing entry point. It invokes two reusable workflows in parallel:

- **Extract layout ABI** runs on `macos-15`, restores or prepares the exact dependency headers, and extracts every record/vtable value requested by that version in consolidated compiler probes. It does not build or link BambuStudio itself.
- **Extract function ABI** runs on `ubuntu-24.04`, downloads the official macOS DMG for the requested release, extracts its arm64 Mach-O, and resolves all reviewed function and event symbols directly from `LC_SYMTAB`. The extractor also records the release binary SHA-256 and `LC_UUID`.

The final job accepts the results only when their version and exact upstream source commit agree. It then writes `abi-layouts/<version>/macos-arm64.json`, uploads it as an artifact, and commits the generated profile to this repository. The target JSON contains `symbols`, `layouts`, and `vtables`; `manifest.json` holds provenance and hashes. Because each file has one target architecture, UUIDs are scalar strings and addresses are JSON integers rather than architecture-keyed maps or hexadecimal strings. All function and event-global addresses are keyed by their canonical C++ names in `symbols`; event meaning belongs to the consumer. Layouts are keyed only by their actual C++ type and contain direct `members`, `bases`, `size`, and `alignment` facts. They contain no extension-feature groups, aliases, precomposed access paths, or UI metadata; consumers compose direct offsets for their own use. A missing record, vtable, symbol, architecture, UUID, or commit match is a hard failure.

Each version owns a platform-neutral `abi-layouts/<version>/requirements.json`. It lists record members/bases, canonical C++ function or global names, and vtable method signatures without a target tree or duplicated mangled names. An optional `requirements.<platform>-<architecture>.json` is recursively overlaid on the common document. Platform overrides are reserved for genuine ABI exceptions, such as constructor/destructor variants whose demangled C++ names are identical. The extractor demangles the release binary's own symbol table and requires every canonical name to resolve uniquely; the current macOS arm64 catalog needs only three explicit variant selectors. Inherited versions copy the common file and all neighboring platform overrides.

See [Adding ABI requirements](docs/adding-abi-requirements.md) for the cross-repository workflow used
when a BambuStudioEx feature needs a new function, global, member, base, or vtable entry.

Mach-O symbol values are image virtual addresses, not live process addresses. A consumer must first verify the exact binary hash and UUID, then apply the loaded image slide. The release asset cache avoids downloading the large DMG again on later runs.

## Source-layout probe

For member offsets, a full application link and dSYM are not always necessary. The source probe
forces the reviewed types to materialize and parses Clang's own record-layout output. Private data
members are included without changing upstream declarations or constructing any objects.

The default catalog consolidates all current record requirements into one syntax-only translation
unit, so common headers are parsed once. `Plater::priv` is defined inside `Plater.cpp`; the extractor
copies the exact source prefix through that complete record definition and does not parse unrelated
function implementations that follow it. The full-source hash, sliced-prefix hash, and ending line
are recorded as provenance, and any missing or ambiguous record remains a hard failure.

```bash
python3 scripts/extract-bambustudio-abi.py \
  --source-dir /path/to/BambuStudio \
  --output abi-values.json \
  --compiler "$(xcrun --find clang++)" \
  --std c++17 \
  --compiler-arg=-I/path/to/generated/includes \
  --compiler-arg=-I/path/to/dependency/includes
```

The probe still needs the exact compiler, SDK, generated headers, compile definitions, and dependency
headers that affect the selected records. It does not need dependency libraries, application object
files, linking, packaging, or `dsymutil`. The intended runner optimization is therefore to cache a
small versioned **ABI sysroot** of headers and generated configuration, then execute these probes in
seconds or minutes. Symbol addresses remain a separate binary-extraction concern.

`extract-bambustudio-abi.py` starts the single record-layout probe and a much smaller ConfigOption
vtable probe concurrently, then merges their results into the selected version's value catalog in
`config/bambustudio-abi-values.json`. Keeping vtable generation separate is intentional: enabling
code generation in the large `Plater.cpp` probe is slower than compiling the tiny `Config.hpp` probe
alongside the syntax-only record pass. The lower-level `extract-clang-layouts.py` and
`extract-clang-vtables.py` tools remain independently usable.

The reusable **Extract layout ABI** workflow restores the exact dependency prefix when cached and
builds it on a cache miss, then runs this source probe without building or linking BambuStudio itself.
The uploaded artifact contains all
requested values together with the resolved upstream commit, dependency tree, runner image, compiler, probe
arguments, and source-slice hashes.

Reviewed outputs are stored under `abi-layouts/<BambuStudio-version>/`. A target file such as
`macos-arm64.json` is a complete runtime profile containing the exact release identity, reviewed
symbols/events, and grouped numeric layouts. Its neighboring `manifest.json` binds that file's
SHA-256 to source, release, catalog, generator, and workflow provenance. A target file is added only
after both independent extractors succeed; unsupported platforms do not receive empty placeholders.

## Trust and reproducibility model

- Only public source from `https://github.com/bambulab/BambuStudio.git` is accepted.
- The resolved commit, `deps` Git tree, upstream version, runner image, Xcode, SDK, compiler, CMake, Ninja, flags, hashes, architectures, and UUIDs are recorded.
- Dependency caches are keyed by upstream dependency tree and concrete runner image. They improve iteration speed but are not treated as proof of compatibility.
- Generated layouts are never assumed to match an installed binary solely because a version string, source tag, hash, or UUID looks familiar.
- Consumers are expected to fail closed when required structure, symbols, or binary witnesses cannot be validated unambiguously.

## Development

Shell scripts use Bash strict mode and are designed to run from any working directory. Local checks,
including a small Clang fixture that verifies private member extraction, can be run with:

```bash
./tests/test-scripts.sh
```

The complete build requires a GitHub-hosted macOS runner and executes code from the selected upstream revision. Review workflow changes before running them.

## License

The automation and analysis code in this repository is licensed under the [Apache License 2.0](LICENSE). BambuStudio and all source or build products obtained from it remain subject to BambuStudio's own license and third-party notices.
