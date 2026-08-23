# 故障排查

[English](TROUBLESHOOTING.md) | [中文](TROUBLESHOOTING.zh.md)

`matrix_e2ee` 错误码速查与常见运行故障恢复手册。

## 错误码

`matrix_e2ee_error` 事件携带 `code` 字段（绝不包含机密）。常见错误码：

| 错误码 | 含义 | 典型处理方式 |
|---|---|---|
| `soft_logout` | 访问令牌失效；同一设备可重新登录 | 调用 `reauthenticate` 服务或使用界面的重新认证提示 |
| `hard_logout` | 令牌失效且非软退出 | 删除 session 和 store，移除集成后重新添加并重新验证 |
| `store_missing` | 加密存储目录丢失 | 视为新设备；不可单独复用残留的 session 文件 |
| `session_missing` | 恢复路径缺少 session 文件 | 使用密码进行首次登录 / 重新配置 |
| `session_corrupt` | session 文件无法读取或损坏 | 删除 session（若不一致也删除 store），重新配置 |
| `restore_failed` | 无法从 session/store 恢复客户端 | 检查日志；通常需要重新配置 |
| `password_required` | 需要密码但未提供 | 在登录 / 重新认证时提供密码 |
| `login_failed` | 主服务器拒绝登录 | 检查凭据和主服务器 URL |
| `device_mismatch` | 重新认证会导致 `device_id` 改变 | 不写入新令牌；这不是升级到新设备的途径 |
| `room_not_allowed` | `room_id` 不在 `allowed_rooms` 中 | 将房间加入允许列表或发送到其他房间 |
| `send_failed` | 发送失败（非信任原因） | 检查网络连接和房间成员资格 |
| `unverified_device` | 加密发送被阻断：存在未验证/未知设备 | 为这些设备完成 SAS（或指纹）验证 |
| `encryption_unavailable` | 端到端加密路径不可用 | 检查 nio/store；正常安装下不应出现 |
| `device_missing` | 目标设备不在加密存储中 | 等待获取设备密钥 / 仅对已知设备发起验证 |
| `fingerprint_mismatch` | 手动核对指纹与存储不匹配 | 重新核对密钥；切勿强行信任 |
| `invalid_transaction` | SAS `transaction_id` 未知或已过期 | 发起新的验证 |
| `invalid_state` | 客户端状态异常时调用了服务 | 检查软退出 / 连接状态；恢复后重试 |
| `verification_timeout` | 集成 240 秒验证窗口超时 | 从 Element 重新发起 SAS 验证 |
| `verification_peer_denied` | 发起者非机器人账号且不在 `verification_peer_users` 中 | 调整允许列表或由允许的用户发起 |
| `refresh_token_unsupported` | 服务器返回了刷新令牌/短期令牌 | 使用标准密码登录获取长期访问令牌（不使用令牌刷新） |

## 恢复手册

Session JSON 文件与加密存储均保存在 Home Assistant 主机上，并已加入 gitignore。本项目为公开仓库：切勿提交令牌、pickle 密钥、密码或存储文件。

安全诊断信息（无令牌、pickle 密钥、密码或消息正文）可通过**下载诊断信息**及 **Connection** 二进制传感器获取 —— 参见[实体与诊断](USAGE.zh.md#实体与诊断)。

**Session 文件与加密存储必须始终成对备份与恢复。** 单独的 session JSON 无法恢复 Megolm 历史记录；缺少 session 文件中匹配的 `pickle_key`，加密存储亦毫无用处。若两者不匹配，必须视为新设备处理。

### 软退出（`matrix_e2ee_error` 错误码 `soft_logout`）

访问令牌已失效，但主服务器仍允许同一设备重新登录。集成会**保留** `.storage/matrix_e2ee_store/` 和现有的 `device_id`。在重新认证成功之前，消息发送、入站指令、SAS 验证和同步将保持阻断。

在初始配置时，软退出会在集成卡片上显示**重新认证**提示（原生 reauth 流程）。在运行时，可通过服务重新认证：

1. 使用机器人账号密码调用 `matrix_e2ee.reauthenticate`（开发者工具 → 服务，或通过自动化）。密码仅需提供给此服务。
2. 成功后，session 文件**仅更新访问令牌**。`device_id` 和 `pickle_key` 保持不变，加密存储继续复用。
3. 若主服务器返回了不同的 `device_id`，则**不会**写入新令牌（报 `device_mismatch` 错误），旧 session 继续保留。这不是迁移到新设备的途径。

密码绝不会出现在事件、日志行或服务返回值中。

### 硬退出（`hard_logout`）

令牌已失效且**不是**软退出。配置将**失败**。**切勿**复用旧加密存储。

1. 若仍可行，在主服务器上撤销旧设备。
2. 删除 `<config>/.storage/matrix_e2ee_session.json` **和** `<config>/.storage/matrix_e2ee_store/`。
3. 在**设置 → 设备与服务**中删除该集成，然后通过界面重新添加，使首次登录创建**新**设备。
4. 重新执行 SAS 验证（`start_verification` / `confirm_verification`）。旧历史消息将无法解密。

### 加密存储丢失（`store_missing`）

须视为新设备处理。单独的 session JSON 不足以恢复 Megolm 历史记录。删除残留的 session 文件，然后按照硬退出步骤操作（新登录 + SAS 验证）。切勿将旧存储复制到新设备上。

### 密钥泄露或主机被窃

1. 在主服务器上撤销旧 Matrix 设备。
2. 销毁本地 session 文件与加密存储（路径同上）。
3. 首次登录将创建新设备。
4. 对需要信任的设备重新执行 SAS 验证。先前的密文无法恢复。

### 迁移至新的 Home Assistant 主机（正规迁移）

1. 停止旧主机上的 Home Assistant（或禁用集成），避免机器人在两处同时连接。
2. 将 `<config>/.storage/matrix_e2ee_session.json` **与** `<config>/.storage/matrix_e2ee_store/` **一并**复制到新主机的对应路径。两者必须保持成对匹配。
3. 在新主机的 `custom_components` 下安装相同版本的 `matrix_e2ee` 并重启。
4. 通过**设置 → 设备与服务**重新添加集成（向导仍会要求输入密码；检测到 session 文件存在时，客户端会恢复同一 `device_id` 而非创建新设备）。若存储或 session 丢失或不匹配，须视为新设备并重新验证。

### 短期 / 刷新令牌（`refresh_token_unsupported`）

本集成不支持轮换刷新令牌。若登录或 `reauthenticate` 收到了刷新令牌或短期访问令牌（`expires_in_ms`），集成将拒绝持久化保存该会话。请使用长期访问令牌（不使用令牌刷新的标准密码登录）。

## 相关文档

- [使用指南](USAGE.zh.md)：服务、事件、自动化与诊断实体。
- [设备验证](DEVICE_VERIFICATION.zh.md)：分步 SAS 与指纹验证说明。
- [安全模型](../SECURITY.md)：信任边界、存储保护与密钥泄露处置。
