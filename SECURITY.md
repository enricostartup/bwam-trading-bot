# Security policy

Questo progetto non contiene e non accetta seed phrase, private key o file wallet.

- Segnala privatamente eventuali vulnerabilità al maintainer del repository.
- Non aprire issue contenenti credenziali o dati personali.
- `mode` è intenzionalmente limitato a `paper`; una patch che aggiunge firma o invio di transazioni richiede un audit separato.
- Gli endpoint dati sono input non fidati: il motore deve continuare a fallire chiuso sugli ingressi quando schema o disponibilità cambiano.

