# Adding ABI requirements

This repository publishes binary ABI facts. It does not decide which BambuStudioEx command or
event uses them. Changes that introduce a new native integration therefore normally span this
repository and `KimDaeWook/BambuStudioEx`.

## 1. Identify the exact C++ facts

Record the upstream Bambu Studio revision, declaration, and call site that justify the integration.
Prefer an existing exported function or accessor. Add a record member or vtable method only when no
equivalent callable API exists and document any side effects of the alternatives that were rejected.

Use the full demangled C++ name exactly as LLVM prints it, including namespaces, parameter types,
`const`, and libc++'s `std::__1` spelling. Do not invent a logical alias and do not add Runtime event
meaning, UI labels, feature names, or composed member paths.

## 2. Update the version requirements

Edit `abi-layouts/<version>/requirements.json`:

- add a function or global to the sorted `symbols` array;
- add a direct member or base to `layouts[<C++ type>]`; or
- add a virtual method signature to `vtables[<C++ type>].methods` and extend `vtable_probe` when the
  existing probe class does not materialize it.

Common requirements belong only in `requirements.json`. Put a value in
`requirements.<platform>-<architecture>.json` only when that ABI genuinely needs an override. A
constructor or destructor whose complete/base/deleting variants demangle to the same C++ name is the
usual reason for a `symbol_overrides` entry. Ordinary functions must not duplicate their mangled
name in the platform file.

For a new Bambu Studio version, dispatching the workflow creates `requirements.json` by copying the
nearest earlier numeric version and also copies its platform override files. Review the inherited
catalog before accepting it.

## 3. Generate and review the profile

Run **Generate complete ABI profile** with the exact upstream release tag. The layout and function
jobs run independently and the assemble job publishes only when both are complete and refer to the
same upstream commit.

Review the resulting changes:

- every requested symbol is present exactly once and its address is a non-zero JSON integer;
- every layout contains only direct `members`, `bases`, `size`, and `alignment` facts;
- the manifest records both common and platform requirement hashes; and
- the executable SHA-256, UUID, release tag, source commit, and target architecture match the
  official release.

Never copy an address or offset from a previous version to make extraction pass.

## 4. Add the BambuStudioEx consumer

In the BambuStudioEx repository:

1. add the typed native call to `src/runtime/studio/studio_abi_methods.inc`;
2. map its `StudioMethod` value to the exact same C++ key in
   `src/runtime/studio/studio_abi_profile_names.inc`;
3. implement the adapter/command behavior and its capability checks;
4. for an event global, add its semantic kind and reason to the adapter's internal event mapping
   instead of putting that policy in this repository; and
5. refresh the committed generated-profile test fixture and add failure tests for missing data.

Published profiles may contain symbols unknown to an older BambuStudioEx build. The consumer ignores
those forward entries, but it never calls one until that build has an explicit typed mapping. This
allows the ABI profile to be published before or together with the consumer without breaking older
installers.

## 5. Validate the end-to-end boundary

Build BambuStudioEx, run its Studio adapter and launcher tests, and execute the read-only
`profile generate` command against an authorized installed copy. That command must only download,
validate, and stage the published profile. A live `install` or `restore` remains a separate explicit
integration test because it modifies BambuSource.

