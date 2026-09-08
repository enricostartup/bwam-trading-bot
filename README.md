# Bwam Migration Paperbot

Monitor e simulatore **solo paper trading** per le coin Pump.fun create da:

`bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa`

Il bot entra soltanto quando l’API segnala contemporaneamente `complete=true` e un `pool_address`, applica i filtri di market cap e registra prezzi, posizioni, costi e PnL in SQLite. Non contiene chiavi private, builder di transazioni, firme o un’opzione live nascosta.

## Verdetto sintetico

L’idea merita un forward test, ma **non merita ancora capitale reale**. Nel campione salvato (1.049 launch, 35 migrazioni; storico troncato a 6,18 giorni), 28 ingressi superano il filtro $30k. La baseline con ingresso ritardato di un minuto produce rendimento netto medio −12,29%, mediano −33,96%, win rate 28,57% e profit factor 0,493. Tutte le sei varianti di sensibilità restano negative. Il creator genera centinaia di tentativi al giorno; la selezione “solo migrate” elimina quasi tutti i fallimenti ma porta l’ingresso dopo la fase che ha già prodotto la maggior parte della selezione positiva. “Il dev non può togliere la liquidità migrata” non equivale a “il prezzo non può crollare” e non equivale a “il dev non vende i token comprati”. Leggi [research/REPORT_IT.md](research/REPORT_IT.md) per metodo e limiti.

## Avvio su Windows, macOS o Linux

Richiede Python 3.11+ e Git.

```bash
git clone https://github.com/enricostartup/bwam-trading-bot.git
cd bwam-trading-bot
python -m venv .venv
```

Attiva l’ambiente:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Poi:

```bash
python -m pip install -e .
cp config.example.json config.json
bwam-paperbot --config config.json run
```

Su Windows senza `cp`:

```powershell
Copy-Item config.example.json config.json
```

Una singola iterazione:

```bash
bwam-paperbot --config config.json run --once
```

Stato del conto paper:

```bash
bwam-paperbot --config config.json status
```

## Rifare l’analisi storica

```bash
bwam-paperbot --config config.json research --days 14 --output research
```

La raccolta OHLCV rispetta intenzionalmente un intervallo conservativo di 12,5 secondi tra richieste. I risultati vengono salvati in:

- `research/analysis_snapshot.json`
- `research/launches_snapshot.csv`
- `research/migration_backtest.csv`
- `research/REPORT_IT.md`

## Regole predefinite (ipotesi, non parametri ottimizzati)

- ingresso: prima osservazione entro 5 minuti dalla migrazione;
- market cap: $30k–$250k;
- size: $50;
- massimo 3 posizioni;
- stop: -30%;
- take profit: +50%;
- trailing: attivo da +30%, uscita dopo -20% dal picco;
- timeout: 60 minuti;
- costi simulati: 250 bps + $0,15 per tratta;
- stop giornaliero: -$50 realizzati.

Questi numeri sono volutamente espliciti e modificabili in `config.json`. Cambiarli dopo avere guardato il risultato storico crea overfitting; ogni variante va validata su dati futuri.

## Perché non c’è ancora il live trading

Un percorso live sensato richiede almeno:

1. 30–60 giorni di forward paper trading senza buchi di dati.
2. Fill simulati confrontati con quote eseguibili e price impact, non solo market cap.
3. Un RPC/indexer a bassa latenza con SLA e un feed di migrazione on-chain.
4. Wallet dedicato, capitale limitato, allowlist del programma, simulazione della transazione, slippage cap e kill switch indipendente.
5. Test di spegnimento, riavvio, doppio evento, reorg/finalità e API indisponibile.

Collegare un wallet prima di questi passaggi trasformerebbe un esperimento misurabile in un rischio operativo non quantificato.

## Sorgenti dati e fragilità

Il prototipo usa l’endpoint pubblico frontend di Pump.fun per discovery/marking e GeckoTerminal per l’analisi OHLCV. Sono dipendenze non garantite: possono cambiare schema, applicare rate limit o diventare indisponibili. Il motore fallisce chiuso per gli ingressi e registra gli errori; non interpreta dati mancanti come un segnale.

## Test

```bash
python -m unittest discover -s tests -v
```

## Sicurezza

- `mode` accetta soltanto `paper`.
- `config.json`, `.env` e database runtime non vengono versionati.
- Non incollare mai seed phrase o private key in questo repository.
- Le memecoin possono perdere quasi tutto il valore anche con liquidità bloccata.

Licenza MIT. Software sperimentale, non consulenza finanziaria.
