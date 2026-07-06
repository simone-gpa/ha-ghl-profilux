# ha-ghl-profilux

Integrazione custom per Home Assistant per il controller d'acquario **GHL ProfiLux 4/4e** tramite **connessione locale WebSocket** (`ws://<ip>/ws`).

> **Protocollo non ufficiale.** GHL non ha mai pubblicato la specifica del protocollo — questa integrazione è basata sul reverse engineering della community (vedi [profilux-go](https://github.com/cjburchell/profilux-go), Apache-2.0). Un aggiornamento firmware GHL potrebbe romperla. Non siamo affiliati a GHL.
>
> **L'acquario è un sistema critico.** I comandi di scrittura (prese, Feed Pause, Manutenzione) modificano lo stato del controller — usarli con cautela. Non commandare prese governate da timer o da automazioni ProfiLux: questa integrazione controlla solo prese già in modalità manuale.

## Prerequisiti

- Home Assistant 2024.11 o superiore
- GHL ProfiLux **4 o 4e** (ProfiLux 3 richiede un protocollo diverso, non supportato)
- Firmware recente sul controller
- **WebSocket interface abilitato** sul ProfiLux:
  GHL Control Center → Impostazioni → Interfacce web → abilita WebSocket

## Installazione via HACS

1. HACS → **Integrazioni** → menu (⋮) → **Repository personalizzati**
2. Aggiungi `https://github.com/lutrib/ha-ghl-profilux` come tipo **Integrazione**
3. Cerca "GHL ProfiLux" e clicca **Scarica**
4. Riavvia Home Assistant

## Configurazione

1. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → "GHL ProfiLux"**
2. Inserisci:
   - **Indirizzo IP** del ProfiLux (es. `192.168.1.50`)
   - **Username** (default: `admin`)
   - **Password** del controller

L'integrazione apre una connessione WebSocket persistente e rileva automaticamente le sonde e le prese presenti.

## Entità create

### Sensori (rilevati automaticamente in base alle sonde connesse)

| Tipo sonda | Unità | Note |
|-----------|-------|------|
| Temperatura | °C | |
| pH | pH | |
| Redox/ORP | mV | |
| Conducibilità | µS/cm | |
| Umidità | % | |
| Ossigeno | mg/L | |
| Tensione | V | |
| Temperatura aria | °C | |

### Binary sensor
- **Allarme** — `problem`: True se c'è un allarme attivo sul ProfiLux
- **Prese non manuali** — `power`: stato on/off in sola lettura (prese gestite da timer/automazioni ProfiLux)

### Switch
- **Prese in modalità manuale** — on/off controllabile. Solo le prese già in modalità AlwaysOn/AlwaysOff nel ProfiLux vengono esposte come switch.

### Pulsanti
- **Avvia/Termina pausa alimentazione** — Feed Pause
- **Avvia/Termina manutenzione** — Maintenance mode

## Limitazioni note e avvertenze

- **Connessioni multiple**: il ProfiLux gestisce male più connessioni WebSocket simultanee. Non tenere aperto GHL Control Center o l'app GHL Connect mentre questa integrazione è attiva.
- **Prese**: solo le prese già in modalità manuale nel ProfiLux possono essere controllate da HA. Le prese con timer, automazioni ProfiLux o funzioni speciali sono esposte solo in lettura.
- **Scritture in EEPROM**: i comandi di switch scrivono la modalità della presa nella EEPROM del ProfiLux (persistente al riavvio). Feed Pause e Maintenance sono comandi volatili.
- **Protocollo da verificare su hardware reale**: il parsing dei frame e gli offset dei codici sono stati derivati dalla community — segnala eventuali anomalie aprendo una issue con il debug logging attivato.

## Debug logging

Aggiungi a `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.ghl_profilux: debug
```

## Diagnostica

In **Impostazioni → Dispositivi e servizi → GHL ProfiLux → ⋮ → Scarica diagnostica** trovi lo stato completo del coordinator (seriale oscurato automaticamente).

## Riferimenti tecnici

- Protocollo ProfiLux (Go, Apache-2.0): [cjburchell/profilux-go](https://github.com/cjburchell/profilux-go)
- Implementazione WS Python: [fylia32/HA_GHL_PROFILUX](https://github.com/fylia32/HA_GHL_PROFILUX)
- Thread community Reef2Reef: [Smart home integration of GHL Profilux](https://www.reef2reef.com/threads/smart-home-integration-of-ghl-profilux.435799/)

## Licenza

MIT — vedi [LICENSE](LICENSE).
