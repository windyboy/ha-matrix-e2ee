# 使用指南

[English](USAGE.md) | [中文](USAGE.zh.md)

介绍 `matrix_e2ee` 集成提供的服务、事件、自动化示例以及诊断实体。

## 服务、事件与自动化

### 服务

| 服务 | 字段 | 说明 |
|---|---|---|
| `matrix_e2ee.send_message` | `message`, `room_id` | 目标房间必须在 `allowed_rooms` 中。在加密房间中遇到未验证设备时会严格阻断发送。 |
| `matrix_e2ee.reauthenticate` | `password` | 仅用于软退出（soft logout）。更新访问令牌（access token）；保留原 `device_id` 和加密存储。**仅限管理员。** |
| `matrix_e2ee.start_verification` | `user_id`, `device_id` | 目标设备必须已存在于加密存储中。确认前不会建立信任。**仅限管理员。** |
| `matrix_e2ee.confirm_verification` | `transaction_id` | 唯一将设备标记为已验证的步骤。**仅限管理员。** |
| `matrix_e2ee.cancel_verification` | `transaction_id` | 取消进行中的 SAS 验证。**仅限管理员。** |
| `matrix_e2ee.get_fingerprint` | （无） | 发出包含机器人公钥的 `matrix_e2ee_fingerprint` 事件。 |
| `matrix_e2ee.verify_device_by_fingerprint` | `user_id`, `device_id`, `ed25519` | 严格匹配时建立单向本地信任。**仅限管理员。** |

仅限管理员调用的服务由 Home Assistant 的 admin-service 机制强制限制。

### 事件

| 事件 | 负载（不包含密钥） |
|---|---|
| `matrix_e2ee_command` | 仅包含 `room_id`、`sender`、`command`、`args` —— 绝不包含原始消息正文 |
| `matrix_e2ee_error` | `code` 及非机密上下文字段（参见[错误码](TROUBLESHOOTING.zh.md#错误码)） |
| `matrix_e2ee_verification` | `stage`、`transaction_id`、`user_id`、`device_id`；可选 `emojis`、`expires_at` |
| `matrix_e2ee_message_received` | `sender`、`room_id`；可选 `event_id` |
| `matrix_e2ee_verification_done` | `peer_user_id`、`peer_device_id`、`timestamp` |
| `matrix_e2ee_fingerprint` | `user_id`、`device_id`、`ed25519`、`curve25519` —— 仅包含公钥 |

SAS emoji 核对可在“选项”向导中进行，高级场景也可在“开发者工具”中通过 `matrix_e2ee_verification` 事件（`stage: sas`）完成。确认（confirm）是唯一将设备标记为已验证的步骤。接受入站 SAS 启动请求属于协议流程延续，并不代表信任。

指令触发 `matrix_e2ee_command` 事件，附带 `room_id`、`sender`、`command` 和 `args`（若 Matrix 提供还包含 `event_id` / `thread_parent`）。已接收的入站文本还会触发 `matrix_e2ee_message_received` 事件；绝不暴露消息正文。本集成从不自行调用 `domain.service`，请在自动化中映射处理指令。

`notify.matrix_e2ee` 已推迟实现。不存在 `matrix_e2ee_message` 事件。

### 自动化示例

当门磁传感器触发时发送消息：

```yaml
automation:
  - alias: "前门打开时通知 Matrix"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: matrix_e2ee.send_message
        data:
          room_id: "!yourRoomId:example.org"
          message: "前门已打开"
```

响应入站 Matrix 指令（将 `!ping` 映射为回复）：

```yaml
automation:
  - alias: "Matrix !ping 指令"
    trigger:
      - platform: event
        event_type: matrix_e2ee_command
        event_data:
          command: ping
    action:
      - service: matrix_e2ee.send_message
        data:
          room_id: "{{ trigger.event.data.room_id }}"
          message: "pong"
```

在软退出后重新认证（仅限管理员；若界面有重新认证提示，优先使用界面）：

```yaml
automation:
  - alias: "Matrix 软退出重新认证"
    trigger:
      - platform: event
        event_type: matrix_e2ee_error
        event_data:
          code: soft_logout
    action:
      - service: matrix_e2ee.reauthenticate
        data:
          password: !secret matrix_bot_password
```

## 实体与诊断

### 连接状态二进制传感器

本集成提供了一个诊断连接性实体：

- **实体**：`binary_sensor.*_connection`（名称：**Connection**）
- **设备类型 (Device class)**：connectivity
- **类别**：diagnostic
- **开启 (On)**：机器人已连接且未处于软退出状态
- **属性**（无机密）：`soft_logged_out`、`device_id`、`known_device_count`、`verified_peer_count`、`verified_peers`（最多 10 组 `{user_id, device_id}` 对；仅对端设备，不包含机器人自身）

### 机器人活动事件实体

`event.*_bot_activity` 记录最新接收到的活动，事件类型包括 `message`、`command` 和 `verification_done`。它与连接传感器归属于同一个机器人设备，采用推送驱动；不暴露任何消息正文或密钥材料。

### 配置条目诊断

**设置 → 设备与服务 → Matrix E2EE → ⋮ → 下载诊断信息** 可导出脱敏快照：

| 字段 | 含义 |
|---|---|
| `integration_version` | 来自 `manifest.json` 的版本号 |
| `nio_version` | 已安装的 `matrix-nio` 版本（若可导入） |
| `client.user_id` | 机器人 Matrix 用户 ID |
| `client.device_id` | 机器人设备 ID |
| `client.session_present` | Session 会话文件是否已恢复 |
| `client.store_present` | 加密存储目录是否存在 |
| `client.soft_logged_out` | 软退出状态锁 |
| `client.encryption_enabled` | 在本集成中恒为 `true` |
| `client.store_sync_tokens` | 在本集成中恒为 `true` |
| `client.known_device_count` | 机器人设备存储中的设备数 |
| `client.verified_peer_count` | 机器人已标记为验证的设备数 |

诊断信息绝不包含访问令牌、pickle 密钥、密码、消息正文或加密材料。

## 相关文档

- [设备验证](DEVICE_VERIFICATION.zh.md)：分步 SAS 与指纹验证说明。
- [故障排查](TROUBLESHOOTING.zh.md)：错误码、恢复手册与灾难恢复。
- [安全模型](../SECURITY.md)：信任边界、存储保护与密钥泄露处置。
