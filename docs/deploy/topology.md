# Raincoat 部署拓扑

## 部署目标

- 与 `squirrel` 部署在同一台服务器
- 使用独立代码目录、独立容器、独立 Nginx location
- 采用同域不同路径

## 推荐服务器目录

```text
/srv/squirrel/
/srv/raincoat/
  app/
  data/
    uploads/
    runs/
    artifacts/
```

## 容器拓扑

```text
Nginx on host
  |
  |-- /         -> raincoat-web:3100
  |-- /reports  -> raincoat-web:3100
  |-- /api/*    -> raincoat-api:3200
  |-- /artifacts/* -> /srv/raincoat/data/artifacts/
```

## 与 Squirrel 并存

- `squirrel` 继续使用自己的目录和容器
- `raincoat` 不复用 `squirrel` 的应用目录
- 两边通过 Nginx 做路径或域名级隔离

## 发布方式

参考 `squirrel` 的本地发起发布：

1. 本地跑测试和构建
2. 打 git bundle
3. 上传到服务器
4. 服务器 checkout 指定 revision
5. `docker compose up -d --build`
6. 健康检查
