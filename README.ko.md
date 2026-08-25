# BambuStudio ABI Layouts

[English](README.md)

BambuStudio ABI Layouts는 공개된 [BambuStudio](https://github.com/bambulab/BambuStudio) 소스 코드로부터 C++ ABI 레이아웃 근거를 재구성하는 독립 오픈 소스 빌드·분석 프로젝트입니다.

설치된 BambuStudio를 다시 빌드하거나 대체하지 않고 연동해야 하는 확장 런타임, 호환성 어댑터, 진단 도구 등을 위한 프로젝트입니다. 소스 기반 record/vtable layout과 공식 릴리스 바이너리의 검토된 function/event 주소를 각각 추출한 뒤, 작고 버전이 명확한 런타임 프로파일로 합칩니다. 기존 전체 dSYM 빌드는 연구 근거로 유지하지만 빠른 프로파일 파이프라인에는 필요하지 않습니다.

이 프로젝트는 Bambu Lab과 제휴 관계가 아니며 Bambu Lab의 보증을 받지 않습니다.

## 필요한 이유

export symbol은 보통 설치된 바이너리에서 직접 확인할 수 있습니다. 반면 C++ 오브젝트와 멤버 offset을 특정 사용처의 명령어만으로 복원하면 컴파일러 최적화나 평범한 소스 변경에도 탐지가 쉽게 깨집니다.

컴파일러가 생성한 타입 정보는 더 강한 소스 기반 근거를 제공합니다. 대응하는 공개 revision에서 만든 dSYM의 DWARF에는 record 크기, 상속 관계, 멤버 위치가 포함될 수 있습니다. 이후 설치된 바이너리의 구조적 근거와 함께 검증하면 어댑터가 레이아웃을 받아들일지 더 보수적으로 판단할 수 있습니다.

다만 이것은 근거이지 자동 호환성 보장은 아닙니다.

- 재빌드한 dSYM의 Mach-O UUID는 보통 Bambu Lab 배포 앱과 다릅니다. UUID가 일치하는 공식 dSYM처럼 배포 바이너리 symbolication에 사용하면 안 됩니다.
- 소스 revision만으로 C++ ABI 전체가 결정되지는 않습니다. Xcode, Apple Clang, SDK, deployment target, CMake 옵션, dependency revision, 생성 헤더와 compile definition도 결과에 영향을 줍니다.
- 빌드 provenance가 불완전하거나 대상 바이너리 검증이 모호하면 해당 레이아웃은 사용할 수 없는 상태로 남겨야 합니다.

## 완전한 프로파일 파이프라인

수동 **Generate complete ABI profile** workflow가 배포 진입점입니다. 다음 두 reusable workflow를 병렬로 호출합니다.

- **Extract layout ABI**는 `macos-15`에서 정확한 dependency header cache를 복원하고, 통합된 compiler probe로 해당 버전이 요구하는 모든 record/vtable 값을 추출합니다. BambuStudio를 build하거나 link하지 않습니다.
- **Extract function ABI**는 `ubuntu-24.04`에서 요청한 공식 macOS DMG를 다운로드하고 arm64 Mach-O를 꺼낸 뒤, `LC_SYMTAB`에서 검토된 function/event symbol을 모두 해석합니다. 릴리스 바이너리 SHA-256과 `LC_UUID`도 기록합니다.

마지막 job은 두 결과의 version과 정확한 upstream source commit이 같을 때만 결합합니다. 이후 `abi-layouts/<version>/macos-arm64.json`을 생성하고 artifact로 업로드한 뒤 저장소에 commit합니다. Target JSON에는 `symbols`, `layouts`, `vtables`가 들어가고, `manifest.json`에는 provenance와 hash가 들어갑니다. 파일 하나가 target architecture 하나만 표현하므로 UUID와 address는 architecture map이 아닌 scalar입니다. 모든 함수와 event global 주소는 canonical C++ 이름을 key로 `symbols`에 들어가며 event 의미는 consumer가 관리합니다. Layout은 실제 C++ type을 key로 사용하며 직접적인 `members`, `bases`, `size`, `alignment` 사실만 포함합니다. 확장 기능별 group, 임의 alias, 미리 합산한 접근 path 또는 UI metadata는 포함하지 않고 소비자가 필요한 직접 offset을 조합합니다. Record, vtable, symbol, architecture, UUID 또는 commit 일치 중 하나라도 빠지면 hard failure입니다.

각 버전은 플랫폼 중립적인 `abi-layouts/<version>/requirements.json`을 소유합니다. 여기에는 target tree나 중복된 mangled name 없이 record member/base, canonical C++ 함수 또는 global 이름, vtable method signature가 들어갑니다. 선택적인 `requirements.<platform>-<architecture>.json`은 공통 문서 위에 재귀적으로 overlay됩니다. 플랫폼 override는 demangle된 C++ 이름이 같은 생성자/소멸자 variant처럼 실제 ABI 예외에만 사용합니다. Extractor는 release binary 자체의 symbol table을 demangle하고 모든 canonical 이름이 유일하게 해석되는지 검증합니다. 현재 macOS arm64 catalog에서 명시적 variant 선택이 필요한 항목은 세 개뿐입니다. 버전을 상속할 때는 공통 파일과 인접한 platform override를 모두 복사합니다.

Mach-O symbol 값은 실행 중인 절대 주소가 아니라 image virtual address입니다. Consumer는 정확한 binary hash와 UUID를 먼저 검증하고 로드된 image slide를 적용해야 합니다. 큰 DMG는 release asset cache를 사용하므로 다음 실행에서는 다시 다운로드하지 않습니다.

## dSYM 연구 파이프라인

레이아웃 추출 문제 때문에 비용이 큰 빌드를 처음부터 반복하지 않도록 두 단계로 분리합니다.

### 1단계: DWARF를 포함한 macOS Release 빌드

`Build macOS dSYM` workflow는 다음 작업을 수행합니다.

1. upstream BambuStudio tag, branch 또는 전체 commit을 입력받습니다.
2. 고정된 `bambulab/BambuStudio` 저장소에서 입력을 해석하고 정확한 commit을 기록합니다.
3. 선택한 revision이 지원 대상 upstream macOS build contract를 그대로 선언하는지 확인합니다.
4. 해당 contract와 같은 runner 계열에서 arm64 dependency를 빌드하고 캐시합니다.
5. upstream `BuildMac.sh`의 Release/Ninja 빌드에 `-g -fstandalone-debug`만 추가합니다.
6. 결과 BambuStudio 실행 파일에 Apple `dsymutil`을 실행합니다.
7. 바이너리와 dSYM의 UUID 집합이 서로 일치하는지 검증합니다.
8. dSYM, machine-readable manifest와 toolchain provenance를 workflow artifact로 업로드합니다.

dependency 빌드와 애플리케이션 빌드는 서로 다른 job입니다. 애플리케이션 빌드나 dSYM 생성이 실패하더라도 완성된 dependency cache를 재사용할 수 있습니다.

### 2단계: ABI 레이아웃 추출

2단계는 BambuStudio를 재빌드하지 않고 1단계 artifact를 사용합니다. 명시적으로 요청된 타입과 멤버만 추출하고 각 결과의 DWARF 소스 위치를 보존하며, versioned JSON 레이아웃 manifest를 생성할 예정입니다. 대상 바이너리 검증과 downstream profile 비교도 이 단계에 속합니다.

GitHub Actions에서 유효한 dSYM이 생성되는 것을 확인하기 전까지 2단계를 빌드 workflow에 섞지 않습니다.

### 빠른 소스 레이아웃 probe

멤버 offset만 필요하다면 애플리케이션 전체 link와 dSYM이 항상 필요한 것은 아닙니다. 소스 probe는
검토된 타입을 강제로 구체화한 뒤 Clang 자체 record-layout 출력을 파싱합니다. Upstream 선언을
수정하거나 객체를 생성하지 않고도 private 데이터 멤버를 포함합니다.

기본 catalog는 현재 필요한 모든 record를 하나의 syntax-only translation unit으로 합쳐 공통 헤더를
한 번만 파싱합니다. `Plater::priv`는 `Plater.cpp` 안에 정의되어 있으므로 extractor가 해당 record의
완전한 정의가 끝나는 지점까지 정확한 소스 prefix를 복사하고, 그 뒤의 무관한 함수 구현은 파싱하지
않습니다. 원본 전체 hash, 잘라낸 prefix hash와 종료 줄을 provenance로 기록하며 record가 없거나
모호하면 hard failure로 처리합니다.

```bash
python3 scripts/extract-bambustudio-abi.py \
  --source-dir /path/to/BambuStudio \
  --output abi-values.json \
  --compiler "$(xcrun --find clang++)" \
  --std c++17 \
  --compiler-arg=-I/path/to/generated/includes \
  --compiler-arg=-I/path/to/dependency/includes
```

선택한 record에 영향을 주는 정확한 compiler, SDK, 생성 헤더, compile definition과 dependency
헤더는 여전히 필요합니다. 하지만 dependency library, 애플리케이션 object, link, package,
`dsymutil`은 필요하지 않습니다. 따라서 runner에서는 헤더와 생성 설정만 담은 작은 버전별
**ABI sysroot**를 cache하고 이 probe를 수초~수분 안에 실행하는 방향이 적합합니다. Symbol 주소는
별도의 바이너리 추출 대상으로 유지합니다.

`extract-bambustudio-abi.py`는 단일 record-layout probe와 훨씬 작은 ConfigOption vtable probe를
동시에 시작한 뒤 결과를 선택한 버전의 value catalog에 맞춰 병합합니다. vtable 생성을
분리한 것은 의도적입니다. 큰 `Plater.cpp` probe에 코드 생성을 활성화하는 것보다 syntax-only record
pass와 작은 `Config.hpp` probe를 나란히 실행하는 편이 더 빠릅니다. 하위 도구인
`extract-clang-layouts.py`와 `extract-clang-vtables.py`도 각각 독립적으로 사용할 수 있습니다.

reusable/manual **Extract layout ABI** workflow는 1단계에서 cache한 정확한 dependency prefix를
복원하고 BambuStudio를 빌드하거나 link하지 않은 채 이 소스 probe를 실행합니다. Cache miss 시 긴
dependency 빌드를 암묵적으로 시작하지 않고 실패합니다. 업로드 artifact에는 요청된 모든 값과 함께 해석된
upstream commit, dependency tree, runner image, compiler, probe 인자와 소스 slice hash가 들어갑니다.

검토가 끝난 결과는 `abi-layouts/<BambuStudio-version>/` 아래에 저장합니다. `macos-arm64.json` 같은
target 파일은 정확한 릴리스 identity, 검토된 symbol/event와 그룹별 숫자 layout을 포함하는 완전한
런타임 프로파일입니다. 같은 위치의 `manifest.json`은 target 파일 SHA-256을 source, release, catalog,
generator 및 workflow provenance와 결합합니다. 두 독립 extractor가 모두 성공한 target만 추가하며
지원하지 않는 플랫폼의 빈 placeholder 파일은 만들지 않습니다.

## 1단계 실행 방법

**Actions → Build macOS dSYM → Run workflow**에서 다음 값을 입력합니다.

- `bambu_ref`: `v02.08.02.60` 같은 upstream tag, upstream branch 또는 40자리 전체 commit
- `rebuild_dependencies`: 일치하는 dependency cache를 무시할 때만 활성화

workflow는 수동 실행만 허용합니다. Pull request나 일반 push로 임의 BambuStudio revision을 실행할 수 없습니다. upstream URL은 고정되어 있고 입력 ref를 검증하며 job의 저장소 권한은 read-only입니다.

최초 workflow는 현재 BambuStudio macOS toolchain 조건인 `macos-15`, CMake 3.31.0, Ninja, Release, deployment target 10.15, `BuildMac.sh -1`을 따릅니다. 첫 ABI 대상이 Apple Silicon slice이므로 upstream universal 빌드에서 architecture만 의도적으로 `-a arm64`로 제한하며, 이 차이는 manifest에 기록합니다. Hosted runner image는 계속 바뀌므로 실제 image와 모든 tool version도 함께 기록합니다.

선택한 revision의 workflow contract가 다르면 macOS 빌드를 시작하기 전에 1단계를 중단합니다. 새로운 contract 지원은 호환될 것이라고 추측하는 대신 이 프로젝트의 검토된 변경으로 추가해야 합니다.

## 산출물

`bambustudio-macos-arm64-dsym-<commit>` artifact에는 다음 파일이 포함됩니다.

```text
BambuStudio.app.dSYM/
BambuStudio-LICENSE
manifest.json
toolchain.txt
binary-uuids.txt
dsym-uuids.txt
```

Actions artifact는 중간 빌드 근거이며 만료됩니다. 장기 보관 대상은 큰 dSYM 묶음이 아니라 이후 생성할 작은 ABI 레이아웃 manifest와 provenance입니다.

## 신뢰와 재현성 원칙

- `https://github.com/bambulab/BambuStudio.git`의 공개 소스만 입력으로 허용합니다.
- 해석된 commit, `deps` Git tree, upstream version, runner image, Xcode, SDK, compiler, CMake, Ninja, flags, 해시, architecture와 UUID를 기록합니다.
- dependency cache는 upstream dependency tree와 실제 runner image로 구분합니다. 반복 시간을 줄이는 수단일 뿐 호환성의 증명으로 사용하지 않습니다.
- version string, source tag, hash 또는 UUID가 유사하다는 이유만으로 생성 레이아웃이 설치 바이너리와 일치한다고 간주하지 않습니다.
- 필요한 구조, symbol 또는 바이너리 근거를 명확하게 검증할 수 없으면 consumer는 안전하게 실패해야 합니다.

## 개발

Shell script는 Bash strict mode를 사용하고 어느 working directory에서도 실행할 수 있도록 작성합니다.
private 멤버 추출을 확인하는 작은 Clang fixture를 포함한 로컬 검사는 다음과 같이 실행합니다.

```bash
./tests/test-scripts.sh
```

전체 빌드는 GitHub-hosted macOS runner가 필요하며 선택한 upstream revision의 코드를 실행합니다. 실행 전 workflow 변경 내용을 검토하십시오.

## 라이선스

이 저장소의 자동화 및 분석 코드는 [Apache License 2.0](LICENSE)으로 배포됩니다. BambuStudio와 그 소스·빌드 결과물에는 BambuStudio 자체 라이선스 및 third-party notice가 적용됩니다.
