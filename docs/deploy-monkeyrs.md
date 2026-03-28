# `your-domain.example` 部署建议

> 状态说明：本文档描述当前推荐的正式部署路径，对应现有 `docker-compose.prod.yml` 和 `scripts/server-up.sh`。如后端架构继续调整，务必同步更新部署脚本和本文档。

推荐使用同一个主域名拆成两个入口：

- `https://your-domain.example`：个人网站
- `https://your-domain.example/xcx`：微信小程序后端 API

这样做的原因：

- 小程序正式上线要求把请求域名配置为 HTTPS 合法域名
- 个人网站和 API 逻辑隔离，后续好加管理后台
- 不需要把 `:8000` 暴露给公网

## DNS 记录

至少配置这两条：

- `@  -> A -> YOUR_SERVER_IP`
- `www -> A -> YOUR_SERVER_IP`

## 服务器目录

- 代码目录：`/root/teamhome`
- 个人网站目录：`/var/www/your-domain.example`
- 证书校验目录：`/var/www/certbot`

## 首次启动后端

```bash
cd /root/teamhome
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml build api langgraph
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml up -d api langgraph
docker compose -f docker-compose.prod.yml ps
curl http://127.0.0.1:8000/openapi.json
```

## 后续更新

```bash
bash /root/teamhome/scripts/server-up.sh
```

`server-up.sh` 当前会执行：

- 拉取最新代码
- 生产环境安全预检
- 启动数据库
- 构建 `api` / `langgraph`
- 执行 Alembic 迁移
- 强制重建并拉起服务
- 检查 OpenAPI 健康状态

## Nginx

把 `docs/nginx-monkeyrs.conf` 放到服务器的 `/etc/nginx/conf.d/monkeyrs.conf`

然后执行：

```bash
nginx -t
systemctl reload nginx
```

## 证书

推荐用已有 `your-domain.example` 证书，或为 `your-domain.example` / `www.your-domain.example` 申请证书：

```bash
mkdir -p /var/www/certbot
dnf install -y certbot python3-certbot-nginx || yum install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.example -d www.your-domain.example
```

证书签发成功后，Nginx 会自动补全 443 配置。

## 微信小程序后台

把业务域名配置成：

- `https://your-domain.example/xcx`

不要再使用：

- `http://YOUR_SERVER_IP:8000`
- `http://your-domain.example:8000`
- `https://your-domain.example:8000`

## 备注

- 正式环境默认 API 入口是 `https://your-domain.example/xcx`
- 本地联调请用前端本地覆盖配置，不要改动仓库默认正式地址
- 生产部署前先检查 `backend/.env` 中的 `ENVIRONMENT`、`JWT_SECRET`、`CORS_ALLOW_ORIGINS`、微信配置和调试开关
