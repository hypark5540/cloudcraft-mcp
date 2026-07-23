# Release guide

Cloudcraft MCP `0.1.6`은 하나의 Python 구현을 다음 공개 형식으로 배포합니다.

- PyPI: `cloudcraft-mcp==0.1.6`
- npm: `@hypark5540/cloudcraft-mcp@0.1.6`
- OCI/GHCR: `ghcr.io/hypark5540/cloudcraft-mcp:0.1.6`
- MCP Registry: `io.github.hypark5540/cloudcraft-mcp`
- GitHub Release: Claude Desktop용 `cloudcraft-mcp-0.1.6.mcpb`와 checksum
- Gemini CLI: `v0.1.6` 태그의 `gemini-extension.json`

npm 패키지는 별도 JavaScript 서버가 아니라 빌드된 Python wheel과 `uv` 실행기를
담습니다. PyPI wheel, npm에 포함된 wheel, MCPB에 포함된 서버가 같은 소스와 버전을
가리키는지 릴리스 검증에서 확인해야 합니다. 버전이 지정된 레지스트리 아티팩트와 Git
태그는 변경 불가능한 것으로 취급합니다.

## 릴리스 전 일회성 설정

### PyPI Trusted Publishing

PyPI의 `cloudcraft-mcp` 프로젝트에 다음 GitHub OIDC publisher를 등록합니다.

- Owner: `hypark5540`
- Repository: `cloudcraft-mcp`
- Workflow: `publish.yml`
- Environment: `pypi`

기존 `0.1.5`는 덮어쓰지 않습니다. GitHub environment에는 승인자와 보호된 `v*`
태그 규칙을 적용하고 장기 PyPI API token은 저장하지 않습니다.

### npm Trusted Publishing

npm은 OIDC trusted publisher를 설정하기 전에 패키지가 존재해야 할 수 있습니다.
`@hypark5540/cloudcraft-mcp`가 아직 없다면 실행 코드와 의존성이 없는 `0.0.0`
bootstrap tarball을 `bootstrap` dist-tag로 한 번만 게시한 뒤 GitHub publisher를
설정합니다. npm 계정의 2FA를 켜고 브라우저 로그인만 사용합니다.

```bash
npx --yes --package=node@24.18.0 --package=npm@11.18.0 \
  --call 'npm login --auth-type=web'

npx --yes --package=node@24.18.0 --package=npm@11.18.0 \
  --call 'npm run build:npm-bootstrap'

npx --yes --package=node@24.18.0 --package=npm@11.18.0 \
  --call 'npm publish release-artifacts/npm-bootstrap/*.tgz --access public --tag bootstrap'

npx --yes --package=node@24.18.0 --package=npm@11.18.0 \
  --call 'npm trust github @hypark5540/cloudcraft-mcp --repo hypark5540/cloudcraft-mcp --file publish.yml --env release --allow-publish --yes'
```

bootstrap tarball은 게시 전에 반드시 펼쳐 보고 `package.json`, `README.md`,
`LICENSE` 외 실행 파일이나 의존성이 없는지 확인합니다. OIDC 게시가 성공하면 token
기반 publish를 차단하고 bootstrap 버전을 폐기 안내합니다.

### GHCR와 MCP Registry

처음 푸시된 개인 계정의 GHCR 패키지는 private일 수 있습니다. MCP Registry 게시
전에 `ghcr.io/hypark5540/cloudcraft-mcp`를 Public으로 전환하고 익명 pull을
확인합니다. `release`와 `mcp-registry` GitHub environment에는 필요한 최소 권한만
부여합니다. 저장소 secret에 Cloudcraft API 키, npm token, PyPI token 또는 GHCR
PAT를 넣지 않습니다.

MCP Registry 이름 `io.github.hypark5540/cloudcraft-mcp`의 GitHub 소유권 검증과
publisher 로그인을 최초 릴리스 전에 완료합니다. `server.json`에 선언된 npm, PyPI,
OCI 세 패키지가 모두 공개되고 정확한 `0.1.6` 버전을 제공한 뒤 Registry 항목을
게시합니다.

## 버전 일치 항목

태그를 만들기 전에 아래 위치가 모두 `0.1.6`인지 확인합니다.

- `pyproject.toml`, `uv.lock`, `src/cloudcraft_mcp/__init__.py`
- `package.json`, lockfile, npm에 포함되는 wheel 이름
- `server.json`의 서버 버전, package 버전, OCI tag
- `gemini-extension.json`, MCPB manifest
- `Dockerfile`의 기본 `VERSION`
- `README.md`, `mcp.example.json`, 버전이 고정된 client/release 문서

MCP 이름은 항상 `io.github.hypark5540/cloudcraft-mcp`, npm 이름은
`@hypark5540/cloudcraft-mcp`, PyPI 이름은 `cloudcraft-mcp`이어야 합니다. 이름을
버전 문자열과 함께 기계적으로 검사해 오타가 있는 릴리스를 차단합니다.

## 로컬 사전 검증

Cloudcraft API 키 없이 다음 검증을 실행합니다. 통합 테스트가 명시적으로 필요한
경우에만 격리된 테스트 계정 키를 별도 secret store에서 주입합니다.

```bash
uv sync --locked --extra dev
uv run ruff check src tests
uv run mypy src
uv run pytest
uv build

npm run deps:locked
npm run check
npm pack --dry-run
```

Docker가 있는 환경에서는 잠긴 Python base digest와 `uv.lock`만 사용해 이미지를 두
번 빌드하고 런타임 버전을 확인합니다.

```bash
docker build \
  --build-arg VERSION=0.1.6 \
  --build-arg REVISION="$(git rev-parse HEAD)" \
  -t ghcr.io/hypark5540/cloudcraft-mcp:0.1.6 .

docker run --rm ghcr.io/hypark5540/cloudcraft-mcp:0.1.6 --version
```

Docker build context에는 `.env`, registry 설정, private key가 포함되지 않으며 API
키를 build argument로 받지 않습니다. 컨테이너는 비루트 UID로 stdio 서버를
실행합니다.

## 태그와 자동 배포

검증된 변경을 커밋한 뒤 이동하지 않을 annotated tag를 만들고 푸시합니다.

```bash
git tag -a v0.1.6 -m "cloudcraft-mcp 0.1.6"
git push origin v0.1.6
```

릴리스 workflow는 태그의 소스를 한 번 checkout한 뒤 다음 순서로 동작해야 합니다.

1. 테스트, 정적 검사, 버전 일치, stdio handshake를 실행합니다.
2. wheel/sdist, npm tarball, MCPB, OCI 이미지를 만들고 재현성 및 포함 파일을
   검증합니다.
3. GitHub OIDC로 PyPI와 npm에 게시하고 GHCR image, provenance, SBOM을 푸시합니다.
4. 검증한 MCPB와 checksum을 GitHub Release에 첨부합니다.
5. 세 package registry의 공개 상태와 버전을 확인한 뒤 `server.json`을 MCP
   Registry에 게시합니다.

각 publish job은 필요한 동안에만 `id-token: write`, `packages: write`,
`contents: write` 중 해당 권한을 가져야 합니다. 빌드와 테스트 job에는 쓰기 권한을
주지 않습니다.

## 게시 후 확인

새 셸과 빈 도구 캐시에서 공개 아티팩트를 직접 확인합니다.

```bash
uvx --refresh --from cloudcraft-mcp==0.1.6 cloudcraft-mcp --version
npx --yes @hypark5540/cloudcraft-mcp@0.1.6 --version
docker pull ghcr.io/hypark5540/cloudcraft-mcp:0.1.6
docker run --rm ghcr.io/hypark5540/cloudcraft-mcp:0.1.6 --version

curl -fsSL https://pypi.org/pypi/cloudcraft-mcp/0.1.6/json
npm view @hypark5540/cloudcraft-mcp@0.1.6 version dist.integrity
```

GitHub Release checksum과 provenance, GHCR manifest의 source revision, MCP Registry의
세 package identifier도 태그와 일치해야 합니다. 마지막으로 테스트 계정으로 MCP
stdio handshake와 `whoami`를 실행하되 키나 API 응답을 CI 로그에 출력하지 않습니다.

## 실패와 재시도 정책

여러 registry의 publish는 원자적이지 않습니다. 일부 형식이 먼저 게시된 뒤 다른
job이 실패하면 원래 태그와 검증된 artifact를 그대로 사용해 실패한 job만
재시도합니다. 같은 버전에 다른 바이트를 업로드하거나 release asset을 덮어쓰지
마세요.

소스, 메타데이터, dependency 또는 workflow를 바꿔야 한다면 `v0.1.6` 태그를
이동하지 말고 다음 patch 버전을 만듭니다. 이미 공개된 PyPI/npm 버전, 버전 OCI tag,
MCP Registry 항목과 GitHub Release asset은 모두 immutable로 취급합니다.
