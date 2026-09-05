# RUNBOOK RB-BGP-02: BGP Route Flapping & Peering Session Instability

## Metadata
- **Runbook ID**: `RB-BGP-02`
- **Domain**: IP/MPLS Core & Peering Routing
- **Applies To**: `CR-*`, `AGG-*`, `MPLS-Router`, `BGP`
- **Severity**: P2 - High
- **Symptoms**:
  - `BGP_SESSION_FLAP` (Rapid state transitions: ESTABLISHED <-> IDLE/ACTIVE)
  - `HOLD_TIMER_EXPIRED` log events
  - High CPU utilization on routing engine process (rpd / bgp_agent > 80%)
  - Route table churn causing micro-burst packet loss and high latency across metro rings

## Triage Verification Steps
1. Identify flapping BGP peer neighbor and flap count:
   ```bash
   show bgp summary | grep Flaps
   show bgp neighbor <peer_ip> flap-statistics
   ```
2. Verify Keepalive / Hold time timers (standard 30s / 90s):
   ```bash
   show bgp neighbor <peer_ip> timers
   ```
3. Test MTU size and transport connectivity across peer peering interfaces:
   ```bash
   ping <peer_ip> size 1500 do-not-fragment count 10
   ```

## Immediate Mitigation Actions
1. **Section 2.1 - Enable Route Flap Damping (RFD)**:
   Apply flap dampening profile to suppress unstable prefix advertisements before they flood the internal IBGP mesh:
   ```bash
   set protocols bgp group EXTERNAL-PEERS damping half-life 15 reuse 750 suppress 2000 max-suppress 60
   ```
2. **Section 2.2 - Quarantine Flapping Peer**:
   If single peer neighbor flaps > 5 times in 10 minutes:
   ```bash
   set protocols bgp neighbor <peer_ip> shutdown "Automated NOC quarantine: excessive flap rate"
   ```
3. **Section 2.3 - Verify Alternative Transit Routing**:
   Confirm traffic gracefully shifts to secondary upstream transit or IXP peering link without packet drops.

## Safety Warnings
- Do not shut down internal IBGP sessions (`iBGP`) connecting primary core nodes unless isolating a hardware fault.
- Coordinate with upstream peer NOC before clearing damping states.
