# BambuStudio ABI Layouts

[English](README.md)

BambuStudio ABI Layouts는 공개된 [BambuStudio](https://github.com/bambulab/BambuStudio) 소스 코드로부터 C++ ABI 레이아웃 근거를 재구성하는 독립 오픈 소스 빌드·분석 프로젝트입니다.

설치된 BambuStudio를 다시 빌드하거나 대체하지 않고 연동해야 하는 확장 런타임, 호환성 어댑터, 진단 도구 등을 위한 프로젝트입니다. 첫 번째 단계에서는 선택한 upstream revision을 Release 최적화와 독립적인 DWARF 정보가 포함되도록 빌드하고, 생성된 macOS dSYM과 빌드 과정을 감사할 수 있는 provenance를 함께 보존합니다. 이후 별도 단계에서 DWARF를 작고 검토 가능한 클래스·멤버 레이아웃 manifest로 변환합니다.

이 프로젝트는 Bambu Lab과 제휴 관계가 아니며 Bambu Lab의 보증을 받지 않습니다.

## 필요한 이유

export symbol은 보통 설치된 바이너리에서 직접 확인할 수 있습니다. 반면 C++ 오브젝트와 멤버 offset을 특정 사용처의 명령어만으로 복원하면 컴파일러 최적화나 평범한 소스 변경에도 탐지가 쉽게 깨집니다.

컴파일러가 생성한 타입 정보는 더 강한 소스 기반 근거를 제공합니다. 대응하는 공개 revision에서 만든 dSYM의 DWARF에는 record 크기, 상속 관계, 멤버 위치가 포함될 수 있습니다. 이후 설치된 바이너리의 구조적 근거와 함께 검증하면 어댑터가 레이아웃을 받아들일지 더 보수적으로 판단할 수 있습니다.

다만 이것은 근거이지 자동 호환성 보장은 아닙니다.

- 재빌드한 dSYM의 Mach-O UUID는 보통 Bambu Lab 배포 앱과 다릅니다. UUID가 일치하는 공식 dSYM처럼 배포 바이너리 symbolication에 사용하면 안 됩니다.
- 소스 revision만으로 C++ ABI 전체가 결정되지는 않습니다. Xcode, Apple Clang, SDK, deployment target, CMake 옵션, dependency revision, 생성 헤더와 compile definition도 결과에 영향을 줍니다.
- 빌드 provenance가 불완전하거나 대상 바이너리 검증이 모호하면 해당 레이아웃은 사용할 수 없는 상태로 남겨야 합니다.

## 파이프라인

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
동시에 시작한 뒤 결과를 `config/bambustudio-abi-values.json`의 34개 값으로 병합합니다. vtable 생성을
분리한 것은 의도적입니다. 큰 `Plater.cpp` probe에 코드 생성을 활성화하는 것보다 syntax-only record
pass와 작은 `Config.hpp` probe를 나란히 실행하는 편이 더 빠릅니다. 하위 도구인
`extract-clang-layouts.py`와 `extract-clang-vtables.py`도 각각 독립적으로 사용할 수 있습니다.

수동 **Extract macOS arm64 ABI layouts** workflow는 1단계에서 cache한 정확한 dependency prefix를
복원하고 BambuStudio를 빌드하거나 link하지 않은 채 이 소스 probe를 실행합니다. Cache miss 시 긴
dependency 빌드를 암묵적으로 시작하지 않고 실패합니다. 업로드 artifact에는 34개 값과 함께 해석된
upstream commit, dependency tree, runner image, compiler, probe 인자와 소스 slice hash가 들어갑니다.

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
