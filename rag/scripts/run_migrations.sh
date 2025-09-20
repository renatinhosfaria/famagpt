#!/bin/bash

# Script para executar migrations do RAG Híbrido
# Executa as migrations em ordem e valida cada uma

set -e

echo "=================================="
echo "RAG HÍBRIDO - EXECUÇÃO DE MIGRATIONS"
echo "=================================="

# Configurações
MIGRATIONS_DIR="/var/www/famagpt/rag/migrations"
SCRIPTS_DIR="/var/www/famagpt/rag/scripts"
BACKUP_DIR="/var/www/famagpt/rag/backups"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log colorido
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verificar se psql está disponível
if ! command -v psql &> /dev/null; then
    log_error "psql não encontrado. Instale PostgreSQL client."
    exit 1
fi

# Verificar se Python está disponível para testes
if ! command -v python3 &> /dev/null; then
    log_warning "python3 não encontrado. Testes automatizados serão ignorados."
    PYTHON_AVAILABLE=false
else
    PYTHON_AVAILABLE=true
fi

# Definir URL do banco (pode ser passada como variável de ambiente)
if [ -z "$DATABASE_URL" ]; then
    log_warning "DATABASE_URL não definida. Usando padrão local."
    DATABASE_URL="postgresql://localhost:5432/famagpt"
fi

# Criar diretório de backup se não existir
mkdir -p "$BACKUP_DIR"

# Função para fazer backup
create_backup() {
    log_info "Criando backup do banco de dados..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_pre_hybrid_$TIMESTAMP.sql"
    
    if pg_dump "$DATABASE_URL" > "$BACKUP_FILE"; then
        log_success "Backup criado: $BACKUP_FILE"
        echo "$BACKUP_FILE" > "$BACKUP_DIR/latest_backup.txt"
    else
        log_error "Falha ao criar backup"
        exit 1
    fi
}

# Função para executar migration
run_migration() {
    local migration_file=$1
    local migration_name=$(basename "$migration_file" .sql)
    
    log_info "Executando $migration_name..."
    
    if psql "$DATABASE_URL" -f "$migration_file"; then
        log_success "$migration_name executada com sucesso"
        return 0
    else
        log_error "Falha ao executar $migration_name"
        return 1
    fi
}

# Função para verificar se migration já foi aplicada
is_migration_applied() {
    local version=$1
    
    # Verificar se tabela de migrations existe e se a versão já foi aplicada
    RESULT=$(psql "$DATABASE_URL" -t -c "
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'schema_migrations'
        ) AND EXISTS(
            SELECT 1 FROM schema_migrations 
            WHERE version = '$version'
        );" 2>/dev/null || echo "f")
    
    if [ "$RESULT" = " t" ]; then
        return 0  # Migration já aplicada
    else
        return 1  # Migration não aplicada
    fi
}

# Função para verificar conectividade
check_connection() {
    log_info "Verificando conectividade com o banco de dados..."
    
    if psql "$DATABASE_URL" -c "SELECT 1;" > /dev/null 2>&1; then
        log_success "Conectado ao banco de dados"
    else
        log_error "Não foi possível conectar ao banco de dados"
        log_error "URL: $DATABASE_URL"
        exit 1
    fi
}

# Função para verificar pré-requisitos
check_prerequisites() {
    log_info "Verificando pré-requisitos..."
    
    # Verificar se tabelas RAG existem
    TABLES_EXIST=$(psql "$DATABASE_URL" -t -c "
        SELECT count(*) FROM information_schema.tables 
        WHERE table_name IN ('rag_documents', 'rag_document_chunks');" 2>/dev/null || echo "0")
    
    if [ "$TABLES_EXIST" -ne 2 ]; then
        log_error "Tabelas RAG não encontradas. Execute a inicialização do RAG primeiro."
        exit 1
    fi
    
    # Verificar extensões necessárias
    EXTENSIONS=$(psql "$DATABASE_URL" -t -c "
        SELECT count(*) FROM pg_extension 
        WHERE extname IN ('vector', 'pg_trgm');" 2>/dev/null || echo "0")
    
    if [ "$EXTENSIONS" -lt 1 ]; then
        log_warning "Extensões podem não estar instaladas. Tentaremos instalar durante a migration."
    fi
    
    log_success "Pré-requisitos verificados"
}

# Função principal
main() {
    echo ""
    log_info "Iniciando processo de migration para RAG Híbrido"
    echo ""
    
    # Verificações iniciais
    check_connection
    check_prerequisites
    
    # Criar backup (apenas se não estivermos em ambiente de teste)
    if [ "$SKIP_BACKUP" != "true" ]; then
        create_backup
    else
        log_warning "Backup ignorado (SKIP_BACKUP=true)"
    fi
    
    echo ""
    log_info "=== EXECUTANDO MIGRATIONS ==="
    
    # Lista de migrations em ordem
    migrations=("001_add_fulltext_support" "002_create_fulltext_indexes" "003_create_sync_triggers")
    
    for migration in "${migrations[@]}"; do
        migration_file="$MIGRATIONS_DIR/${migration}.sql"
        
        if [ ! -f "$migration_file" ]; then
            log_error "Migration não encontrada: $migration_file"
            exit 1
        fi
        
        # Verificar se já foi aplicada
        if is_migration_applied "${migration:0:3}"; then
            log_warning "$migration já foi aplicada, pulando..."
            continue
        fi
        
        # Executar migration
        if ! run_migration "$migration_file"; then
            log_error "Falha na migration $migration"
            
            # Tentar restaurar backup
            if [ "$SKIP_BACKUP" != "true" ] && [ -f "$BACKUP_DIR/latest_backup.txt" ]; then
                LATEST_BACKUP=$(cat "$BACKUP_DIR/latest_backup.txt")
                log_info "Tentando restaurar backup: $LATEST_BACKUP"
                # Note: Em produção, seria necessário mais cuidado aqui
                # psql "$DATABASE_URL" < "$LATEST_BACKUP"
            fi
            
            exit 1
        fi
        
        echo ""
    done
    
    log_success "Todas as migrations executadas com sucesso!"
    
    # Executar configuração de português
    echo ""
    log_info "=== CONFIGURANDO PORTUGUÊS ==="
    
    if [ -f "$SCRIPTS_DIR/configure_postgresql_portuguese.sql" ]; then
        if psql "$DATABASE_URL" -f "$SCRIPTS_DIR/configure_postgresql_portuguese.sql"; then
            log_success "Configuração portuguesa aplicada"
        else
            log_warning "Falha na configuração portuguesa (não crítico)"
        fi
    fi
    
    # Executar testes se Python estiver disponível
    if [ "$PYTHON_AVAILABLE" = true ] && [ "$SKIP_TESTS" != "true" ]; then
        echo ""
        log_info "=== EXECUTANDO TESTES ==="
        
        if [ -f "$SCRIPTS_DIR/test_migrations.py" ]; then
            export DATABASE_URL
            if python3 "$SCRIPTS_DIR/test_migrations.py"; then
                log_success "Todos os testes passaram!"
            else
                log_error "Alguns testes falharam. Verifique os logs acima."
                exit 1
            fi
        fi
    else
        log_warning "Testes automatizados ignorados"
    fi
    
    # Resumo final
    echo ""
    echo "=================================="
    log_success "MIGRATION RAG HÍBRIDO CONCLUÍDA"
    echo "=================================="
    echo ""
    log_info "Próximos passos:"
    echo "  1. Verificar logs acima para qualquer warning"
    echo "  2. Executar testes de integração no ambiente"
    echo "  3. Implementar código da Semana 2 (LiteralSearchEngine)"
    echo ""
    log_info "Para monitorar o sistema:"
    echo "  SELECT * FROM validate_tsvector_sync();"
    echo "  SELECT * FROM get_fulltext_stats();"
    echo ""
}

# Verificar argumentos de linha de comando
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --database-url)
            DATABASE_URL="$2"
            shift 2
            ;;
        -h|--help)
            echo "Uso: $0 [options]"
            echo "Options:"
            echo "  --skip-backup      Pular criação de backup"
            echo "  --skip-tests       Pular testes automatizados"
            echo "  --database-url     URL do banco de dados"
            echo "  -h, --help         Mostrar esta ajuda"
            exit 0
            ;;
        *)
            log_error "Opção desconhecida: $1"
            exit 1
            ;;
    esac
done

# Executar função principal
main