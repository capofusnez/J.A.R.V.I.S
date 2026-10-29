"""Creazione guidata di nuovi moduli-strumento.

Il modello può SCRIVERE il codice di un nuovo modulo solo su richiesta esplicita dell'utente, e il codice
viene controllato staticamente prima di essere salvato. L'attivazione richiede sempre una conferma.

ATTENZIONE: non è un sandbox a prova di attacco. I controlli servono a bloccare gli errori e le
stranezze di un modello linguistico locale (accesso a file, rete, processi, introspezione), non un
attaccante determinato. Per questo l'utente può leggere il codice prima di installarlo.
"""
import ast
import re

ALLOWED_IMPORTS = {
    "math", "random", "secrets", "string", "re", "datetime", "calendar", "json", "statistics",
    "decimal", "fractions", "hashlib", "base64", "uuid", "textwrap", "itertools", "collections",
    "unicodedata", "typing", "functools", "operator",
}
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "open", "__import__", "input", "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "memoryview",
}
MAX_CODE_CHARS = 8000


def sanitize_module_name(raw: str) -> str:
    """'Convertitore Unità!' -> 'convertitore_unita' (solo lettere minuscole, cifre e underscore)."""
    name = (raw or "").lower().strip()
    name = (name.replace("à", "a").replace("è", "e").replace("é", "e")
                .replace("ì", "i").replace("ò", "o").replace("ù", "u"))
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_tools$", "", name)
    name = re.sub(r"_+", "_", name).strip("_")[:30]
    if name and not name[0].isalpha():
        name = "mod_" + name
    return name


def validate_code(code: str):
    """Controllo statico. Ritorna (errori, info): errori vuoto = il codice è accettabile."""
    errors = []
    if not code or not code.strip():
        return ["il codice è vuoto"], {}
    if len(code) > MAX_CODE_CHARS:
        errors.append("il codice è troppo lungo")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"errore di sintassi alla riga {e.lineno}"], {}

    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef)):
            pass
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            pass                                                      # docstring del modulo
        else:
            errors.append(f"istruzione non permessa a livello di modulo (riga {node.lineno})")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    errors.append(f"import non permesso: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                errors.append(f"import non permesso: {node.module or '.'}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            errors.append(f"funzione non permessa: {node.func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append(f"accesso non permesso a '{node.attr}'")
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id != "__name__":
            errors.append(f"nome non permesso: {node.id}")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.Global, ast.Nonlocal)):
            errors.append("costrutto non permesso (async/global/nonlocal)")

    tool_classes = [c for c in classes if c.name.endswith("Tools")]
    methods = []
    if len(tool_classes) != 1:
        errors.append("serve esattamente una classe il cui nome finisce per 'Tools'")
    else:
        for item in tool_classes[0].body:
            if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                methods.append((item.name, bool(ast.get_docstring(item))))
        if not methods:
            errors.append("la classe non ha metodi pubblici")
        elif not any(has_doc for _, has_doc in methods):
            errors.append("i metodi devono avere una breve descrizione (docstring)")

    errors = list(dict.fromkeys(errors))                              # senza duplicati, stesso ordine
    info = {"class_name": tool_classes[0].name if len(tool_classes) == 1 else None,
            "methods": [n for n, _ in methods]}
    return errors, info


def build_module_prompt() -> str:
    return (
        "Sei uno sviluppatore Python. Scrivi un piccolo modulo di strumenti per un assistente vocale.\n"
        "REGOLE:\n"
        '1. Una sola classe il cui nome finisce per "Tools" (es. UnitConverterTools).\n'
        "2. Metodi pubblici con type hint e UNA riga di docstring in italiano che dice cosa fanno. "
        "Restituiscono SEMPRE una stringa: una frase completa, pronta da leggere ad alta voce.\n"
        "3. Solo logica pura, offline. Import consentiti: " + ", ".join(sorted(ALLOWED_IMPORTS)) + ".\n"
        "4. Vietati: rete, file, processi, eval, exec, open, getattr e attributi con doppio underscore.\n"
        "5. Nessun codice eseguito all'import: solo import, costanti e la classe.\n"
        "6. Parametri semplici (int, float, str). Con input non valido restituisci un messaggio chiaro, "
        "senza sollevare eccezioni.\n"
        'Rispondi SOLO con JSON: {"module_name": "nome_breve_senza_tools", "python_code": "..."}'
    )
