"""
Script para executar testes de integração do FamaGPT
"""

import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from test_integration import run_integration_tests


async def main():
    """Função principal para executar os testes"""
    print("=" * 60)
    print("🧪 SISTEMA DE TESTES - FAMAGPT")
    print("=" * 60)
    print()
    
    try:
        await run_integration_tests()
        print("\n✅ Todos os testes foram executados!")
        
    except KeyboardInterrupt:
        print("\n⏹️  Testes interrompidos pelo usuário")
        
    except Exception as e:
        print(f"\n❌ Erro durante execução dos testes: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)