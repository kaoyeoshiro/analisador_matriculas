=============================================================================
    ANALISADOR DE USUCAPIÃO COM IA VISUAL - MATRÍCULAS E CONFRONTANTES
                        Procuradoria-Geral do Estado de MS
=============================================================================

🚀 COMO USAR O SISTEMA:

1. EXECUTAR O PROGRAMA:
   - Clique duas vezes em: Matriculas_Confrontantes_PGE_MS.exe
   - O sistema abrirá uma interface gráfica

2. CONFIGURAÇÃO INICIAL:
   - Obtenha uma API Key em: https://openrouter.ai/
   - Cole a chave no campo "API Key" na interface
   - Escolha o modelo de IA (recomendado: claude-3.5-sonnet)

3. PROCESSAR MATRÍCULAS:
   - Clique em "Adicionar PDFs/Imagens"
   - Selecione os arquivos de matrículas para análise
   - Clique em "Processar Todos"
   - Aguarde a análise ser concluída

4. VISUALIZAR RESULTADOS:
   - Os resultados aparecem na tabela principal
   - Clique em "Detalhes" para ver informações completas
   - Use "Exportar CSV" para salvar os dados

5. GERAR PLANTAS:
   - Após o processamento, clique em "Gerar Planta do Imóvel"
   - Uma representação visual será criada com base nos dados

📋 SISTEMA DE FEEDBACK:

Após cada análise, o sistema solicitará seu feedback:
- ✅ ACERTOU: Se as confrontações foram identificadas corretamente
- ❌ ERROU: Se houver problemas, descreva onde foi o erro

Seu feedback é essencial para melhorar o sistema!

🔧 CONFIGURAÇÃO DO FEEDBACK (PARA ADMINISTRADORES):

Para receber os feedbacks em uma planilha:
1. Abra o arquivo: GUIA_GOOGLE_FORMS_FEEDBACK.md
2. Siga as instruções para criar um Google Form
3. Configure a integração conforme o guia

⚠️ REQUISITOS DO SISTEMA:

- Windows 10/11
- Conexão com internet para API de IA
- Mínimo 4GB de RAM
- 100MB de espaço livre em disco

🆘 RESOLUÇÃO DE PROBLEMAS:

PROBLEMA: "Erro de API Key"
SOLUÇÃO: Verifique se a chave está correta e tem créditos

PROBLEMA: "Arquivo muito grande"
SOLUÇÃO: PDFs devem ter no máximo 20 páginas

PROBLEMA: "Erro de conexão"
SOLUÇÃO: Verifique sua conexão com internet

📁 ARQUIVOS GERADOS:

- feedback_pendente.json: Feedbacks salvos localmente
- plantas_*.png: Imagens das plantas geradas
- *.csv: Exportações de dados

🔒 PRIVACIDADE E SEGURANÇA:

- Nenhum dado pessoal é coletado
- Documentos são processados via API segura
- Feedbacks são anônimos
- Dados técnicos não incluem conteúdo sensível

📞 SUPORTE TÉCNICO:

Para suporte técnico:
1. Verifique os logs na interface do sistema
2. Consulte o arquivo feedback_pendente.json para erros
3. Entre em contato com a equipe de desenvolvimento

=============================================================================
                            VERSÃO 1.0.0 - SETEMBRO 2025
                    Desenvolvido para a PGE-MS com tecnologia IA
=============================================================================
