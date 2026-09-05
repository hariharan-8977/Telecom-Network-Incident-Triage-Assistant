# RUNBOOK RB-MEM-04: MPLS Core/Aggregation Router Memory Exhaustion & Buffer Bloat

## Metadata
- **Runbook ID**: `RB-MEM-04`
- **Domain**: Router System OS / Control Plane Hardware
- **Applies To**: `CR-*`, `AGG-*`, `Metro-Ethernet`, `MPLS-Router`
- **Severity**: P2 - High
- **Symptoms**:
  - `HIGH_MEMORY_USAGE` (RAM > 92% and growing monotonically)
  - `BUFFER_ALLOCATION_FAILURE` in forwarding engine logs
  - Drop tail queue discards on egress line cards (`PACKET_DROP_QUEUE`)
  - Slow CLI response time and delayed SNMP polling responses

## Triage Verification Steps
1. Inspect memory consumption by subsystem process:
   ```bash
   show system memory detail
   show system processes top | grep -E "fib|rib|kernel|bgp"
   ```
2. Verify packet buffer pools and shared memory ring health:
   ```bash
   show interfaces queue-buffers detail
   show system forwarding-engine memory-summary
   ```

## Immediate Mitigation Actions
1. **Section 4.1 - Flush Route Caches & Dynamic Rib Tables**:
   Release orphaned routing table memory buffers:
   ```bash
   request system route-cache flush dynamic
   ```
2. **Section 4.2 - Non-Stop Routing (NSR) Engine Switchover**:
   Switch active control plane to standby Routing Engine (RE1):
   ```bash
   request chassis routing-engine master switch
   ```
3. **Section 4.3 - Isolate Buggy Daemon**:
   If specific telemetry or SNMP daemon is leaking heap memory:
   ```bash
   restart process telemetry-agent graceful
   ```

## Safety Warnings
- Ensure Standby RE is in `Ready / In-Sync` state prior to switchover to prevent transient control plane blackhole.
