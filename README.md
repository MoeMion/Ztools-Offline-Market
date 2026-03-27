# Z-Tools 离线插件市场

构建可离线部署的 Z-Tools 插件市场静态镜像。

## 功能说明

- 自动解析最新 release tag，或使用手动指定的 tag
- 下载发布元数据和插件压缩包
- 每次重新构建前自动清理旧的输出目录
- 在可用时镜像插件 README 文件
- 镜像 README 中可下载的图片资源，并尽可能将 README 内的图片链接改写为本地路径
- 尽可能将插件、分类、README 和 source manifest 中暴露出的 URL 重写为本地离线路径
- 当某些外部图片下载失败时，保留原始外链，避免打包中断
- 构建与客户端兼容的静态 `market-data` 目录树
- 通过 Docker Compose + nginx 提供静态访问服务

## 快速开始

使用一条 Python 命令打包市场：

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080
```

使用一条 Docker 命令启动服务：

```bash
docker compose up -d --force-recreate
```

## 常见用法

使用上游最新 release：

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080
```

使用指定 tag：

```bash
python scripts/ztools_offline_market.py package --tag v2026.03.23.1338 --base-url http://127.0.0.1:18080
```

输出到自定义目录：

```bash
python scripts/ztools_offline_market.py package --base-url http://127.0.0.1:18080 --output custom-market-data
```

## 仓库结构

```text
scripts/
  ztools_offline_market.py   主 CLI 脚本

tests/
  test_build.py              构建与打包测试
  test_pull.py               拉取与 README 镜像测试
  test_verify.py             输出校验测试

docker/
  nginx.conf                 静态 nginx 配置

fixtures/
  sample_release/            最小测试样例数据

docs/
  operations.md              详细操作说明
```

## CLI 命令

- `package` —— 一条命令完成 pull + README 镜像 + build + verify
- `pull` —— 下载上游 release 资源到本地目录
- `build` —— 从输入目录构建可发布的静态市场目录
- `verify` —— 校验生成后的市场目录结构

## 说明

- 默认输出目录为 `market-data`。
- 当省略 `--tag` 时，工具会自动解析上游最新 release tag。
- Docker 默认从 `./market-data` 提供静态文件；如果使用自定义输出目录，请同步修改 `docker-compose.yml` 或重命名输出目录。
- 完整操作流程见 `docs/operations.md`。

## Vibe Coding 警告

本仓库完全由 Claude Code 生成，请自行评估并承担使用风险。
