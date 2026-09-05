# RUNBOOK RB-RAN-03: 5G gNodeB Signaling & Authentication Storm

## Metadata
- **Runbook ID**: `RB-RAN-03`
- **Domain**: 5G Radio Access Network (RAN) / Core Signaling
- **Applies To**: `gNB-*`, `5G-RAN`, `NG-C`, `S1-MME`, `AMF`
- **Severity**: P2 - High / P3 - Medium
- **Symptoms**:
  - `AUTH_FAILURE_BURST` (Exponential increase in 5G NAS Authentication rejects)
  - `NGAP_SETUP_FAILURE` or `S1AP_TRANSPORT_TIMEOUT`
  - High control plane latency (>300ms) on cell tower baseband unit (BBU)
  - Radio Resource Control (RRC) connection rejection rate > 15%

## Triage Verification Steps
1. Query gNodeB NG-C/S1 signaling association status:
   ```bash
   show ran gnb ngap-status
   show ran gnb rrc-stats cell-id all
   ```
2. Verify AMF/MME signaling health and reachability:
   ```bash
   ping 10.240.12.1 source 10.240.34.5 count 20
   show ran ipsec tunnel amf-primary status
   ```
3. Check for IoT / rogue UE reconnect burst:
   ```bash
   show ran nas-reject-reasons detail
   ```

## Immediate Mitigation Actions
1. **Section 3.1 - Apply Access Barring & Signaling Throttling**:
   Enable Unified Access Control (UAC) / Call Gapping to throttle rogue registration storms:
   ```bash
   set ran cell midtown-sector-1 uac-barring factor 50 time 30
   set ran control-plane rate-limit ng-nas max-tps 250
   ```
2. **Section 3.2 - Reset Baseband Signaling Daemon**:
   If NGAP stack is hung on BBU:
   ```bash
   restart process ran-ngap-daemon graceful
   ```
3. **Section 3.3 - Verify Core AMF Capacity**:
   Contact 5G Core operations desk to verify AMF slice capacity and subscriber database (UDM/HSS) response times.

## Safety Warnings
- Never execute a full hard reboot on active gNodeB sector during peak hours without establishing emergency 911 carrier fallback.
