# Package initializer for rag service to allow patching rag.main in tests.
"""RAG package initializer.
Expõe o módulo main para facilitar patch em testes (patch('rag.main.*')).
"""

from importlib import import_module as _imp

try:
	_main = _imp('rag.main')
	main = _main  # expõe como atributo do pacote
except Exception:  # pragma: no cover - se falhar inicialização pesada
	main = None

__all__ = ["main"]
