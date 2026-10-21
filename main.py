import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

# Importa la nuova GUI cinematografica
from gui_v2 import StarkHUD

if __name__ == "__main__":
    # Inizializza l'applicazione PyQt6
    app = QApplication(sys.argv)
    
    # Imposta un font monospazio globale stile Stark
    app.setFont(QFont("Consolas", 10))
    
    # Avvia l'interfaccia HUD Mark.XXI
    window = StarkHUD()
    window.show()
    
    # Esegue il loop dell'applicazione
    sys.exit(app.exec())