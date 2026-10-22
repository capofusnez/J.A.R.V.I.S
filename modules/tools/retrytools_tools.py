class RetryTools:
    def run(self, text: str = "") -> str:
        # Simula un tentativo di esecuzione con un numero massimo di ripetizioni
        max_attempts = 3
        attempt = 1
        while attempt <= max_attempts:
            try:
                # Simula un'operazione che potrebbe fallire
                result = self._simulate_operation(text)
                return f"Successo dopo {attempt} tentativi: {result}"
            except Exception as e:
                if attempt == max_attempts:
                    return f"Fallito dopo {max_attempts} tentativi: {str(e)}"
                attempt += 1
                print(f"Tentativo {attempt} fallito. Riprovando...")

    def _simulate_operation(self, text: str) -> str:
        # Simula un'operazione che potrebbe fallire
        if text == "errore":
            raise ValueError("Operazione fallita")
        return f"Operazione completata con successo: {text}"