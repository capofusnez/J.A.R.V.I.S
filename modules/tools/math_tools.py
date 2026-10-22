class MathTools:
    def calcola_percentuale(self, valore: float, percentuale: float) -> str:
        risultato = (valore * percentuale) / 100.0
        return f"Il {percentuale}% di {valore} è pari a {risultato}."

    def calcola_potenza(self, base: float, esponente: float) -> str:
        risultato = base ** esponente
        return f"{base} elevato a {esponente} dà come risultato {risultato}."
