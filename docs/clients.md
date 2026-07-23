# MCP 클라이언트 연결 가이드

Cloudcraft MCP `0.1.6`은 로컬 `stdio` 서버입니다. PyPI, npm, GHCR 배포본은
동일한 Python 서버를 실행하며 네트워크 요청은 사용자가 지정한 Cloudcraft API로만
보냅니다.

| 배포 방식 | 고정된 식별자 | 로컬 요구 사항 |
| --- | --- | --- |
| PyPI / uvx | `cloudcraft-mcp==0.1.6` | Python을 자동 관리하는 `uv` |
| npm / npx | `@hypark5540/cloudcraft-mcp@0.1.6` | Node.js 22 이상과 `uv` |
| OCI / Docker | `ghcr.io/hypark5540/cloudcraft-mcp:0.1.6` | Docker 또는 호환 OCI 런타임 |
| MCP Registry | `io.github.hypark5540/cloudcraft-mcp` | 선택한 패키지 런타임 |

## API 키 준비와 보안

[Cloudcraft](https://app.cloudcraft.co/)의 User settings에서 API 키를 만듭니다.
이 키는 현재 세분화된 MCP 전용 권한이 아니라 Cloudcraft 계정의 blueprint 읽기와
변경 작업을 허용할 수 있으므로 비밀번호처럼 취급해야 합니다.

- 키를 명령행 인수, Git 저장소, Dockerfile 또는 이미지 레이어에 넣지 마세요.
- 가능하면 클라이언트의 secret 입력 UI나 운영체제 credential store를 사용하세요.
- 환경변수를 사용할 때는 MCP 클라이언트 프로세스에만 `CLOUDCRAFT_API_KEY`를
  전달하세요. 디버그 로그나 화면 공유에도 값을 노출하지 마세요.
- 처음 연결한 뒤 `whoami`로 대상 계정을 확인하고, 생성·수정·삭제 요청은 MCP
  클라이언트의 승인 화면에서 대상 blueprint ID를 다시 확인하세요.
- 생성·수정은 `CLOUDCRAFT_ENABLE_WRITES=true`로 명시적으로 켜야 합니다. 삭제는
  `CLOUDCRAFT_ENABLE_DELETES=true`도 필요하며 호출할 때 정확한 blueprint ID를 한 번 더
  전달해야 합니다. 두 기능은 기본적으로 꺼져 있습니다.

서버가 인식하는 선택 환경변수는 다음과 같습니다.

| 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `CLOUDCRAFT_BASE_URL` | `https://api.cloudcraft.co` | 신뢰할 수 있는 HTTPS 프록시 또는 loopback 테스트 서버 |
| `CLOUDCRAFT_LOG_LEVEL` | `WARNING` | stderr 로그 수준 |
| `CLOUDCRAFT_EXPORT_DIR` | 프로세스 전용 임시 하위 디렉터리 | 이미지 내보내기가 쓸 수 있는 루트 디렉터리 |
| `CLOUDCRAFT_ENABLE_WRITES` | `false` | blueprint 생성·수정 허용 |
| `CLOUDCRAFT_ENABLE_DELETES` | `false` | 쓰기와 함께 irreversible delete 허용 |
| `CLOUDCRAFT_MAX_RESPONSE_BYTES` | `26214400` | API 응답당 허용하는 최대 바이트 수 |

## 설치 경로 확인

API 키 없이도 버전 출력은 가능하므로 실제 비밀을 입력하기 전에 설치 경로를 확인할
수 있습니다.

```bash
uvx --from cloudcraft-mcp==0.1.6 cloudcraft-mcp --version
npx -y @hypark5540/cloudcraft-mcp@0.1.6 --version
docker run --rm ghcr.io/hypark5540/cloudcraft-mcp:0.1.6 --version
```

npm 패키지는 검증된 Python wheel을 포함한 실행기이며 `uv`를 하위 프로세스로
사용합니다. `uv`가 기본 `PATH`에 없다면 `CLOUDCRAFT_MCP_UV`에 신뢰할 수 있는
절대 경로를 지정할 수 있습니다.

## Cursor

사용자 설정이나 프로젝트의 `.cursor/mcp.json`에 다음 항목을 추가합니다. 실제 키
대신 Cursor의 환경변수 참조를 사용합니다.

```json
{
  "mcpServers": {
    "cloudcraft": {
      "command": "uv",
      "args": ["tool", "run", "--isolated", "--from", "cloudcraft-mcp==0.1.6", "cloudcraft-mcp"],
      "env": {
        "CLOUDCRAFT_API_KEY": "${env:CLOUDCRAFT_API_KEY}",
        "CLOUDCRAFT_LOG_LEVEL": "WARNING",
        "CLOUDCRAFT_ENABLE_WRITES": "false",
        "CLOUDCRAFT_ENABLE_DELETES": "false"
      }
    }
  }
}
```

Cursor를 시작하는 환경 또는 Cursor의 secret 관리 기능에 API 키를 설정하고 앱을
재시작합니다. 프로젝트 설정 파일에 실제 키를 쓰지 마세요.

## Claude Desktop

GitHub Release의 `cloudcraft-mcp-0.1.6.mcpb`를 지원되는 Claude Desktop에 설치하면
설정 화면에서 API 키를 secret 값으로 입력할 수 있습니다. 함께 게시된 SHA-256 파일과
provenance가 있다면 설치 전에 검증하세요.

MCPB를 지원하지 않는 버전에서는 Claude Desktop 설정의 `mcpServers`에 저장소의
[`mcp.example.json`](../mcp.example.json)과 같은 stdio 항목을 추가합니다. 설정 형식이
환경변수 참조를 지원하지 않으면 클라이언트 secret store를 사용하고, 불가피하게
설정 파일에 키를 저장할 때는 파일 권한과 운영체제 계정을 제한하세요.

## Gemini CLI

저장소의 `gemini-extension.json`은 API 키를 `sensitive` 설정으로 선언합니다.

```bash
gemini extensions install https://github.com/hypark5540/cloudcraft-mcp --ref=v0.1.6
gemini extensions config cloudcraft-mcp
```

설치 검토 화면을 확인한 뒤 Cloudcraft API 키를 입력합니다. 확장은 고정된
`@hypark5540/cloudcraft-mcp@0.1.6` npm 패키지를 stdio로 실행합니다.

## Codex와 ChatGPT Desktop

Codex CLI/IDE의 `~/.codex/config.toml`에는 값이 아니라 전달할 환경변수 이름을
등록할 수 있습니다.

```toml
[mcp_servers.cloudcraft]
command = "uv"
args = ["tool", "run", "--isolated", "--from", "cloudcraft-mcp==0.1.6", "cloudcraft-mcp"]
env_vars = ["CLOUDCRAFT_API_KEY"]

[mcp_servers.cloudcraft.env]
CLOUDCRAFT_LOG_LEVEL = "WARNING"
CLOUDCRAFT_ENABLE_WRITES = "false"
CLOUDCRAFT_ENABLE_DELETES = "false"
```

Codex 또는 로컬 MCP를 지원하는 ChatGPT Desktop을 시작한 프로세스 환경에
`CLOUDCRAFT_API_KEY`가 있어야 합니다. ChatGPT 웹은 로컬 `stdio` 명령을 직접 실행할
수 없으므로 별도로 배포한 원격 MCP 서버 없이는 이 설정을 사용할 수 없습니다.

## Claude Code와 기타 stdio 클라이언트

Claude Code가 API 키를 상속하는 환경에서 다음처럼 사용자 범위 서버를 등록합니다.

```bash
claude mcp add --scope user cloudcraft -- uv tool run --isolated --from cloudcraft-mcp==0.1.6 cloudcraft-mcp
claude mcp get cloudcraft
```

다른 stdio 클라이언트도 `command`, `args`, `env`를 지원한다면 같은 구성을 사용할 수
있습니다. 해당 클라이언트가 환경변수 참조를 해석하지 않으면 문자열
`${CLOUDCRAFT_API_KEY}`를 그대로 넣지 말고 클라이언트의 secret 입력 방식을
사용하세요.

## Docker로 격리 실행

호스트 환경의 키를 값 없이 전달하면 키가 명령 기록에 복사되지 않습니다. `-i`는
stdio 연결에 필수입니다.

```bash
docker run --rm -i \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  -e CLOUDCRAFT_API_KEY \
  ghcr.io/hypark5540/cloudcraft-mcp:0.1.6
```

내보낸 파일을 유지해야 할 때만 전용 호스트 디렉터리를 컨테이너에 마운트하고
`CLOUDCRAFT_EXPORT_DIR`을 그 경로로 설정하세요. 광범위한 홈 디렉터리나 Docker
socket을 마운트하지 마세요.

연결 후에는 `whoami`, `list_blueprints`처럼 읽기 도구부터 시험하고, 클라이언트가
표시하는 도구 주석과 승인 프롬프트를 확인한 뒤 변경 도구를 사용하세요.
