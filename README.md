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
6. **受控点位写入通道**：仅操作者可下发，提交留痕、按操作者回看

## 受控点位写入通道
- `POST /api/auth/login` 登录获取 token（操作者 `operator1/operator123`，只读查看者 `viewer1/viewer123`）
- `POST /api/modbus/write` 受控下发（仅操作者，Header 携带 `Authorization: Bearer <token>`）：
  提交前校验点位存在性与数值范围，不满足时说明原因且不改变原值；
  同一点位上一次下发未结束时以先到为准，后来的提交返回 409 提示，可稍后重试
- `GET /api/modbus/write-records?operator=` 按操作者回看下发记录（谁、何时、哪个点位、改成多少、结果与原因）
- `GET /api/modbus/points` 点位台账（是否可写、允许范围、当前值）
- 只读查看者仅可查看实时读数，下发与记录查询均返回 403；实时读取与查询接口口径不变

## 启动
```bash
cd frontend && npm install && npm run dev
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8002
```

## 测试
```bash
cd backend && python3 tests/test_write_channel.py
```
