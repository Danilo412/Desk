DESK 0.13.0 — TESTE PESSOAL DO SERVIÇO

O Desk 0.12.5 já abriu neste PC com o Smart App Control ativo. Esta prévia
0.13.0 acrescenta o suporte ao serviço na máquina que será acessada.

NA OUTRA MÁQUINA, UMA VEZ, COM ACESSO DIRETO:
1. Entre no Windows e instale Desk-0.13.0-Update.exe normalmente no perfil
   que já usa o Desk. Abra e confira o mesmo número e o estado Disponível.
2. Execute Desk-Service-0.13.0-Setup.exe e aprove a solicitação de administrador.
3. Selecione o Desk.exe recém-instalado. Na página de autorização, marque
   "Aprovar esta versão exata para teste pessoal (sem certificado)".
   Confira e conclua a instalação. O instalador valida os arquivos exatos.
4. Deixe o Desk aberto. O serviço atende somente sessões já autorizadas com
   mouse e teclado do usuário configurado. Teste a conexão, bloqueie o Windows
   diretamente e digite VOCÊ a senha pela sessão remota. Não envie a senha.

O serviço inicia com o Windows e pode fornecer tela e entrada nas telas
protegidas, incluindo bloqueio e avisos de administrador. Não remove a senha,
não salva senhas e não oferece uma conexão antes do primeiro login do usuário.
Não modifica SAC, Defender, UAC, certificados raiz ou permissões do Windows.
Os programas ainda precisam ser permitidos pelo próprio Windows.

IMPORTANTE SOBRE ATUALIZAÇÕES NO MODO PESSOAL:
O vínculo vale apenas para esta versão exata. Antes de atualizar o Desk,
planeje uma nova autorização administrativa do serviço; caso contrário, o
acesso à tela bloqueada ficará indisponível. A conexão ao desktop desbloqueado
continua seguindo as permissões normais. Este é um teste, não uma promessa de
suporte contínuo já validado. Assinatura de editor confiável permite outro modo
de distribuição; ela não é criada nem simulada por este pacote.

O pacote público não inclui credenciais de relay, identidades ou senhas.
Atualizações preservam a configuração existente. Instalações novas precisam
da configuração de transporte utilizada nos seus computadores.
