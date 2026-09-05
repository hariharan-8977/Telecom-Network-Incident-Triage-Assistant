# RUNBOOK RB-OPT-01: Core Optical DWDM Fiber Cut & Span Failure

## Metadata
- **Runbook ID**: `RB-OPT-01`
- **Domain**: Optical Transport / DWDM / Core Transmission
- **Applies To**: `DWDM-CORE-*`, `Optical-DWDM`, `Optical-100G`
- **Severity**: P1 - Critical
- **Symptoms**:
  - `LOSS_OF_SIGNAL` (LOS) or `OPTICAL_POWER_LOW` on DWDM transponders
  - Multiple simultaneous BGP/OSPF neighbor drops across core router pairs
  - Sudden bidirectional packet loss (>90%) across inter-city spans
  - Cascading alarms on downstream aggregation switches (`LINK_DOWN`, `REMOTE_FAULT`)

## Triage Verification Steps
1. Verify Optical Supervisory Channel (OSC) status on transponder:
   ```bash
   show optical transponder osc status
   show interfaces dwdm opt-monitor detail
   ```
2. Check receive optical power (dBm). Normal range is -8 dBm to -15 dBm. If RX power < -30 dBm, physical fiber discontinuity exists.
3. Review Automatic Protection Switching (APS):
   - Confirm if optical protection switch engaged within 50ms:
   ```bash
   show protection-group optical 1 detail
   ```

## Immediate Mitigation Actions
1. **Section 1.1 - Force Protection Switchover**:
   If APS did not trigger automatically and optical standby path is healthy:
   ```bash
   protection-group optical 1 manual-switch to standby
   ```
2. **Section 1.2 - Dispatch Field OTDR Team**:
   Trigger automated OTDR (Optical Time-Domain Reflectometer) trace to locate physical break distance in kilometers:
   ```bash
   run otdr test span DWDM-CORE-NYC-BOS laser 1550nm
   ```
   Note the break location marker (e.g., Milepost 42.8 on Route 95 ROW) and dispatch regional fiber splicing team with ticket priority P1.
3. **Section 1.3 - Reroute L3 Traffic**:
   Temporarily increase IGP cost on affected core interfaces to divert transit traffic to secondary corridor (`DWDM-CORE-NYC-PHL`).

## Safety Warnings
- Do NOT gaze into exposed optical fiber connectors (Class 1M / Class 3B laser radiation).
- Ensure rerouting does not cause congestion overload exceeding 85% capacity on secondary links.
