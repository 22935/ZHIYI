# 端—边—云真实联调演示

这个目录提供三个独立 HTTP 进程：

- `terminal_node.py`：端节点；
- `edge_node.py`：边节点；
- `cloud_node.py`：云端资源注册、签名执行和显式故障转移协调器。

运行以下命令可以执行完整验收流程，输出机器可读 JSON：

```powershell
python tools/edge_cloud_demo/run_demo.py --work-dir .tmp/edge-cloud-demo
```

流程包括：资源注册并只返回一次 secret、节点配置、节点签名心跳、边节点签名执行、边节点故障后的云端重绑定、边进程退出后的再次重绑定、边进程重启后的心跳恢复。

演示使用临时 HTTP 服务和 SQLite 数据库，不代表生产部署拓扑。注册 secret 只在进程内用于配置节点，最终报告会主动脱敏，不输出 secret。生产环境仍应通过正式的资源注册 API、密钥托管和 TLS 部署。
