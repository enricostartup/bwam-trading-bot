# Audit del wallet e baseline storica

Generato: 2026-09-08T17:43:11.776642+00:00

## Verdetto

**NO-GO per denaro reale; GO soltanto per forward paper trading.** Il campione storico non dimostra eseguibilità reale: OHLCV a un minuto non contiene mempool latency, price impact individuale, transazioni fallite o MEV.

## Campione

- Finestra richiesta: 14 giorni
- Finestra effettivamente restituita dalla sorgente: 6.18 giorni
- Storico troncato dalla sorgente: sì
- Launch osservati: 1049
- Migrazioni: 35 (3.34%)
- Frequenza media sul periodo osservato: 5.67 migrazioni/giorno
- Token migrati con OHLCV utilizzabile: 35
- Ingressi che superano il filtro market cap: 28
- Esclusi dal filtro market cap: 7
- Token migrati senza OHLCV utilizzabile: 0
- Ritardo mediano launch → prima candela del pool: 6.1 minuti

## Baseline dichiarata prima del test

Ingresso: apertura della prima candela disponibile almeno 60 secondi dopo la prima candela del pool. Uscita: take profit +50%, stop -30% o 60 minuti. Se TP e SL compaiono nella stessa candela, viene contato prima lo stop. Capitale $50.00; costo per tratta 250 bps + $0.15.

- Rendimento netto mediano: -33.96%
- Win rate: 28.57%
- Rendimento netto medio: -12.29%
- Profit factor: 0.493
- Esiti: TP 8, stop 20, timeout 0

## Sensibilità (non ottimizzazione)

| Variante | N | Media netta | Mediana netta | Win rate | Profit factor |
|---|---:|---:|---:|---:|---:|
| instant_50tp_30sl_60m | 35 | -20.96% | -33.96% | 17.14% | 0.255 |
| delay1m_50tp_30sl_60m | 28 | -12.29% | -33.96% | 28.57% | 0.493 |
| delay2m_50tp_30sl_60m | 22 | -6.38% | -33.96% | 36.36% | 0.705 |
| delay5m_50tp_30sl_60m | 16 | -4.12% | -33.96% | 37.50% | 0.792 |
| delay1m_25tp_20sl_15m | 28 | -10.18% | -24.48% | 32.14% | 0.365 |
| delay1m_100tp_30sl_60m | 28 | -16.74% | -33.96% | 14.29% | 0.425 |

Le varianti sono state fissate per controllare la robustezza a ritardo e uscite, non per scegliere retrospettivamente la migliore. Più righe testate aumentano il rischio di data snooping.

## Limiti che impediscono conclusioni forti

1. L’endpoint Pump.fun usato è pubblico ma non è un contratto di servizio stabile.
2. La prima candela GeckoTerminal approssima la migrazione; non è un timestamp di fill.
3. Le candele a un minuto creano ambiguità intrabar e nascondono slippage/MEV.
4. La sorgente ha troncato lo storico a 1.049 launch (6,18 giorni effettivi) e il risultato può dipendere dal regime di mercato.
5. Le metriche del creator riportate da tracker terzi non sono un audit contabile.
6. L’ultimo prezzo scambiato non garantisce che una posizione della size ipotizzata sia liquidabile a quel prezzo.

Il criterio “market cap > 30k” non seleziona molto se l’ingresso avviene **dopo** la migrazione: la graduation stessa avviene normalmente a una capitalizzazione superiore. Va trattato come controllo anti-crollo al momento del rilevamento, non come fonte di edge.

## Cosa significa davvero “safe”

La documentazione ufficiale Pump.fun dice che, dopo la graduation, il pool canonico appartiene al protocollo: il creator non può semplicemente ritirare quella liquidità. È una protezione contro il classico liquidity rug, non contro vendite, sniper, concentrazione degli holder o un crollo del 90%.

L’affermazione assoluta “questo creator non vende” è falsa almeno in un caso direttamente visibile: nella cronologia del token `AE3jmK…Kk8r`, Solscan mostra 268.249.999,999999 token trasferiti dalla bonding curve al wallet e poi dal wallet indietro alla bonding curve. Inoltre, due token migrati controllati durante questo audit non risultavano più nei token account del wallet. Questo non prova un rug; prova che “non vende mai” non è una premessa utilizzabile.

TokenRadar etichetta il deployer “Serial rugger” e mostra 32 token “safe” su 6.979 indicizzati. È una classificazione euristica di terzi e non viene usata come verità nel backtest, ma contraddice l’idea che la reputazione “tutte safe” sia pacifica.

## Fonti

- [Wallet su Solscan](https://solscan.io/account/bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa)
- [Bonding curve e migrazione, documentazione Pump.fun](https://pump.fun/docs/bonding-curve)
- [Fee schedule Pump.fun/PumpSwap](https://pump.fun/docs/fees)
- [Programma Pump ufficiale](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md)
- [Esempio di acquisto e restituzione dei token del creator](https://solscan.io/account/AE3jmKsufnYbBUaZ1rFXQZLmsA6mxaEf151a4VfnKk8r)
- [Profilo euristico TokenRadar](https://tokenradar.app/deployers/bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa)
