DESK 0.13.1 — TESTE DO CONTROLE E DO SERVIÇO

Instale na máquina que será acessada, no perfil de usuário que já usa o Desk.
Se já houver um serviço Desk 0.13.0 instalado, remova apenas o aplicativo
"Desk - Serviço de tela de bloqueio" em Aplicativos instalados do Windows,
aprovando como administrador. Não remova o Desk nem seus dados de usuário.
O instalador novo não sobrescreve um serviço antigo em execução.
1. Encerre a sessão remota e saia do Desk pelo menu > Sair do Desk.
2. Instale Desk-0.13.1-Update.exe. Seu número fixo e suas configurações locais
   são preservados. Confira em Configurações > Atualizações: versão 0.13.1.
3. Execute Desk-Service-0.13.1-Setup.exe e aprove a solicitação de administrador.
   Selecione o Desk.exe recém-instalado e marque a aprovação da versão exata
   para teste pessoal. O vínculo anterior precisa ser substituído por este.
4. Abra o Desk e confira Configurações > Acesso sem supervisão >
   Mouse, teclado e tela de bloqueio > Verificar serviço de controle.
5. Reconecte e teste primeiro mouse e teclado na área de trabalho. O serviço
   é escolhido somente em uma sessão aprovada com permissão de controle.
   Depois, bloqueie a máquina pessoalmente e digite VOCÊ a senha pela sessão
   remota. Não envie a senha ao chat.

O serviço inicia com o Windows e pode fornecer captura e entrada nas telas
protegidas, incluindo bloqueio e avisos de administrador. Não remove nem salva
a senha do Windows. Não oferece acesso antes do primeiro login do usuário.
Os arquivos continuam sujeitos às proteções do Windows; não são instaladas
exclusões de antivírus, exceções de política ou certificados raiz.

O modo pessoal vincula o usuário, o caminho e as versões exatas aprovadas pelo
administrador. Uma atualização do Desk exige renovar esse vínculo. O serviço
0.13.1 acrescenta verificação da troca de desktop antes de injetar entrada;
isso evita reutilizar uma captura antiga após bloquear/desbloquear o Windows.
Este pacote é uma prévia para teste; a validação entre computadores ainda
precisa ser concluída. A liberação anterior da Microsoft foi para o instalador
0.13.0 e não constitui assinatura digital deste novo pacote.

O pacote público não contém credenciais de relay, identidades ou senhas.
Atualizações preservam a configuração local. Uma instalação nova precisa da
configuração de transporte utilizada pelo proprietário.
