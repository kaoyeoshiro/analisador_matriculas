# Sistema de Auto-Atualização Automática

## 📋 Visão Geral

Este sistema implementa auto-atualização completamente automatizada seguindo o fluxograma:

**CODE → COMMIT → GITHUB ACTIONS → RELEASE → AUTO-UPDATE**

## 🔄 Como Funciona

### 1. Workflow Automático (GitHub Actions)

**Trigger**: A cada push no branch `main` ou `master`

**Processo**:
- Build automático com PyInstaller
- Versionamento incremental (v1.0.1, v1.0.2, v1.0.3...)
- Criação de release no GitHub
- Upload do executável como asset da release

### 2. Auto-Atualização no Cliente

**Verificação Automática**:
- ✅ 2 segundos após inicialização do app
- ✅ Execução em background (não bloqueia interface)
- ✅ Totalmente silenciosa
- ✅ Download e aplicação automáticos

**Fallback Manual**:
- Botão "Verificar Atualizações" na interface
- Confirmação do usuário antes de aplicar
- Feedback visual durante o processo

## 📁 Arquivos do Sistema

```
projeto/
├── .github/workflows/build-release.yml  # GitHub Actions workflow
├── updater.py                           # Módulo de auto-atualização
├── VERSION                              # Versão atual (1.0.0)
├── main.py                              # Integração com o sistema
└── Matriculas_Confrontantes_PGE_MS.spec # Configuração PyInstaller
```

## 🚀 Configuração Inicial

### 1. Repositório GitHub

O repositório já está configurado:
- **Repositório**: `https://github.com/kaoyeoshiro/analisador_matriculas`
- **Visibilidade**: Deve ser público (para API funcionar)
- **Permissões**: Contents: write, Actions: write

### 2. Primeira Release

Para ativar o sistema:

1. Faça um commit e push para `main`
2. O GitHub Actions criará automaticamente a primeira release
3. A partir daí, o sistema funcionará automaticamente

## 🛠️ Funcionamento Técnico

### Verificação de Versões

```python
# Versão atual (arquivo VERSION)
current_version = "1.0.0"

# Busca latest release via API
latest_version = "1.0.5"  # Exemplo

# Compara usando packaging.version
if version.parse(latest_version) > version.parse(current_version):
    # Aplica atualização
```

### Download e Aplicação

1. **Download**: Baixa executável da release
2. **Script Batch**: Cria script para substituir executável
3. **Substituição**: Para o app atual e aplica nova versão
4. **Reinicialização**: Inicia automaticamente nova versão

### Tratamento de Erros

- ✅ Timeout de rede (10s verificação, 30s download)
- ✅ Fallback em caso de erro
- ✅ Backup do executável atual
- ✅ Logs detalhados (modo debug)

## 🎯 Fluxo do Usuário

### Experiência Típica

1. **Usuário abre executável antigo**
2. **2 segundos depois**: Sistema verifica atualizações em background
3. **Se há nova versão**: Download automático inicia
4. **Após download**: Executável para e aplica atualização
5. **Resultado**: Nova versão inicia automaticamente

### Experiência Transparente

- ⚡ Sem interrupção da experiência
- 🔇 Completamente silencioso
- 🚀 Sempre na versão mais recente
- 🔄 Zero configuração necessária

## 🧪 Como Testar

### 1. Teste Local

```bash
python updater.py
```

### 2. Teste de Integração

```bash
python -c "from updater import create_updater; print('OK')"
```

### 3. Teste de Build

```bash
pyinstaller --clean --noconfirm Matriculas_Confrontantes_PGE_MS.spec
```

## 🔧 Personalização

### Configurar Repositório

```python
# No updater.py - função create_updater()
updater = AutoUpdater(
    repo_owner="kaoyeoshiro",           # Seu usuário GitHub
    repo_name="analisador_matriculas",  # Nome do repositório
    executable_name="RelatorioTJMS.exe" # Nome do executável
)
```

### Configurar Comportamento

```python
updater = AutoUpdater(
    # ... outros parâmetros
    silent=True,        # False = logs detalhados
    auto_update=True    # False = só verificação manual
)
```

## 📈 Versionamento

- **Formato**: v1.0.X (onde X = GITHUB_RUN_NUMBER)
- **Incremento**: Automático a cada build
- **Exemplo**: v1.0.1 → v1.0.2 → v1.0.3...

## 🔒 Segurança

- ✅ Downloads via HTTPS
- ✅ Verificação de integridade
- ✅ Backup automático antes de atualizar
- ✅ Rollback em caso de falha
- ✅ Timeout para evitar travamentos

## 🎉 Benefícios

### Para Desenvolvedores
- 🚀 Deploy automático
- 📦 Build CI/CD integrado
- 🔄 Distribuição instantânea
- 📊 Controle de versões automático

### Para Usuários
- ⚡ Sempre atualizado
- 🔇 Zero configuração
- 🚫 Sem downloads manuais
- ✨ Experiência transparente

## 🔍 Troubleshooting

### Problema: Atualização não funciona
- ✅ Verifique se repositório é público
- ✅ Confirme se há releases no GitHub
- ✅ Teste conexão com internet

### Problema: Build falha
- ✅ Verifique requirements.txt
- ✅ Confirme dependências PyInstaller
- ✅ Check logs do GitHub Actions

### Problema: Executável não inicia
- ✅ Teste modo debug (console=True)
- ✅ Verifique dependências DLL
- ✅ Confirme arquivo VERSION presente

---

**🤖 Sistema de Auto-Atualização v1.0 - Implementação Completa**

*Experiência de software profissional com atualizações transparentes!*