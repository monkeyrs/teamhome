# `your-domain.example` 部署建议

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
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/openapi.json
```

## 后续更新

```bash
bash /root/teamhome/scripts/server-up.sh
```

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
