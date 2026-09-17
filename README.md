# solo-6600020: Modbus 工业协议数据采集监控大屏

## 技术栈
- Frontend: Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS + ECharts
- Backend: Python FastAPI + pymodbus

## 核心特性
1. **Modbus RTU/TCP 寄存器实时读取**：pymodbus 连接工业设备
2. **时序曲线 ECharts 绘制**：实时趋势图，多寄存器对比
3. **阈值告警 WebSocket 推送**：温度/压力超限自动告警
4. **设备拓扑 SVG 图**：可视化设备布局与在线状态
5. **采集任务调度**：可调轮询间隔，设备启停控制
6. **受控点位下发通道**：写入归属鉴权 + 提交前校验 + 并发去重 + 全量审计回看

## 受控下发通道
下发不再对任何人放开，所有受控接口需在请求头携带 `X-Operator-Id`：

- **写入归属**：仅 `role=operator` 且点位在其归属名单内的操作者可下发；
  `viewer`（只读查看者）只能看实时读数，任何下发/审计访问返回 403。
- **提交前校验**：目标点位必须存在（422）、数值必须在量程内（422，布尔点位
  仅接受 `true/false`）；不满足时返回原因，**原值不改变**，刷新/重新读取仍可
  看出本次下发未生效。
- **并发去重**：同一点位上一次下发未结束（pending）时，后来的提交返回 409，
  以先到的一次为准，并提示后来者；该记录可重试。
- **异步执行与重试**：受理返回 `202` 与审计记录，后台模拟设备下发；设备离线
  等失败标记 `retryable=true`，可凭原记录一键重试（仅本人、仅可重试记录）。
- **审计回看**：每次提交记录「谁、什么时间、哪个点位、由多少改成多少、结果与
  原因」，可按操作者/点位过滤（`GET /api/modbus/writes?mine=true`）。
- **读取口径不变**：`GET /api/modbus/devices`、`GET /api/modbus/read/...` 无需
  身份、返回结构保持原样。

### 主要接口
| 方法 | 路径 | 说明 | 身份 |
| --- | --- | --- | --- |
| GET | `/api/operators` | 操作者与写入归属名单 | 否 |
| GET | `/api/modbus/points` | 点位目录（量程/可写/当前值/在线） | 否 |
| GET | `/api/modbus/read/{dev}/{addr}/{count}` | 实时读寄存器（口径不变） | 否 |
| POST | `/api/modbus/write/{dev}/{addr}` | 受控下发，body `{"value": 30.5}` | 操作者 |
| GET | `/api/modbus/writes?mine=true` | 审计回看（可按 `operator_id`/点位过滤） | 操作者 |
| GET | `/api/modbus/writes/{id}` | 查询单条下发结果（仅本人） | 操作者 |
| POST | `/api/modbus/writes/{id}/retry` | 重试失败/冲突的下发（仅本人） | 操作者 |
| PATCH | `/api/modbus/devices/{id}/online?online=true` | 设备恢复上线 | 操作者 |

演示账号（见 `backend/app/services/operator_service.py`）：
`op001`（A区温度/湿度/露点）、`op002`（B区压力）、`op003`（C区电机）、
`viewer001`（只读访客）。

## 启动
```bash
cd frontend && npm install && npm run dev
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8002
```
