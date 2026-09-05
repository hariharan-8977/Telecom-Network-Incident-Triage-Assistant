# RUNBOOK RB-PWR-05: Cell Site Commercial Power Failure & Battery Float Depletion

## Metadata
- **Runbook ID**: `RB-PWR-05`
- **Domain**: Facility / Energy Systems / Cell Site Infrastructure
- **Applies To**: `PWR-SITE-*`, `gNB-*`, `Power-UPS`, `Facility`
- **Severity**: P1 - Critical / P2 - High
- **Symptoms**:
  - `MAINS_AC_POWER_FAIL` alarm from site rectifier
  - Rectifier switches to `BATTERY_DISCHARGE_ACTIVE` mode
  - Battery DC voltage drops below 48.0V (Standard float: 54.0V)
  - Estimated remaining runtime alert (`EST_BATTERY_RUNTIME_LOW < 90m`)

## Triage Verification Steps
1. Query Site Rectifier & Smart Battery Management Controller:
   ```bash
   show facility power site-status
   show battery string detail
   ```
2. Verify AC mains input phase voltage (L1/L2/L3) and utility grid status:
   ```bash
   show power grid-infeed-status
   ```
3. Check backup generator auto-start controller status:
   ```bash
   show generator telemetry status
   ```

## Immediate Mitigation Actions
1. **Section 5.1 - Manual Remote Generator Crank**:
   If automatic transfer switch (ATS) failed to start stationary generator:
   ```bash
   request facility generator start force
   ```
2. **Section 5.2 - Radio Power Shedding (Energy Save Mode)**:
   Extend battery backup longevity by down-powering massive MIMO antenna panels and carrier aggregation secondary carriers:
   ```bash
   set ran cell power-saving-mode aggressive
   shutdown radio-carrier sector-all band-77-n78
   ```
3. **Section 5.3 - Emergency Mobile Generator Dispatch**:
   If battery voltage < 46.5V and generator fails to ignite, dispatch local emergency mobile diesel generator trailer (ETA SLA < 60 min).

## Safety Warnings
- Never attempt remote ATS overrides if a physical smoke or fire alarm is active at the shelter.
