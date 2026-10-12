# Forte Gesso | Sistema de gestão

Sistema web responsivo com login, clientes, obras, agenda, orçamentos imprimíveis, lançamentos financeiros, cheques, materiais e despesas gerais. Todos os arquivos do projeto estão na raiz, sem subpastas.

## Implantação no GitHub + Coolify

1. Crie um repositório e envie **todos os arquivos da raiz** deste pacote diretamente para a raiz do GitHub (incluindo `Dockerfile`, `app.py`, `index.html`, `logo.jpg`, `requirements.txt`). Não envie só o ZIP.
2. No Coolify, crie uma aplicação a partir do repositório, com **build pack Dockerfile**. Porta: **8000**.
3. Em Environment Variables, defina `SECRET_KEY` com um texto longo e aleatório, `ADMIN_USER` e `ADMIN_PASSWORD` com uma senha forte **antes da primeira inicialização**. Configure também `DATABASE_PATH=/data/fortegesso.db` e `COOKIE_SECURE=1` somente se estiver usando domínio HTTPS.
4. Crie um **volume persistente** no Coolify: caminho dentro do container `/data` (por exemplo nome `fortegesso-dados`). Sem volume, os dados podem desaparecer após redeploy.
5. Faça o deploy e acesse o endereço gerado. Troque a senha no sistema após entrar.

**Login inicial, somente se não forem configuradas as variáveis antes do primeiro deploy:** `admin` / `admin123`. Altere imediatamente. `ADMIN_USER` e `ADMIN_PASSWORD` só são lidos na criação do primeiro usuário e não resetam uma senha existente.

## Funcionalidades
- Clientes: cadastrar, pesquisar, editar, excluir.
- Obras: cliente opcional, data sem horário, status, valor combinado, ajudante, notas.
- Agenda: visualização mensal dos serviços programados.
- Orçamentos: itens, quantidades, preços, total automático, aprovação, impressão em PDF via navegador.
- Financeiro: receita, material, despesa geral e ajudante em categorias independentes; vencimento, baixa e data de pagamento.
- Cheques: emitidos e recebidos via lançamentos com forma de pagamento cheque; número, banco, titular e data de compensação.
- Relatórios: somente fluxo efetivamente pago/recebido pelo mês da baixa; valores pendentes são separados.
- Exportação CSV; layout para celular e instalação pela opção Adicionar à Tela de Início do navegador.

## Regra de financeiro
O valor contratado em uma obra e o custo previsto do ajudante **não criam automaticamente lançamentos**, evitando duplicar receitas e gastos. Crie os recebimentos/pagamentos no Financeiro. Um cheque é uma **forma de pagamento de um único lançamento**. O valor só entra no saldo realizado ao marcar `pago` na data da compensação, sem um lançamento extra. Não trate cheque pendente como dinheiro disponível.

## Execução local
`pip install -r requirements.txt` e `python app.py`. Disponível em http://localhost:8000.

## Observações
Versão inicial de gestão, sem integração bancária, emissão fiscal, automação do WhatsApp, multiusuários com permissões ou anexo de fotos. Faça backup periódico do arquivo no volume `/data/fortegesso.db`, preferencialmente com o serviço parado ou usando backup SQLite consistente.

## Atualização visual Mobile 2.0
Esta versão redesenha a navegação do celular com barra inferior de cinco atalhos, menu lateral com demais módulos, cartões responsivos para tabelas, formulário otimizado para toque e ações rápidas na página inicial. A lógica de armazenamento e as rotas da API são preservadas. Para atualizar, substitua os arquivos do repositório e faça redeploy, mantendo o mesmo volume `/data`. Não exclua o volume persistente.
